"""FastAPI application with lifespan-managed LangGraph singleton."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from agentic_claims.core.config import getSettings
from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.web.routers.pages import router as pagesRouter

logger = logging.getLogger(__name__)

projectRoot = Path(__file__).resolve().parent.parent.parent.parent
templates = Jinja2Templates(directory=str(projectRoot / "templates"))


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
