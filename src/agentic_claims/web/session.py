"""Session management for per-conversation state."""

import uuid

from starlette.requests import Request


def getSessionIds(request: Request) -> dict:
    """Get or create session IDs for thread and claim tracking.

    Checks the session for existing IDs. If missing, generates new UUIDs
    and stores them in the session cookie.

    Returns:
        Dict with threadId and claimId strings.
    """
    if "thread_id" not in request.session:
        request.session["thread_id"] = str(uuid.uuid4())
    if "claim_id" not in request.session:
        request.session["claim_id"] = str(uuid.uuid4())

    return {
        "threadId": request.session["thread_id"],
        "claimId": request.session["claim_id"],
    }
