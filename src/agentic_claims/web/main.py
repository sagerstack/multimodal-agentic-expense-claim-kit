"""FastAPI application with lifespan-managed LangGraph singleton."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles

from agentic_claims.core.config import getSettings
from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.web.routers.pages import router as pagesRouter

logger = logging.getLogger(__name__)

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
    graph, checkpointerCtx = await getCompiledGraph()
    app.state.graph = graph
    app.state.checkpointerCtx = checkpointerCtx
    logger.info("LangGraph graph and checkpointer initialized (lifespan singleton)")
    yield
    await checkpointerCtx.__aexit__(None, None, None)
    logger.info("Checkpointer connection closed")


settings = getSettings()

app = FastAPI(title="Cognitive Atelier", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie="agentic_session",
    max_age=None,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")

app.include_router(pagesRouter)
