"""Tests for the Approver Dashboard router — page handler and API endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

from agentic_claims.web.main import projectRoot

_REVIEWER_USER = {
    "userId": 1,
    "username": "james",
    "role": "reviewer",
    "employeeId": "EMP002",
    "displayName": "James Wilson",
}

_EMPLOYEE_USER = {
    "userId": 2,
    "username": "alice",
    "role": "user",
    "employeeId": "EMP001",
    "displayName": "Alice Tan",
}


@pytest.fixture
def client():
    """Test client with dashboard router, mocked getCurrentUser as reviewer."""
    from agentic_claims.web.routers.dashboard import router as dashboardRouter
    from agentic_claims.web.routers.pages import router as pagesRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    testApp.include_router(dashboardRouter)
    testApp.include_router(pagesRouter)
    testApp.state.graph = MagicMock()

    with patch("agentic_claims.web.routers.dashboard.getCurrentUser", return_value=_REVIEWER_USER):
        with patch("agentic_claims.web.routers.pages.getCurrentUser", return_value=_REVIEWER_USER):
            with TestClient(testApp, follow_redirects=False) as c:
                yield c


@pytest.fixture
def employeeClient():
    """Test client with non-reviewer user to verify role enforcement."""
    from agentic_claims.web.routers.dashboard import router as dashboardRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(dashboardRouter)

    with patch("agentic_claims.web.routers.dashboard.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


def _mockKpiSession(pending=3, approved=10, escalated=2, rejected=1):
    """Build a mock async session that returns KPI status rows."""
    rows = [
        ("pending", pending),
        ("ai_approved", approved),
        ("escalated", escalated),
        ("ai_rejected", rejected),
    ]
    mockResult = MagicMock()
    mockResult.all.return_value = rows
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)
    return mockSession


def _mockClaimsSession():
    """Build a mock async session that returns claims rows."""
    rows = [
        (1, "CLM-001", "EMP001", "pending", Decimal("45.00"), "SGD", None, "Alice Tan"),
        (2, "CLM-002", "EMP002", "ai_approved", Decimal("120.00"), "SGD", None, None),
    ]
    mockResult = MagicMock()
    mockResult.all.return_value = rows
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)
    return mockSession


def _mockEfficiencySession():
    """Build a mock async session that returns hourly efficiency rows."""
    rows = [(9, 10, 8), (10, 5, 4), (11, 20, 18)]
    mockResult = MagicMock()
    mockResult.all.return_value = rows
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)
    return mockSession


def testKpisEndpointReturnsCorrectShape(client):
    """GET /api/dashboard/kpis returns JSON with pending, autoApproved, escalated, rejected."""
    mockSession = _mockKpiSession(pending=3, approved=10, escalated=2)
    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", return_value=mockSession):
        response = client.get("/api/dashboard/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "pending" in data
    assert "autoApproved" in data
    assert "escalated" in data
    assert "rejected" in data
    assert data["pending"] == 3
    assert data["autoApproved"] == 10
    assert data["escalated"] == 2


def testKpisEndpointForbiddenForNonReviewer(employeeClient):
    """GET /api/dashboard/kpis returns 403 for non-reviewer."""
    response = employeeClient.get("/api/dashboard/kpis")
    assert response.status_code == 403


def testClaimsEndpointReturnsList(client):
    """GET /api/dashboard/claims returns a list of claim dicts."""
    mockSession = _mockClaimsSession()
    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", return_value=mockSession):
        response = client.get("/api/dashboard/claims")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    first = data[0]
    assert "id" in first
    assert "claimNumber" in first
    assert "employeeName" in first
    assert "status" in first
    assert "totalAmount" in first
    assert "currency" in first


def testClaimsEndpointEmployeeNameFallback(client):
    """Claims without a matching user show employeeId as name."""
    mockSession = _mockClaimsSession()
    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", return_value=mockSession):
        response = client.get("/api/dashboard/claims")
    data = response.json()
    # Second row has no displayName (None) — should fallback to employeeId
    second = data[1]
    assert second["employeeName"] == "EMP002"


def testClaimsEndpointForbiddenForNonReviewer(employeeClient):
    """GET /api/dashboard/claims returns 403 for non-reviewer."""
    response = employeeClient.get("/api/dashboard/claims")
    assert response.status_code == 403


def testEfficiencyEndpointReturnsHourlyRates(client):
    """GET /api/dashboard/efficiency returns hourlyRates list."""
    mockSession = _mockEfficiencySession()
    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", return_value=mockSession):
        response = client.get("/api/dashboard/efficiency")
    assert response.status_code == 200
    data = response.json()
    assert "hourlyRates" in data
    rates = data["hourlyRates"]
    assert isinstance(rates, list)
    assert len(rates) == 3
    first = rates[0]
    assert "hour" in first
    assert "rate" in first
    assert first["rate"] == 80.0  # 8/10 * 100


def testEfficiencyEndpointForbiddenForNonReviewer(employeeClient):
    """GET /api/dashboard/efficiency returns 403 for non-reviewer."""
    response = employeeClient.get("/api/dashboard/efficiency")
    assert response.status_code == 403


def testDashboardPageReturns200WithKpis(client):
    """GET /dashboard renders page with KPI data in HTML."""
    mockKpi = _mockKpiSession(pending=5, approved=20, escalated=1)
    mockClaims = _mockClaimsSession()

    def sessionFactory():
        """Return alternating sessions for kpis then claims queries."""
        sessions = [mockKpi, mockClaims]
        idx = 0

        class _CM:
            async def __aenter__(self):
                nonlocal idx
                s = sessions[min(idx, len(sessions) - 1)]
                idx += 1
                return s

            async def __aexit__(self, *args):
                return False

        return _CM()

    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", side_effect=sessionFactory):
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Approver Dashboard" in response.text


def testDashboardPageRedirectsNonReviewer():
    """GET /dashboard redirects users with role != reviewer to /."""
    from agentic_claims.web.routers.dashboard import router as dashboardRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(dashboardRouter)

    with patch("agentic_claims.web.routers.dashboard.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            response = c.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def testDashboardPageNotInPagesRouter():
    """/dashboard route no longer exists in pages.py router."""
    from agentic_claims.web.routers import pages

    routes = [r.path for r in pages.router.routes]
    assert "/dashboard" not in routes


def testKpisEndpointIncludesRejectedCount(client):
    """GET /api/dashboard/kpis returns rejected count in status breakdown."""
    mockSession = _mockKpiSession(pending=2, approved=8, escalated=3, rejected=4)
    with patch("agentic_claims.web.routers.dashboard.getAsyncSession", return_value=mockSession):
        response = client.get("/api/dashboard/kpis")
    assert response.status_code == 200
    data = response.json()
    assert "rejected" in data
    assert data["rejected"] == 4
    assert data["pending"] == 2
    assert data["escalated"] == 3
