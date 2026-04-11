"""Page route handlers for all application pages."""

import logging

from fastapi import APIRouter
from starlette.requests import Request

from agentic_claims.core.logging import logEvent
from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.routers.chat import fetchClaimsForTable
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def chatPage(request: Request):
    """Render the AI Expense Submission chat page.

    Reuses the active thread_id and claim_id so navigating away and back keeps
    the current conversation. Fresh IDs are created only by /chat/reset,
    logout, or the New Claim button that calls reset.
    """
    sessionIds = getSessionIds(request)
    currentUser = getCurrentUser(request)
    logEvent(
        logger,
        "chat.page_loaded",
        logCategory="chat_history",
        actorType="user",
        userId=currentUser["username"],
        username=currentUser["username"],
        employeeId=currentUser["employeeId"],
        claimId=sessionIds["claimId"],
        draftClaimNumber=f"DRAFT-{sessionIds['claimId'][:8]}",
        threadId=sessionIds["threadId"],
        status="loaded",
        message="Chat page loaded with existing session",
    )

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
            "name": "Claim Submission",
            "icon": "send",
            "waitingText": "Awaiting policy check...",
        },
    ]

    claims = await fetchClaimsForTable(employeeId=currentUser["employeeId"])
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
