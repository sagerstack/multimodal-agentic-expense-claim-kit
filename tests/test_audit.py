"""Tests for the Audit & Transparency Log router."""

from datetime import datetime, timezone
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

_NOW = datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc)


def _makeAuditRow(action: str, newValue: str, ts=None):
    row = MagicMock()
    row.action = action
    row.newValue = newValue
    row.timestamp = ts or _NOW
    return row


@pytest.fixture
def client():
    """Test client with audit router, mocked getCurrentUser as reviewer."""
    from agentic_claims.web.routers.audit import router as auditRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    testApp.include_router(auditRouter)

    with patch("agentic_claims.web.routers.audit.getCurrentUser", return_value=_REVIEWER_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


@pytest.fixture
def employeeClient():
    """Test client with non-reviewer user."""
    from agentic_claims.web.routers.audit import router as auditRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(auditRouter)

    with patch("agentic_claims.web.routers.audit.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


def testTimelineEndpointReturnsSteps(client):
    """GET /api/audit/{claimId}/timeline returns HTML partial with 4 steps."""
    auditRows = [
        _makeAuditRow("receipt_uploaded", "{}"),
        _makeAuditRow(
            "ai_extraction",
            '{"confidence": 0.95, "extracted": {"merchant": "Starbucks"}}',
        ),
        _makeAuditRow(
            "policy_check",
            '{"compliant": true, "policyRefs": [{"section": "Meals 3.2"}], "violations": []}',
        ),
        _makeAuditRow("claim_submitted", "{}"),
    ]
    mockScalars = MagicMock()
    mockScalars.all.return_value = auditRows
    mockResult = MagicMock()
    mockResult.scalars.return_value = mockScalars

    mockClaimRow = MagicMock()
    mockClaimRow.id = 1
    mockClaimRow.claimNumber = "CLM-001"
    mockClaimRow.status = "pending"
    mockClaimRow.totalAmount = Decimal("45.00")
    mockClaimRow.currency = "SGD"
    mockClaimRow.merchant = "Starbucks"
    mockClaimResult = MagicMock()
    mockClaimResult.first.return_value = mockClaimRow

    mockInsightRow = MagicMock()
    _insightData = {"total_amount": 45.0, "currency": "SGD", "intake_findings": {}}
    mockInsightRow.get = lambda k, d=None: _insightData.get(k, d)
    mockInsightMappings = MagicMock()
    mockInsightMappings.first.return_value = mockInsightRow
    mockInsightResult = MagicMock()
    mockInsightResult.mappings.return_value = mockInsightMappings

    mockAvgRow = MagicMock()
    mockAvgRow.avg = 50.0
    mockAvgResult = MagicMock()
    mockAvgResult.first.return_value = mockAvgRow

    callCount = 0

    def sessionFactory():
        class _CM:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, *args, **kwargs):
                nonlocal callCount
                callCount += 1
                if callCount == 1:
                    return mockResult  # audit_log query
                elif callCount == 2:
                    return mockClaimResult  # claim summary
                elif callCount == 3:
                    return mockInsightResult  # insights claim
                else:
                    return mockAvgResult  # avg query

        return _CM()

    with patch("agentic_claims.web.routers.audit.getAsyncSession", side_effect=sessionFactory):
        response = client.get("/api/audit/1/timeline")
    assert response.status_code == 200
    assert "Receipt Uploaded" in response.text
    assert "AI Extraction" in response.text
    assert "Policy Check" in response.text
    assert "Claim Submitted" in response.text


def testTimelineEndpointHandlesMissingSteps(client):
    """No audit entries returns all 8 steps as pending."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    steps = _buildTimelineSteps([])
    assert len(steps) == 8
    for step in steps:
        assert step["status"] == "pending"
    names = [s["name"] for s in steps]
    assert names == [
        "Receipt Uploaded",
        "AI Extraction",
        "Policy Check",
        "Claim Submitted",
        "Compliance Agent",
        "Fraud Checking Agent",
        "Advisory Agent",
        "Reviewer Decision",
    ]


def testInsightsEndpointReturnsAnomalyAndBenchmark(client):
    """GET /api/audit/{claimId}/insights returns anomalyCount and costBenchmark."""
    mockInsightRow = MagicMock()
    mockInsightRow.get = lambda k, d=None: {
        "total_amount": 120.0,
        "currency": "SGD",
        "intake_findings": {"violations": [{"description": "Exceeds limit"}]},
    }.get(k, d)
    mockMappings = MagicMock()
    mockMappings.first.return_value = mockInsightRow
    mockInsightResult = MagicMock()
    mockInsightResult.mappings.return_value = mockMappings

    mockAvgRow = MagicMock()
    mockAvgRow.avg = 80.0
    mockAvgResult = MagicMock()
    mockAvgResult.first.return_value = mockAvgRow

    callCount = 0

    def sessionFactory():
        class _CM:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def execute(self, *args, **kwargs):
                nonlocal callCount
                callCount += 1
                if callCount == 1:
                    return mockInsightResult
                return mockAvgResult

        return _CM()

    with patch("agentic_claims.web.routers.audit.getAsyncSession", side_effect=sessionFactory):
        response = client.get("/api/audit/1/insights")
    assert response.status_code == 200
    data = response.json()
    assert "anomalyCount" in data
    assert data["anomalyCount"] == 1
    assert "costBenchmark" in data
    assert data["costBenchmark"]["claimAmount"] == 120.0


def testInsightsEndpointForbiddenForNonReviewer(employeeClient):
    """GET /api/audit/{claimId}/insights returns 403 for non-reviewer."""
    response = employeeClient.get("/api/audit/1/insights")
    assert response.status_code == 403


def testClaimsListEndpointReturnsSortedList(client):
    """GET /api/audit/claims returns list ordered by created_at DESC."""
    row1 = MagicMock()
    row1.id = 2
    row1.claimNumber = "CLM-002"
    row1.status = "ai_approved"
    row1.totalAmount = Decimal("200.00")
    row1.currency = "SGD"
    row1.createdAt = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)

    row2 = MagicMock()
    row2.id = 1
    row2.claimNumber = "CLM-001"
    row2.status = "pending"
    row2.totalAmount = Decimal("45.00")
    row2.currency = "SGD"
    row2.createdAt = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)

    mockResult = MagicMock()
    mockResult.all.return_value = [row1, row2]
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=mockResult)
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    with patch("agentic_claims.web.routers.audit.getAsyncSession", return_value=mockSession):
        response = client.get("/api/audit/claims")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["claimNumber"] == "CLM-002"  # newest first


def testClaimsListForbiddenForNonReviewer(employeeClient):
    """GET /api/audit/claims returns 403 for non-reviewer."""
    response = employeeClient.get("/api/audit/claims")
    assert response.status_code == 403


def testAuditPageReturns200(client):
    """GET /audit/{claimId} renders HTML page."""
    _p = "agentic_claims.web.routers.audit"
    _emptyInsights = {"anomalyCount": 0, "costBenchmark": None}
    with patch(f"{_p}._fetchAllClaims", new=AsyncMock(return_value=[])):
        with patch(f"{_p}._fetchTimeline", new=AsyncMock(return_value=[])):
            with patch(f"{_p}._fetchInsights", new=AsyncMock(return_value=_emptyInsights)):
                with patch(f"{_p}._fetchClaimSummary", new=AsyncMock(return_value=None)):
                    response = client.get("/audit/1")
    assert response.status_code == 200
    assert "Audit Log" in response.text


def testAuditPageAllowsNonReviewerOwnClaims():
    """GET /audit/{claimId} allows non-reviewer to view their own claims."""
    from agentic_claims.web.routers.audit import router as auditRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(auditRouter)

    _emptyInsights = {"anomalyCount": 0, "costBenchmark": None}
    _p = "agentic_claims.web.routers.audit"
    with patch(f"{_p}.getCurrentUser", return_value=_EMPLOYEE_USER):
        with patch(f"{_p}._fetchAllClaims", new=AsyncMock(return_value=[])):
            with patch(f"{_p}._fetchTimeline", new=AsyncMock(return_value=[])):
                with patch(f"{_p}._fetchInsights", new=AsyncMock(return_value=_emptyInsights)):
                    with patch(f"{_p}._fetchClaimSummary", new=AsyncMock(return_value=None)):
                        with TestClient(testApp) as c:
                            response = c.get("/audit/1")
    assert response.status_code == 200


def testAuditRouteNotInPagesRouter():
    """/audit/{claimId} route no longer exists in pages.py router."""
    from agentic_claims.web.routers import pages

    routes = [r.path for r in pages.router.routes]
    assert "/audit/{claimId}" not in routes


def testBuildTimelineStepsWithConfidence():
    """_buildTimelineSteps correctly maps AI extraction confidence."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("ai_extraction", '{"confidence": 0.87}'),
    ]
    steps = _buildTimelineSteps(rows)
    aiStep = next(s for s in steps if s["name"] == "AI Extraction")
    assert aiStep["status"] == "completed"
    assert aiStep["confidence"] == 0.87


