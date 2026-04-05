"""Tests for the Claim Review router — page handler and API endpoints."""

import json
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

_FAKE_CLAIM_ROW = {
    "id": 42,
    "claim_number": "CLM-0042",
    "employee_id": "EMP001",
    "status": "submitted",
    "total_amount": Decimal("120.00"),
    "currency": "SGD",
    "created_at": None,
    "intake_findings": {"violations": [{"description": "Amount exceeds policy limit", "score": 0.92}]},
    "receipt_id": 10,
    "merchant": "Starbucks",
    "date": "2026-04-01",
    "receipt_amount": Decimal("120.00"),
    "receipt_currency": "SGD",
    "image_path": None,
    "line_items": {"category": "Meals"},
    "original_currency": None,
    "original_amount": None,
    "converted_amount_sgd": None,
    "display_name": "Alice Tan",
}

_FAKE_AI_INSIGHT = {
    "submissionCount": 5,
    "approvalRate": 80.0,
    "employeeName": "Alice Tan",
}


@pytest.fixture
def client():
    """Test client with review router, mocked getCurrentUser as reviewer."""
    from agentic_claims.web.routers.review import router as reviewRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    testApp.include_router(reviewRouter)

    with patch("agentic_claims.web.routers.review.getCurrentUser", return_value=_REVIEWER_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


@pytest.fixture
def employeeClient():
    """Test client with non-reviewer user."""
    from agentic_claims.web.routers.review import router as reviewRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(reviewRouter)

    with patch("agentic_claims.web.routers.review.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


def testClaimDetailEndpointReturnsFullData(client):
    """GET /api/review/{claimId} returns JSON with claim, receipt, flagReason, aiInsight."""
    with patch("agentic_claims.web.routers.review._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_CLAIM_ROW)):
        with patch("agentic_claims.web.routers.review._fetchAiInsight", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/api/review/42")
    assert response.status_code == 200
    data = response.json()
    assert "claim" in data
    assert "receipt" in data
    assert "flagReason" in data
    assert "aiInsight" in data

    claim = data["claim"]
    assert claim["id"] == 42
    assert claim["claimNumber"] == "CLM-0042"
    assert claim["status"] == "submitted"
    assert claim["totalAmount"] == 120.0

    receipt = data["receipt"]
    assert receipt["merchant"] == "Starbucks"
    assert receipt["category"] == "Meals"

    flagReason = data["flagReason"]
    assert flagReason is not None
    assert "explanation" in flagReason
    assert "confidence" in flagReason
    assert flagReason["confidence"] == 0.92

    aiInsight = data["aiInsight"]
    assert aiInsight["submissionCount"] == 5
    assert aiInsight["approvalRate"] == 80.0


def testClaimDetailReturns404ForMissingClaim(client):
    """GET /api/review/{claimId} returns 404 when claim not found."""
    with patch("agentic_claims.web.routers.review._fetchClaimDetail", new=AsyncMock(return_value=None)):
        response = client.get("/api/review/999")
    assert response.status_code == 404


def testClaimDetailForbiddenForNonReviewer(employeeClient):
    """GET /api/review/{claimId} returns 403 for non-reviewer."""
    response = employeeClient.get("/api/review/42")
    assert response.status_code == 403


def testApproveClaimUpdatesStatusAndCreatesAuditLog(client):
    """POST /api/review/{claimId}/decision with action=approve commits status change."""
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=MagicMock())
    mockSession.add = MagicMock()
    mockSession.commit = AsyncMock()
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession):
        response = client.post(
            "/api/review/42/decision",
            data={"action": "approve", "reviewerNotes": "Looks good"},
        )
    assert response.status_code == 204
    assert response.headers.get("HX-Redirect") == "/dashboard"
    # Verify session.add was called (audit log entry)
    assert mockSession.add.called
    # Verify commit was called
    assert mockSession.commit.called


def testRejectClaimRequiresReason(client):
    """POST /api/review/{claimId}/decision with action=reject and no reason returns 422."""
    response = client.post(
        "/api/review/42/decision",
        data={"action": "reject", "rejectionReason": ""},
    )
    assert response.status_code == 422


def testRejectClaimWithInvalidReasonReturns422(client):
    """POST /api/review/{claimId}/decision with invalid rejectionReason returns 422."""
    response = client.post(
        "/api/review/42/decision",
        data={"action": "reject", "rejectionReason": "Made up reason"},
    )
    assert response.status_code == 422


def testRejectClaimWithValidReasonSucceeds(client):
    """POST /api/review/{claimId}/decision with action=reject and valid reason succeeds."""
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=MagicMock())
    mockSession.add = MagicMock()
    mockSession.commit = AsyncMock()
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession):
        response = client.post(
            "/api/review/42/decision",
            data={
                "action": "reject",
                "rejectionReason": "Policy violation",
                "reviewerNotes": "Exceeds meal policy cap",
            },
        )
    assert response.status_code == 204
    assert response.headers.get("HX-Redirect") == "/dashboard"
    assert mockSession.add.called


