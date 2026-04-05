"""Login and logout route handlers."""

from fastapi import APIRouter, Form
from starlette.requests import Request
from starlette.responses import RedirectResponse

from agentic_claims.web.auth import authenticateUser
from agentic_claims.web.templating import templates

router = APIRouter()

_ROLE_DEFAULTS = {
    "user": "/",
    "reviewer": "/dashboard",
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

    # Extend session cookie lifetime if remember_me checked (7 days)
    if remember_me:
        request.session["remember_me"] = True

    redirectTarget = _ROLE_DEFAULTS.get(user.role, "/")
    return RedirectResponse(redirectTarget, status_code=302)


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