def testBuildTimelineStepsPolicyCompliant():
    """_buildTimelineSteps marks policy_check as compliant correctly."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("policy_check", '{"compliant": true, "policyRefs": [], "violations": []}'),
    ]
    steps = _buildTimelineSteps(rows)
    policyStep = next(s for s in steps if s["name"] == "Policy Check")
    assert policyStep["compliant"] is True
    assert policyStep["violations"] == []


def testBuildTimelineAllSevenSteps():
    """_buildTimelineSteps produces 8 ordered steps when all audit_log actions present."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("receipt_uploaded", "{}"),
        _makeAuditRow("ai_extraction", '{"confidence": 0.92}'),
        _makeAuditRow("policy_check", '{"compliant": true, "policyRefs": [], "violations": []}'),
        _makeAuditRow("claim_submitted", "{}"),
        _makeAuditRow(
            "compliance_check",
            '{"verdict": "pass", "violations": [], "citedClauses": ["Meals 3.1"], "summary": "All good"}',
        ),
        _makeAuditRow(
            "fraud_check",
            '{"verdict": "legit", "flags": [], "duplicateClaims": [], "summary": "No fraud detected"}',
        ),
        _makeAuditRow(
            "advisor_decision",
            '{"decision": "auto_approve", "reasoning": "Clean claim", "complianceSummary": "pass", "fraudSummary": "legit"}',
        ),
    ]
    steps = _buildTimelineSteps(rows)
    assert len(steps) == 8
    names = [s["name"] for s in steps]
    assert names == [
        "Receipt Uploaded",
        "AI Extraction",
        "Policy Check",
        "Claim Submitted",
        "Compliance Agent",
        "Fraud Checking Agent",
        "Advisory Agent",
        "Reviewer Decision",
    ]
    # All steps except Reviewer Decision should be completed (no reviewer audit row provided)
    for step in steps[:-1]:
        assert step["status"] == "completed"
    assert steps[-1]["status"] == "pending"


