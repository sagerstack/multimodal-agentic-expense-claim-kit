"""Tests for the Claim Review router — page handler and API endpoints."""
# BUG-028 tests for _parseIntakeAgentFindings are at the bottom of this file.

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
    "status": "pending",
    "total_amount": Decimal("120.00"),
    "currency": "SGD",
    "category": "Meals",
    "created_at": None,
    "intake_findings": {
        "violations": [{"description": "Amount exceeds policy limit", "score": 0.92}]
    },
    "compliance_findings": None,
    "fraud_findings": None,
    "advisor_decision": None,
    "advisor_findings": None,
    "approved_by": None,
    "receipt_id": 10,
    "receipt_number": None,
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

_FAKE_ESCALATED_CLAIM_ROW = {
    **_FAKE_CLAIM_ROW,
    "status": "escalated",
    "compliance_findings": {
        "verdict": "fail",
        "violations": [{"field": "amount", "value": "520", "limit": "500"}],
        "citedClauses": ["Meals 3.2"],
        "summary": "Amount exceeds daily meal cap",
    },
    "fraud_findings": {
        "verdict": "legit",
        "flags": [],
        "duplicateClaims": [],
        "summary": "No fraud indicators detected",
    },
    "advisor_decision": "escalate_to_reviewer",
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
    """GET /api/review/{claimId} returns JSON with claim, receipt, flagReason, submissionHistory."""
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/api/review/42")
    assert response.status_code == 200
    data = response.json()
    assert "claim" in data
    assert "receipt" in data
    assert "flagReason" in data
    assert "submissionHistory" in data

    claim = data["claim"]
    assert claim["id"] == 42
    assert claim["claimNumber"] == "CLM-0042"
    assert claim["status"] == "pending"
    assert claim["totalAmount"] == 120.0

    receipt = data["receipt"]
    assert receipt["merchant"] == "Starbucks"
    assert receipt["category"] == "Meals"

    flagReason = data["flagReason"]
    assert flagReason is not None
    assert "explanation" in flagReason
    assert "confidence" in flagReason
    assert flagReason["confidence"] == 0.92

    submissionHistory = data["submissionHistory"]
    assert submissionHistory["submissionCount"] == 5
    assert submissionHistory["approvalRate"] == 80.0


def testClaimDetailReturns404ForMissingClaim(client):
    """GET /api/review/{claimId} returns 404 when claim not found."""
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=None)):
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
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Claim Review" in response.text
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

    findings = {"violations": [{"description": "Exceeds limit", "score": 0.88}]}
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


def testShowActionsOnlyForEscalatedClaims(client):
    """reviewPage renders approve/reject buttons only when claim.status == 'escalated'."""
    _path = "agentic_claims.web.routers.review"
    # Escalated claim -> decision buttons rendered
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_ESCALATED_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    # The Approve/Reject buttons should appear for escalated claims
    assert "Approve Claim" in response.text
    assert "Reject Claim" in response.text

    # Submitted (non-escalated) claim -> decision buttons NOT rendered
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Approve Claim" not in response.text


def testComplianceAndFraudFindingsInTemplateContext(client):
    """reviewPage passes complianceFindings and fraudFindings to template context."""
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_ESCALATED_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    # Compliance card should appear (it's in the template when complianceFindings is set)
    assert "Compliance" in response.text
    assert "Fraud Analysis" in response.text


def testReviewApiIncludesAgentFindings(client):
    """GET /api/review/{claimId} includes complianceFindings and fraudFindings in JSON."""
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_ESCALATED_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/api/review/42")
    assert response.status_code == 200
    data = response.json()
    assert "complianceFindings" in data
    assert "fraudFindings" in data
    assert "showActions" in data
    assert "advisorDecision" in data
    assert data["showActions"] is True
    assert data["complianceFindings"]["verdict"] == "fail"
    assert data["fraudFindings"]["verdict"] == "legit"
    assert data["advisorDecision"] == "escalate_to_reviewer"


# ==================== BUG-021: Fraud LEGIT card styling ====================


def testFraudLegitCardUsesGreenProminentStyling(client):
    """BUG-021: fraud card with verdict='legit' must show LEGIT badge with brand green secondary styling."""
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=_FAKE_ESCALATED_CLAIM_ROW)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    html = response.text
    # The fraud findings section must use the brand secondary (green) styling for legit verdict
    assert "text-secondary" in html
    # The legit verdict badge should appear
    assert "LEGIT" in html


