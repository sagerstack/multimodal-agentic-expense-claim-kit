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
        "overview": {"totalEvents": 12, "escalations": 3, "humanReviewRequired": 1, "systemFailures": 0, "integrityStatus": "Healthy"},
        "actionAuthorization": {"totalEvents": 5, "byDecision": {"Auto-Execute": 5}, "agentProfiles": [{"agent": "intake", "totalActions": 3, "uniqueTools": 2, "topAction": "insertAuditLog", "topActionCount": 2, "topActionPct": 66.7, "distribution": [{"tool": "insertAuditLog", "count": 2, "pct": 66.7}, {"tool": "insertClaim", "count": 1, "pct": 33.3}]}], "recentEvents": []},
        "modelContentSafeguards": {"totalEvents": 4, "actionableAlerts": 1, "topAgents": [{"label": "advisor", "count": 1}], "topSurfaces": [{"label": "model_output", "count": 2}], "topControls": [{"label": "B4", "count": 1}], "recentAlerts": []},
        "humanOversight": {"oversightEvents": 1, "reviewerDecisions": 0, "oversightByDecision": {"require_human_review": 1}, "reviewerByDecision": {}, "contracts": []},
        "auditIntegrityMonitoring": {"fileSummaries": [{"name": "audit.jsonl", "eventCount": 12, "ok": True, "issueCount": 0}], "failureEvents": [], "linkageWarnings": [], "reconstructionReadiness": {"claimsObserved": 1, "failureEvents": 0, "filesWithIssues": 0}},
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
    assert "Action Authorization" in response.text
    assert "Agent Activity Profile" in response.text
    assert "Action Distribution by Agent" in response.text
    assert "insertAuditLog" in response.text
    assert "is the most common action" in response.text
    assert "Model &amp; Content Safeguards" in response.text
    assert "Human Oversight" in response.text
    assert "Audit Integrity &amp; Monitoring" in response.text
    assert "CLAIM-224 · escalated" in response.text


def test_governance_page_redirects_non_reviewer(employeeClient):
    response = employeeClient.get("/governance")
    assert response.status_code == 302
    assert response.headers["location"] == "/"
