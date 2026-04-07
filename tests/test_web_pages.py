"""Smoke tests for all 4 page routes and session cookie."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

_FAKE_USER = {
    "userId": 1,
    "username": "testuser",
    "role": "reviewer",
    "employeeId": "EMP001",
    "displayName": "Test User",
}


@pytest.fixture
def client():
    """Lightweight TestClient with session middleware but no auth middleware.

    Mirrors test_chat_page.py pattern — builds a minimal app without AuthMiddleware
    so page content tests are not coupled to the auth flow.
    """
    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware
    from starlette.staticfiles import StaticFiles

    from agentic_claims.web.main import projectRoot
    from agentic_claims.web.routers.audit import router as auditRouter
    from agentic_claims.web.routers.chat import router as chatRouter
    from agentic_claims.web.routers.dashboard import router as dashboardRouter
    from agentic_claims.web.routers.pages import router as pagesRouter
    from agentic_claims.web.routers.review import router as reviewRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    testApp.include_router(auditRouter)
    testApp.include_router(chatRouter)
    testApp.include_router(dashboardRouter)
    testApp.include_router(reviewRouter)
    testApp.include_router(pagesRouter)
    testApp.state.graph = MagicMock()

    emptyKpis = {"draft": 0, "pending": 0, "aiReviewed": 0, "autoApproved": 0, "escalated": 0, "rejected": 0}
    fakeClaimRow = {
        "id": 1, "claim_number": "CLM-0001", "employee_id": "EMP001",
        "status": "pending", "total_amount": 45.0, "currency": "SGD",
        "created_at": None, "intake_findings": {},
        "compliance_findings": None, "fraud_findings": None,
        "advisor_decision": None, "advisor_findings": None, "approved_by": None,
        "receipt_id": 1, "receipt_number": None, "merchant": "Test", "date": "2026-04-01",
        "receipt_amount": 45.0, "receipt_currency": "SGD", "image_path": None,
        "line_items": {}, "original_currency": None, "original_amount": None,
        "converted_amount_sgd": None, "display_name": "Test User",
    }
    emptyInsights = {"anomalyCount": 0, "costBenchmark": None}
    with patch("agentic_claims.web.routers.audit.getCurrentUser", return_value=_FAKE_USER):
        with patch("agentic_claims.web.routers.audit._fetchAllClaims", new=AsyncMock(return_value=[])):
            with patch("agentic_claims.web.routers.audit._fetchTimeline", new=AsyncMock(return_value=[])):
                with patch("agentic_claims.web.routers.audit._fetchInsights", new=AsyncMock(return_value=emptyInsights)):
                    with patch("agentic_claims.web.routers.audit._fetchClaimSummary", new=AsyncMock(return_value=None)):
                        with patch("agentic_claims.web.routers.dashboard.getCurrentUser", return_value=_FAKE_USER):
                            with patch("agentic_claims.web.routers.dashboard._queryKpis", new=AsyncMock(return_value=emptyKpis)):
                                with patch("agentic_claims.web.routers.dashboard._queryClaims", new=AsyncMock(return_value=[])):
                                    with patch("agentic_claims.web.routers.review.getCurrentUser", return_value=_FAKE_USER):
                                        with patch("agentic_claims.web.routers.review._fetchClaimDetail", new=AsyncMock(return_value=fakeClaimRow)):
                                            with patch("agentic_claims.web.routers.review._fetchSubmissionHistory", new=AsyncMock(return_value=None)):
                                                with patch("agentic_claims.web.routers.pages.getCurrentUser", return_value=_FAKE_USER):
                                                    with TestClient(testApp) as c:
                                                        yield c


def testChatPageReturns200(client):
    """GET / returns 200 with chat page content."""
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Expense Submission" in response.text


def testDashboardPageReturns200(client):
    """GET /dashboard returns 200 with dashboard page content."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Approver Dashboard" in response.text


def testAuditPageReturns200(client):
    """GET /audit/test-claim-123 returns 200 with audit page content."""
    response = client.get("/audit/test-claim-123")
    assert response.status_code == 200
    assert "Audit" in response.text


def testReviewPageReturns200(client):
    """GET /review/1 returns 200 with review page content."""
    response = client.get("/review/1")
    assert response.status_code == 200
    assert "Claim Review" in response.text


def testSessionCookieSetOnFirstVisit(client):
    """GET / sets agentic_session cookie."""
    response = client.get("/")
    assert response.status_code == 200
    cookies = response.cookies
    assert "agentic_session" in cookies


def testActivePageIndicatorChat(client):
    """GET / shows active indicator for chat nav item."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text-[#62fae3]" in response.text


def testActivePageIndicatorDashboard(client):
    """GET /dashboard shows active indicator for dashboard nav item."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text-[#62fae3]" in response.text


def test404ForUnknownRoute(client):
    """GET /nonexistent returns 404."""
    response = client.get("/nonexistent")
    assert response.status_code == 404
