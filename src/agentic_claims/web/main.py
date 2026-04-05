"""FastAPI application with lifespan-managed LangGraph singleton."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from agentic_claims.core.config import getSettings
from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.logging import setupLogging
from agentic_claims.web.routers.auth import router as authRouter
from agentic_claims.web.routers.chat import router as chatRouter
from agentic_claims.web.routers.pages import router as pagesRouter

logger = logging.getLogger(__name__)

# Paths that do not require authentication
_PUBLIC_PATHS = {"/login", "/logout"}
_PUBLIC_PREFIXES = ("/static/",)


def _findProjectRoot() -> Path:
    """Find the project root containing static/ and templates/ directories.

    Walks up from this file's location. Falls back to /app (Docker workdir)
    then cwd.
    """
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "static").is_dir() and (candidate / "templates").is_dir():
            return candidate
    # Docker workdir fallback
    docker = Path("/app")
    if (docker / "static").is_dir():
        return docker
    return Path.cwd()


projectRoot = _findProjectRoot()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize graph and checkpointer once at startup (singleton pattern)."""
    setupLogging()
    graph, pool = await getCompiledGraph()
    app.state.graph = graph
    app.state.pool = pool
    logger.info("LangGraph graph and checkpointer initialized (lifespan singleton)")
    yield
    await pool.close()
    logger.info("Checkpointer pool closed")


settings = getSettings()

class AuthMiddleware(BaseHTTPMiddleware):
    """Redirect unauthenticated requests to /login.

    Exempts /login, /logout, and /static/* paths.
    Requires SessionMiddleware to have run first (must be added AFTER this one).
    """

    async def dispatch(self, request: Request, callNext):
        path = request.url.path
        if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await callNext(request)
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=302)
        return await callNext(request)


app = FastAPI(title="Cognitive Atelier", lifespan=lifespan)

# Middleware is applied in LIFO order: SessionMiddleware runs first (outermost),
# then AuthMiddleware can safely access request.session.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="agentic_session",
    max_age=None,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")

app.include_router(authRouter)
app.include_router(chatRouter)
app.include_router(pagesRouter)
