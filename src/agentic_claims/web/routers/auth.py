"""Login and logout route handlers."""

import logging

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import RedirectResponse

from agentic_claims.core.logging import logEvent
from agentic_claims.web.auth import authenticateUser
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)
router = APIRouter()

_ROLE_DEFAULTS = {
    "user": "/",
    "reviewer": "/manage",
}


@router.get("/login")
async def loginGet(request: Request):
    """Render login page. Redirect to role default if already authenticated."""
    if request.session.get("user_id"):
        role = request.session.get("role", "user")
        return RedirectResponse(_ROLE_DEFAULTS.get(role, "/"), status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        context={"error": None, "username": ""},
    )


@router.post("/login")
async def loginPost(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(default=False),
):
    """Process login form. Set session on success, return error on failure."""
    user = await authenticateUser(username, password)
    if user is None:
        logEvent(
            logger,
            "user.login_failed",
            logCategory="chat_history",
            actorType="user",
            username=username,
            status="failed",
            message="User login failed",
        )
        return templates.TemplateResponse(
            request,
            "login.html",
            context={"error": "Invalid username or password", "username": username},
            status_code=200,
        )

    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["employee_id"] = user.employeeId
    request.session["display_name"] = user.displayName
    # Store remember_me flag in session so RememberMeMiddleware can patch Max-Age
    request.session["remember_me"] = bool(remember_me)

    logEvent(
        logger,
        "user.login_succeeded",
        logCategory="chat_history",
        actorType="user",
        userId=user.username,
        username=user.username,
        employeeId=user.employeeId,
        status="completed",
        message="User login succeeded",
    )

    redirectTarget = _ROLE_DEFAULTS.get(user.role, "/")
    return RedirectResponse(redirectTarget, status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    logEvent(
        logger,
        "user.logout",
        logCategory="chat_history",
        actorType="user",
        userId=request.session.get("username"),
        username=request.session.get("username"),
        employeeId=request.session.get("employee_id"),
        claimId=request.session.get("claim_id"),
        threadId=request.session.get("thread_id"),
        status="completed",
        message="User logged out",
    )
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
