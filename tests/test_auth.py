"""Unit tests for authentication module."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from starlette.testclient import TestClient


@pytest.fixture(autouse=True)
def setTestEnv():
    """Ensure session secret key is set before app import."""
    os.environ.setdefault("SESSION_SECRET_KEY", "test-secret-key")


@pytest.fixture
def client():
    """TestClient with mocked lifespan and no real DB."""
    with patch("agentic_claims.core.graph.getCompiledGraph") as mockGetGraph:
        mockGraph = AsyncMock()
        mockPool = AsyncMock()
        mockGetGraph.return_value = (mockGraph, mockPool)

        from agentic_claims.web.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _makeUser(username="sagar", role="user", employeeId="1010736", displayName="Sagar"):
    """Build a mock User object with a valid bcrypt hash for 'sagar123'."""
    user = MagicMock()
    user.id = 1
    user.username = username
    user.hashedPassword = bcrypt.hashpw(b"sagar123", bcrypt.gensalt()).decode("utf-8")
    user.role = role
    user.employeeId = employeeId
    user.displayName = displayName
    return user


# ---------------------------------------------------------------------------
# authenticateUser unit tests
# ---------------------------------------------------------------------------


def _mockAuthDb(mockUser):
    """Context manager factory that patches DB access in authenticateUser."""
    mockEngine = AsyncMock()
    mockSession = AsyncMock()
    mockResult = MagicMock()
    mockResult.scalar_one_or_none.return_value = mockUser
    mockSession.execute = AsyncMock(return_value=mockResult)

    mockSessionCtx = MagicMock()
    mockSessionCtx.__aenter__ = AsyncMock(return_value=mockSession)
    mockSessionCtx.__aexit__ = AsyncMock(return_value=False)

    from contextlib import ExitStack
    from unittest.mock import patch

    stack = ExitStack()
    stack.enter_context(
        patch("agentic_claims.web.auth.create_async_engine", return_value=mockEngine)
    )
    stack.enter_context(patch("agentic_claims.web.auth.AsyncSession", return_value=mockSessionCtx))
    return stack


@pytest.mark.asyncio
async def testAuthenticateUserValidCredentials():
    """authenticateUser returns User when credentials match."""
    mockUser = _makeUser()

    with _mockAuthDb(mockUser):
        from agentic_claims.web.auth import authenticateUser

        result = await authenticateUser("sagar", "sagar123")
        assert result is mockUser


@pytest.mark.asyncio
async def testAuthenticateUserInvalidPassword():
    """authenticateUser returns None when password does not match."""
    mockUser = _makeUser()

    with _mockAuthDb(mockUser):
        from agentic_claims.web.auth import authenticateUser

        result = await authenticateUser("sagar", "wrongpassword")
        assert result is None


@pytest.mark.asyncio
async def testAuthenticateUserUnknownUsername():
    """authenticateUser returns None when username is not found."""
    with _mockAuthDb(mockUser=None):
        from agentic_claims.web.auth import authenticateUser

        result = await authenticateUser("nobody", "password")
        assert result is None


# ---------------------------------------------------------------------------
# requireAuth unit tests
# ---------------------------------------------------------------------------


def testRequireAuthNoSession():
    """requireAuth returns redirect to /login when no user_id in session."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "session": {},  # empty session — no user_id
    }
    request = Request(scope)

    from agentic_claims.web.auth import requireAuth

    result = requireAuth(request)
    assert result is not None
    assert result.status_code == 302
    assert result.headers["location"] == "/login"


def testRequireAuthWithSession():
    """requireAuth returns None when user_id is present in session."""
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": [],
        "session": {"user_id": 1},
    }
    request = Request(scope)

    from agentic_claims.web.auth import requireAuth

    result = requireAuth(request)
    assert result is None


# ---------------------------------------------------------------------------
# Route integration tests (via TestClient)
# ---------------------------------------------------------------------------


def testLoginGetRendersForm(client):
    """GET /login returns 200 with login form visible."""
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 200
    assert "Sign In" in response.text
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text


def testLogoutClearsSession(client):
    """GET /logout redirects to /login."""
    # First set a fake session
    client.cookies.set("agentic_session", "dummy")
    response = client.get("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def testUnauthenticatedRootRedirectsToLogin(client):
    """GET / without session redirects to /login."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["location"]


def testLoginPostInvalidCredentialsShowsError(client):
    """POST /login with wrong credentials renders login page with error."""
    mockAuth = patch(
        "agentic_claims.web.routers.auth.authenticateUser", new=AsyncMock(return_value=None)
    )
    with mockAuth:
        response = client.post(
            "/login",
            data={"username": "sagar", "password": "wrongpassword"},
            follow_redirects=False,
        )
    assert response.status_code == 200
    assert "Invalid username or password" in response.text
    # Username preserved
    assert "sagar" in response.text


def testLoginPostValidCredentialsUserRedirectsToRoot(client):
    """POST /login with valid user credentials redirects to /."""
    mockUser = _makeUser(role="user")
    mockAuth = patch(
        "agentic_claims.web.routers.auth.authenticateUser", new=AsyncMock(return_value=mockUser)
    )
    with mockAuth:
        response = client.post(
            "/login",
            data={"username": "sagar", "password": "sagar123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def testLoginPostValidCredentialsReviewerRedirectsToManage(client):
    """POST /login with valid reviewer credentials redirects to /manage."""
    mockUser = _makeUser(
        username="james", role="reviewer", employeeId="909090", displayName="James"
    )
    mockAuth = patch(
        "agentic_claims.web.routers.auth.authenticateUser",
        new=AsyncMock(return_value=mockUser),
    )
    with mockAuth:
        response = client.post(
            "/login",
            data={"username": "james", "password": "james123"},
            follow_redirects=False,
        )
    assert response.status_code == 302
    assert response.headers["location"] == "/manage"
