from unittest.mock import AsyncMock, patch

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
    from agentic_claims.web.routers.governance import router as governanceRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.mount("/static", StaticFiles(directory=str(projectRoot / "static")), name="static")
    testApp.include_router(governanceRouter)

    with patch("agentic_claims.web.routers.governance.getCurrentUser", return_value=_REVIEWER_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


@pytest.fixture
def employeeClient():
    from agentic_claims.web.routers.governance import router as governanceRouter

    testApp = FastAPI()
    testApp.add_middleware(
        SessionMiddleware,
        secret_key="test-secret-key",
        session_cookie="agentic_session",
    )
    testApp.include_router(governanceRouter)

    with patch("agentic_claims.web.routers.governance.getCurrentUser", return_value=_EMPLOYEE_USER):
        with TestClient(testApp, follow_redirects=False) as c:
            yield c


def _dashboard_payload():
    return {
        "filters": {"claim": "CLAIM-224", "correlationId": "", "dbClaimId": "202"},
        "scope": {"isFiltered": True, "label": "CLAIM-224 · escalated", "claim": {"claimNumber": "CLAIM-224"}},
        "overview": {"agentsMonitored": 3, "agentList": ["intake", "advisor", "governance_group_c"], "agentActivityTrend": {"days": [{"day": "2026-07-22", "points": [{"agent": "intake", "count": 1}, {"agent": "advisor", "count": 0}]}, {"day": "2026-07-23", "points": [{"agent": "intake", "count": 0}, {"agent": "advisor", "count": 0}]}, {"day": "2026-07-24", "points": [{"agent": "intake", "count": 0}, {"agent": "advisor", "count": 0}]}, {"day": "2026-07-25", "points": [{"agent": "intake", "count": 0}, {"agent": "advisor", "count": 0}]}, {"day": "2026-07-26", "points": [{"agent": "intake", "count": 0}, {"agent": "advisor", "count": 0}]}, {"day": "2026-07-27", "points": [{"agent": "intake", "count": 1}, {"agent": "advisor", "count": 1}]}, {"day": "2026-07-28", "points": [{"agent": "intake", "count": 2}, {"agent": "advisor", "count": 1}]}], "agents": ["intake", "advisor"], "maxCount": 2}, "agentAuthorizations": 5, "contentSafeguards": 4, "humanOversight": 1, "auditIntegrity": "Healthy", "auditIntegrityIssues": 0, "totalEvents": 12, "systemFailures": 0, "humanReviewRequired": 1},
        "actionAuthorization": {"totalEvents": 5, "byDecision": {"Auto-Execute": 4, "Escalate": 1}, "agentDistributions": [{"agent": "intake", "totalActions": 3, "distribution": [{"tool": "insertAuditLog", "count": 2, "pct": 66.7}, {"tool": "insertClaim", "count": 1, "pct": 33.3}]}, {"agent": "advisor", "totalActions": 2, "distribution": [{"tool": "updateClaimStatus", "count": 1, "pct": 50.0}, {"tool": "insertAuditLog", "count": 1, "pct": 50.0}]}], "blockedProfiles": [{"agent": "advisor", "blockedCalls": 1, "blockedTools": [{"tool": "updateClaimStatus", "count": 1}]}, {"agent": "intake", "blockedCalls": 0, "blockedTools": []}], "blockedTotal": 1, "agentsAffected": 1, "topAgent": {"agent": "intake", "totalActions": 3}, "topBlockedTool": {"label": "updateClaimStatus", "count": 1}},
        "modelContentSafeguards": {"totalEvents": 4, "actionableAlerts": 1, "b1": {"evaluations": 2, "passes": 2, "interventions": 0, "outcomes": [{"label": "allowed", "count": 2}]}, "b2": {"evaluations": 2, "passes": 1, "transformed": 1, "entityTypes": [{"label": "EMAIL_ADDRESS", "count": 1}]}, "b3": {"evaluations": 1, "passes": 1, "interventions": 0, "outcomes": [{"label": "grounded", "count": 1}]}, "b4": {"evaluations": 1, "passes": 0, "concerns": 1, "flags": [{"label": "inconsistency", "count": 1}]}, "b6": {"materialDecisions": 1, "explanationsPresent": 1, "explanationsMissing": 0}, "recentAlerts": [{"timestamp": "2026-07-28T05:53:01Z", "agent": "advisor", "contentType": "model_output", "result": "concerns-found", "claimId": 202}]},
        "humanOversight": {"oversightEvents": 1, "reviewerDecisions": 0, "oversightByDecision": {"require_human_review": 1}, "reviewerByDecision": {}, "contracts": [{"claimNumber": "CLAIM-224", "decision": "require_human_review", "contractId": "ESC-224", "status": "pending_review", "reasons": "advisor-requested-review"}], "contractStatuses": [{"label": "pending_review", "count": 1}], "reviewRequiredCount": 1, "openContracts": 1},
        "auditIntegrityMonitoring": {"fileSummaries": [{"name": "audit.jsonl", "eventCount": 12, "ok": True, "issueCount": 0}], "failureEvents": [], "failureComponents": [], "linkageWarnings": [], "warningTypes": [], "reconstructionReadiness": {"claimsObserved": 1, "failureEvents": 0, "filesWithIssues": 0}},
        "claimLinks": [{"id": 202, "claimNumber": "CLAIM-224", "status": "escalated", "amount": 19.36, "currency": "SGD", "displayName": "Alice Tan", "lastEventType": "oversight_governance"}],
        "hasAnyData": True,
    }


def test_governance_page_renders_theme_sections_and_filter_scope(client):
    with patch(
        "agentic_claims.web.routers.governance.buildGovernanceDashboard",
        new=AsyncMock(return_value=_dashboard_payload()),
    ):
        response = client.get("/governance?claim=CLAIM-224&dbClaimId=202")

    assert response.status_code == 200
    assert "Runtime Governance Dashboard" in response.text
    assert "Agents Monitored" in response.text
    assert "Agent Activity Trend" in response.text
    assert "Agent Authorizations" in response.text
    assert "Content Safeguards" in response.text
    assert "System Failures" in response.text
    assert "Action Authorization" in response.text
    assert "Action Distribution by Agent" in response.text
    assert "Agent vs Blocked Calls" in response.text
    assert "insertAuditLog" in response.text
    assert "Top Agent" in response.text
    assert "Blocked Total" in response.text
    assert "updateClaimStatus" in response.text
    assert "blocked calls" in response.text
    assert "Model &amp; Content Safeguards" in response.text
    assert "B1 — Input Attack Detection" in response.text
    assert "B2 — PII Minimization" in response.text
    assert "B3 — Grounding Validation" in response.text
    assert "B4 — Output Critique" in response.text
    assert "B6 — Decision Explanation Coverage" in response.text
    assert "Human Oversight" in response.text
    assert "Advisor vs Governance Decisions" in response.text
    assert "Review Contracts &amp; Outcomes" in response.text
    assert "Audit Integrity &amp; Monitoring" in response.text
    assert "Canonical Audit Health" in response.text
    assert "System Failures &amp; Linkage Warnings" in response.text
    assert "CLAIM-224 · escalated" in response.text


def test_governance_page_redirects_non_reviewer(employeeClient):
    response = employeeClient.get("/governance")
    assert response.status_code == 302
    assert response.headers["location"] == "/"
