"""Shared FastAPI dependencies."""

from starlette.requests import Request


def getGraph(request: Request):
    """Return the compiled LangGraph graph from app state."""
    return request.app.state.graph


def getTemplates(request: Request):
    """Return the Jinja2Templates instance."""
    from agentic_claims.web.main import templates

    return templates
