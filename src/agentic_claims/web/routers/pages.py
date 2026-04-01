"""Page route handlers for all 4 application pages."""

from fastapi import APIRouter
from starlette.requests import Request

from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

router = APIRouter()


@router.get("/")
async def chatPage(request: Request):
    """Render the AI Expense Submission chat page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        request,
        "chat.html",
        context={
            "activePage": "chat",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
        },
    )


@router.get("/dashboard")
async def dashboardPage(request: Request):
    """Render the Approver Dashboard page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={
            "activePage": "dashboard",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
        },
    )


@router.get("/audit")
async def auditPage(request: Request):
    """Render the Audit & Transparency Log page."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        request,
        "audit.html",
        context={
            "activePage": "audit",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
        },
    )


@router.get("/review/{claimId}")
async def reviewPage(request: Request, claimId: str):
    """Render the Claim Review page for a specific claim."""
    sessionIds = getSessionIds(request)
    return templates.TemplateResponse(
        request,
        "review.html",
        context={
            "activePage": "review",
            "claimId": claimId,
            "threadId": sessionIds["threadId"],
        },
    )