def testDecisionForbiddenForNonReviewer(employeeClient):
    """POST /api/review/{claimId}/decision returns 403 for non-reviewer."""
    response = employeeClient.post(
        "/api/review/42/decision",
        data={"action": "approve"},
    )
    assert response.status_code == 403


def testReceiptImageEndpointNoImage(client):
    """GET /api/review/{claimId}/receipt-image returns 404 when no image path stored."""
    mockSession = AsyncMock()
    mockResult = MagicMock()
    mockResult.scalar_one_or_none.return_value = None
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession):
        response = client.get("/api/review/42/receipt-image")
    assert response.status_code == 404


def testReceiptImageEndpointRedirectsToStaticUrl(client):
    """GET /api/review/{claimId}/receipt-image redirects when relative image path found."""
    mockSession = AsyncMock()
    mockResult = MagicMock()
    mockResult.scalar_one_or_none.return_value = "images/receipts/receipt.jpg"
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession):
        response = client.get("/api/review/42/receipt-image")
    assert response.status_code == 302
    assert "/static/" in response.headers["location"]


def testReviewPageReturns200WithClaimData(client):
    """GET /review/{claimId} renders HTML page with claim context."""
    with patch("agentic_claims.web.routers.review._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_CLAIM_ROW)):
        with patch("agentic_claims.web.routers.review._fetchAiInsight", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Review Flagged Claim" in response.text
    assert "CLM-0042" in response.text
    assert "Starbucks" in response.text


def testReviewPageRedirectsNonReviewer():
    """GET /review/{claimId} redirects non-reviewer to /."""
    from agentic_claims.web.routers.review import router as reviewRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(reviewRouter)

    with patch("agentic_claims.web.routers.review.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            response = c.get("/review/42")
    assert response.status_code == 302
    assert response.headers["location"] == "/"


def testReviewRouteNotInPagesRouter():
    """/review/{claimId} route no longer exists in pages.py router."""
    from agentic_claims.web.routers import pages
    routes = [r.path for r in pages.router.routes]
    assert "/review/{claimId}" not in routes


def testParseFlagReasonWithViolations():
    """_parseFlagReason extracts explanation and confidence from violations list."""
    from agentic_claims.web.routers.review import _parseFlagReason
    findings = {
        "violations": [{"description": "Exceeds limit", "score": 0.88}]
    }
    result = _parseFlagReason(findings)
    assert result is not None
    assert result["explanation"] == "Exceeds limit"
    assert result["confidence"] == 0.88


def testParseFlagReasonNullWhenEmpty():
    """_parseFlagReason returns None when no violations or explanation."""
    from agentic_claims.web.routers.review import _parseFlagReason
    assert _parseFlagReason({}) is None
    assert _parseFlagReason(None) is None
    assert _parseFlagReason({"violations": []}) is None