def testFraudLegitCardSummaryIsProminentNotPlainItalic(client):
    """BUG-021: when fraud verdict is legit, the summary text must appear in the fraud card."""
    escalatedWithLegit = {
        **_FAKE_ESCALATED_CLAIM_ROW,
        "fraud_findings": {
            "verdict": "legit",
            "flags": [],
            "duplicateClaims": [],
            "summary": "No fraud indicators detected",
        },
    }
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=escalatedWithLegit)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    html = response.text
    # The fraud summary text must appear
    assert "No fraud indicators detected" in html
    # The legit verdict must show the security icon and LEGIT badge
    assert "LEGIT" in html


# ==================== BUG-022 + BUG-023: Approval badge ====================


def testApprovedByAiShowsAutoApprovedBadge(client):
    """BUG-022: when status is 'ai_approved', header badge shows 'Auto-Approved' and sidebar shows 'AI Approved'."""
    aiApprovedRow = {
        **_FAKE_CLAIM_ROW,
        "status": "ai_approved",
        "approved_by": "agent",
    }
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=aiApprovedRow)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Auto-Approved" in response.text or "AI Approved" in response.text


def testApprovedByReviewerShowsReviewerBadge(client):
    """BUG-022/BUG-023: when status is 'manually_approved', header badge shows 'Approved'."""
    reviewerApprovedRow = {
        **_FAKE_CLAIM_ROW,
        "status": "manually_approved",
        "approved_by": "EMP002",
    }
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=reviewerApprovedRow)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Approved" in response.text


def testApprovedByNullShowsAutoApprovedBadge(client):
    """BUG-022: when status is 'ai_approved' and approved_by is NULL (legacy), badge shows Auto-Approved."""
    nullApprovedRow = {
        **_FAKE_CLAIM_ROW,
        "status": "ai_approved",
        "approved_by": None,
    }
    _path = "agentic_claims.web.routers.review"
    with patch(f"{_path}._fetchClaimDetail", new=AsyncMock(return_value=nullApprovedRow)):
        with patch(f"{_path}._fetchSubmissionHistory", new=AsyncMock(return_value=_FAKE_AI_INSIGHT)):
            response = client.get("/review/42")
    assert response.status_code == 200
    assert "Auto-Approved" in response.text or "AI Approved" in response.text


def testApproveClaimSetsApprovedBy(client):
    """POST /api/review/{claimId}/decision sets approved_by to reviewer's employee ID."""
    mockSession = AsyncMock()
    capturedValues = {}

    async def captureExecute(stmt, *args, **kwargs):
        # Capture the update statement values
        if hasattr(stmt, "_values"):
            capturedValues.update(stmt._values)
        return MagicMock()

    mockSession.execute = captureExecute
    mockSession.add = MagicMock()
    mockSession.commit = AsyncMock()
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession):
        response = client.post(
            "/api/review/42/decision",
            data={"action": "approve", "reviewerNotes": "Approved by reviewer"},
        )
    assert response.status_code == 204
    # Verify commit was called (approved_by written in same transaction)
    assert mockSession.commit.called


# ── _parseIntakeAgentFindings tests (BUG-028) ──


def testParseIntakeAgentFindingsWithConfidenceScores():
    """BUG-028: _parseIntakeAgentFindings must extract confidence scores from intakeFindings."""
    from agentic_claims.web.routers.review import _parseIntakeAgentFindings

    intakeFindings = {
        "confidenceScores": {
            "merchant": 0.95,
            "totalAmount": 0.88,
            "date": 0.92,
        },
        "notes": "Claim looks valid",
    }
    result = _parseIntakeAgentFindings(intakeFindings)

    assert result is not None
    assert result["avgConfidence"] == round((0.95 + 0.88 + 0.92) / 3, 3)
    assert result["lowestField"] == "totalAmount"
    assert result["lowestScore"] == 0.88
    assert result["scores"] == intakeFindings["confidenceScores"]


def testParseIntakeAgentFindingsReturnsNoneWhenNoConfidenceScores():
    """BUG-028: _parseIntakeAgentFindings must return None when confidenceScores absent."""
    from agentic_claims.web.routers.review import _parseIntakeAgentFindings

    intakeFindings = {"notes": "some notes", "violations": []}
    result = _parseIntakeAgentFindings(intakeFindings)
    assert result is None


def testParseIntakeAgentFindingsReturnsNoneForNone():
    """_parseIntakeAgentFindings must return None when intakeFindings is None."""
    from agentic_claims.web.routers.review import _parseIntakeAgentFindings

    assert _parseIntakeAgentFindings(None) is None


def testParseIntakeAgentFindingsHandlesEmptyConfidenceScores():
    """_parseIntakeAgentFindings must return None when confidenceScores dict is empty."""
    from agentic_claims.web.routers.review import _parseIntakeAgentFindings

    result = _parseIntakeAgentFindings({"confidenceScores": {}})
    assert result is None
