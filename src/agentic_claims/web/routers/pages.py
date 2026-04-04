"""Page route handlers for all 4 application pages."""

import uuid

from fastapi import APIRouter
from starlette.requests import Request

from agentic_claims.core.imageStore import clearImage
from agentic_claims.web.routers.chat import fetchClaimsForTable
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.sessionQueues import removeQueue
from agentic_claims.web.templating import templates

router = APIRouter()


@router.get("/")
async def chatPage(request: Request):
    """Render the AI Expense Submission chat page.

    Generates fresh thread_id and claim_id on every page load to match
    Chainlit's on_chat_start behavior. This ensures the checkpointer
    starts with a clean slate — no stale conversation history.
    """
    oldClaimId = request.session.get("claim_id")
    oldThreadId = request.session.get("thread_id")
    if oldClaimId:
        clearImage(oldClaimId)
    if oldThreadId:
        removeQueue(oldThreadId)

    request.session["thread_id"] = str(uuid.uuid4())
    request.session["claim_id"] = str(uuid.uuid4())
    request.session.pop("awaiting_clarification", None)

    sessionIds = getSessionIds(request)
    initialSteps = [
        {"name": "Receipt Uploaded", "icon": "cloud_upload", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": ""},
        {"name": "AI Extraction", "icon": "troubleshoot", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": "Awaiting receipt upload..."},
        {"name": "Policy Check", "icon": "rule", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": "Awaiting extraction data..."},
        {"name": "Final Decision", "icon": "verified", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": "Awaiting policy check..."},
    ]

    claims = await fetchClaimsForTable()
    sessionTotal = sum(float(c.get("total_amount", 0) or 0) for c in claims)

    return templates.TemplateResponse(
        request,
        "chat.html",
        context={
            "activePage": "chat",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
            "steps": initialSteps,
            "claims": claims,
            "sessionTotal": f"SGD {sessionTotal:.2f}",
            "itemCount": len(claims),
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