def testBuildTimelineComplianceCheckColorAndDetails():
    """_buildTimelineSteps sets correct color and details for compliance_check action."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    # Fail verdict should produce red color
    rowsFail = [
        _makeAuditRow(
            "compliance_check",
            '{"verdict": "fail", "violations": [{"field": "amount"}], "citedClauses": ["Meals 2.3"], "summary": "Exceeds cap"}',
        ),
    ]
    stepsFail = _buildTimelineSteps(rowsFail)
    compStep = next(s for s in stepsFail if s["name"] == "Compliance Agent")
    assert compStep["color"] == "red"
    assert compStep["complianceVerdict"] == "fail"
    assert compStep["violationCount"] == 1
    assert "Meals 2.3" in compStep["citedClauses"]
    assert compStep["complianceSummary"] == "Exceeds cap"

    # Pass verdict should produce green color
    rowsPass = [
        _makeAuditRow(
            "compliance_check",
            '{"verdict": "pass", "violations": [], "citedClauses": [], "summary": "OK"}',
        ),
    ]
    stepsPass = _buildTimelineSteps(rowsPass)
    compStepPass = next(s for s in stepsPass if s["name"] == "Compliance Agent")
    assert compStepPass["color"] == "green"


def testBuildTimelineAdvisorEscalatedUsesRed():
    """Advisory Agent escalate_to_reviewer uses red color, not pink."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow(
            "advisor_decision",
            '{"decision": "escalate_to_reviewer", "reasoning": "Needs review"}',
        ),
    ]
    steps = _buildTimelineSteps(rows)
    advisorStep = next(s for s in steps if s["name"] == "Advisory Agent")
    assert advisorStep["color"] == "red"
    assert advisorStep["advisorDecision"] == "escalate_to_reviewer"


