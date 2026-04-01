"""Page route handlers for all 4 application pages."""

from fastapi import APIRouter
from starlette.requests import Request

from agentic_claims.web.main import templates
from agentic_claims.web.session import getSessionIds

router = APIRouter()


@router.get("/")
async def chatPage(request: Request):
    """Render the AI Expense Submission chat page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "activePage": "chat", "session": sessionIds},
    )


@router.get("/dashboard")
async def dashboardPage(request: Request):
    """Render the Approver Dashboard page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "activePage": "dashboard", "session": sessionIds},
    )


@router.get("/audit")
async def auditPage(request: Request):
    """Render the Audit & Transparency Log page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        "audit.html",
        {"request": request, "activePage": "audit", "session": sessionIds},
    )


@router.get("/review/{claimId}")
async def reviewPage(request: Request, claimId: str):
    """Render the Claim Review page for a specific claim."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        "review.html",
        {
            "request": request,
            "activePage": "review",
            "claimId": claimId,
            "session": sessionIds,
        },
    )
