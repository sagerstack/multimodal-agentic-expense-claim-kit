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


class _FakeSink:
    def __init__(self):
        self.events = []
        self.failures = []

    async def append_custom(self, event):
        event = dict(event)
        event["entryId"] = "evt-1"
        event["entryHash"] = "hash-1"
        self.events.append(event)
        return event

    def record_failure_event(self, event):
        self.failures.append(event)


@pytest.fixture
def client():
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


def test_reviewer_decision_emits_canonical_governance_event(client):
    mockSession = AsyncMock()
    mockSession.execute = AsyncMock(return_value=MagicMock())
    mockSession.add = MagicMock()
    mockSession.commit = AsyncMock()
    mockSession.__aenter__ = AsyncMock(return_value=mockSession)
    mockSession.__aexit__ = AsyncMock(return_value=False)

    claim_row = {
        "advisor_decision": "escalate_to_reviewer",
        "advisor_findings": {
            "governanceOversight": {
                "decision": "require_human_review",
                "contract": {"contract_id": "ESC-123"},
            }
        },
    }
    sink = _FakeSink()

    with patch("agentic_claims.web.routers.review.getAsyncSession", return_value=mockSession), patch(
        "agentic_claims.web.routers.review._fetchClaimDetail",
        new=AsyncMock(return_value=claim_row),
    ), patch(
        "agentic_claims.core.graph.getGovernanceAuditSink",
        return_value=sink,
    ):
        response = client.post(
            "/api/review/42/decision",
            data={"action": "approve", "reviewerNotes": "Approved by reviewer"},
        )

    assert response.status_code == 204
    assert len(sink.events) == 1
    assert sink.events[0]["eventType"] == "reviewer_decision"
    added_audit_entry = mockSession.add.call_args.args[0]
    assert "governanceEventRef" in added_audit_entry.newValue
