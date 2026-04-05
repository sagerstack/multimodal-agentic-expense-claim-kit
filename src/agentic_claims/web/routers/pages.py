"""Page route handlers for all application pages."""

import uuid

from fastapi import APIRouter
from starlette.requests import Request

from agentic_claims.core.imageStore import clearImage
from agentic_claims.web.auth import getCurrentUser
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
    currentUser = getCurrentUser(request)

    _pending = {"status": "pending", "timestamp": None, "details": None, "description": None}
    initialSteps = [
        {**_pending, "name": "Receipt Uploaded", "icon": "cloud_upload", "waitingText": ""},
        {
            **_pending,
            "name": "AI Extraction",
            "icon": "troubleshoot",
            "waitingText": "Awaiting receipt upload...",
        },
        {
            **_pending,
            "name": "Policy Check",
            "icon": "rule",
            "waitingText": "Awaiting extraction data...",
        },
        {
            **_pending,
            "name": "Final Decision",
            "icon": "verified",
            "waitingText": "Awaiting policy check...",
        },
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
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
        },
    )
