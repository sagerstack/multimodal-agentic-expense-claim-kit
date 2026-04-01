"""Shared FastAPI dependencies."""

from starlette.requests import Request

from agentic_claims.web.templating import templates


def getGraph(request: Request):
    """Return the compiled LangGraph graph from app state."""
    return request.app.state.graph


def getTemplates(request: Request):
    """Return the Jinja2Templates instance."""
    return templates
