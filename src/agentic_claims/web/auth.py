"""Authentication middleware and helpers for session-based auth."""

from typing import Optional

import bcrypt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.requests import Request
from starlette.responses import RedirectResponse

from agentic_claims.core.config import getSettings
from agentic_claims.infrastructure.database.models import User


async def getDbSession() -> AsyncSession:
    """Create a transient async SQLAlchemy session for auth queries."""
    settings = getSettings()
    engine = create_async_engine(settings.postgres_dsn_async, pool_pre_ping=True)
    async with AsyncSession(engine) as session:
        yield session
    await engine.dispose()


async def authenticateUser(username: str, password: str) -> Optional[User]:
    """Verify credentials against the users table.

    Returns the User object on success, None on failure.
    """
    settings = getSettings()
    engine = create_async_engine(settings.postgres_dsn_async, pool_pre_ping=True)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            user = result.scalar_one_or_none()
            if user is None:
                return None
            if not bcrypt.checkpw(
                password.encode("utf-8"), user.hashedPassword.encode("utf-8")
            ):
                return None
            return user
    finally:
        await engine.dispose()


def requireAuth(request: Request) -> Optional[RedirectResponse]:
    """Check that a valid session exists.

    Returns a RedirectResponse to /login if unauthenticated, else None.
    Called from each protected route handler.
    """
    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=302)
    return None


def getCurrentUser(request: Request) -> dict:
    """Extract the current user data from session.

    Raises HTTP 401 if no session is present.
    """
    userId = request.session.get("user_id")
    if not userId:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "userId": userId,
        "username": request.session.get("username"),
        "role": request.session.get("role"),
        "employeeId": request.session.get("employee_id"),
        "displayName": request.session.get("display_name"),
    }


def requireRole(role: str):
    """Dependency factory that enforces a specific role.

    Redirects user role to / and reviewer role to /manage on mismatch.
    """

    def _checkRole(request: Request) -> Optional[RedirectResponse]:
        authRedirect = requireAuth(request)
        if authRedirect:
            return authRedirect
        sessionRole = request.session.get("role")
        if sessionRole != role:
            target = "/manage" if sessionRole == "reviewer" else "/"
            return RedirectResponse(target, status_code=302)
        return None

    return _checkRole