def testBuildTimelineStatusChangeIgnored():
    """status_change action is not mapped to any timeline step."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("status_change", "escalated"),
    ]
    steps = _buildTimelineSteps(rows)
    # All steps should remain pending — status_change is not mapped
    for step in steps:
        assert step["status"] == "pending", f"{step['name']} should be pending"


def testBuildTimelineParallelFlagAlwaysFalse():
    """_buildTimelineSteps sets parallel=False for all steps (parallel badge removed)."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("compliance_check", '{"verdict": "pass", "violations": [], "summary": ""}'),
        _makeAuditRow("fraud_check", '{"verdict": "legit", "flags": [], "summary": ""}'),
    ]
    steps = _buildTimelineSteps(rows)
    for step in steps:
        assert step["parallel"] is False, f"{step['name']} should have parallel=False"


# ── BUG-017 tests ──


def testBuildTimelineStepsDictConfidenceWithScoreKey():
    """BUG-017: dict confidence with 'score' key is unwrapped to float."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("ai_extraction", '{"confidence": {"score": 0.844}}'),
    ]
    steps = _buildTimelineSteps(rows)
    aiStep = next(s for s in steps if s["name"] == "AI Extraction")
    assert aiStep["status"] == "completed"
    assert aiStep["confidence"] == pytest.approx(0.844)


def testBuildTimelineStepsDictConfidenceWithValueKey():
    """BUG-017: dict confidence with 'value' key is unwrapped to float."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("ai_extraction", '{"confidence": {"value": 0.91}}'),
    ]
    steps = _buildTimelineSteps(rows)
    aiStep = next(s for s in steps if s["name"] == "AI Extraction")
    assert aiStep["confidence"] == pytest.approx(0.91)


def testBuildTimelineStepsDictConfidenceWithNestedConfidenceKey():
    """BUG-017: dict confidence with nested 'confidence' key is unwrapped to float."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    rows = [
        _makeAuditRow("ai_extraction", '{"confidence": {"confidence": 0.76}}'),
    ]
    steps = _buildTimelineSteps(rows)
    aiStep = next(s for s in steps if s["name"] == "AI Extraction")
    assert aiStep["confidence"] == pytest.approx(0.76)


def testBuildTimelineStepsBadConfidenceTypeReturnsNone():
    """BUG-017: an unrecognisable confidence value gracefully becomes None."""
    from agentic_claims.web.routers.audit import _buildTimelineSteps

    # Store confidence as an unrecognisable type (list) — should not raise
    rows = [
        _makeAuditRow("ai_extraction", '{"confidence": [1, 2, 3]}'),
    ]
    steps = _buildTimelineSteps(rows)
    aiStep = next(s for s in steps if s["name"] == "AI Extraction")
    assert aiStep["confidence"] is None


def testAuditPageClaimsListNotEmptyWhenTimelineFails(client):
    """BUG-017: allClaims is still populated even when _fetchTimeline raises."""
    _p = "agentic_claims.web.routers.audit"
    mockClaims = [
        {
            "id": 5,
            "claimNumber": "CLM-005",
            "status": "pending",
            "totalAmount": 88.0,
            "currency": "SGD",
            "createdAt": "2026-04-05T10:00:00",
        }
    ]
    with patch(f"{_p}._fetchAllClaims", new=AsyncMock(return_value=mockClaims)):
        with patch(f"{_p}._fetchTimeline", side_effect=TypeError("float() arg must be a real number, not 'dict'")):
            with patch(f"{_p}._fetchInsights", new=AsyncMock(return_value={"anomalyCount": 0, "costBenchmark": None})):
                with patch(f"{_p}._fetchClaimSummary", new=AsyncMock(return_value=None)):
                    response = client.get("/audit/5")
    assert response.status_code == 200
    # The claims sidebar must include claim data — not be wiped to []
    assert "CLM-005" in response.text
