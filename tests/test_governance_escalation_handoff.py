"""Focused tests for the governance Escalate-to-reviewer application handoff."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from agentic_claims.agents.intake.nodes.humanEscalation import (
    _governanceEscalationReason,
    humanEscalationNode,
)
from agentic_claims.core import graph as graphModule
from agentic_claims.web.routers.chat import postMessage
from agentic_claims.web.sseHelpers import _buildGraphInput


def _submitClaimMessage(payload: object) -> ToolMessage:
    content = json.dumps(payload) if isinstance(payload, dict) else payload
    return ToolMessage(content=content, name="submitClaim", tool_call_id="submit-1")


def _governanceMarker(reason: str = "evidence-insufficient") -> dict:
    return {
        "error": reason,
        "decision": "Escalate",
        "reason": reason,
        "escalation": {"source": "governance", "reason": reason},
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "ordinary-tool-error"},
        {
            "decision": "Escalate",
            "reason": "evidence-insufficient",
            "escalation": {"source": "internal", "reason": "evidence-insufficient"},
        },
        {
            "decision": "Escalate",
            "reason": "attacker-chosen",
            "escalation": {"source": "governance", "reason": "attacker-chosen"},
        },
        {
            "decision": "Escalate",
            "reason": "rate-exceeded",
            "escalation": {"source": "governance", "reason": "exposure-exceeded"},
        },
    ],
)
def test_governanceMarkerRejectsArbitraryForgedUnknownAndMismatchedPayloads(payload):
    state = {"messages": [_submitClaimMessage(payload)]}
    assert _governanceEscalationReason(state) is None


def test_governanceMarkerUsesOnlyMostRecentSubmitClaimResult():
    state = {
        "messages": [
            _submitClaimMessage(_governanceMarker()),
            _submitClaimMessage({"error": "later ordinary error"}),
        ]
    }
    assert _governanceEscalationReason(state) is None


@pytest.mark.asyncio
async def test_governanceMarkerRoutesGraphDirectlyToHumanEscalation():
    markerMessage = _submitClaimMessage(_governanceMarker("rate-exceeded"))

    async def intakeNode(state):
        return {"messages": [markerMessage], "claimSubmitted": False}

    async def preIntakeValidator(state):
        return {}

    async def humanEscalation(state):
        return {"status": "escalated", "intakeFindings": {"routed": True}}

    settings = SimpleNamespace(intake_agent_mode="legacy")
    with (
        patch.object(graphModule, "_installGovernedMcpBoundary"),
        patch.object(graphModule, "getSettings", return_value=settings),
        patch.object(graphModule, "preIntakeValidator", preIntakeValidator),
        patch.object(graphModule, "intakeNode", intakeNode),
        patch.object(graphModule, "humanEscalationNode", humanEscalation),
        patch.object(
            graphModule,
            "postIntakeRouter",
            side_effect=AssertionError("normal router must not run for governance marker"),
        ),
    ):
        result = await graphModule.buildGraph().compile().ainvoke(
            {
                "claimId": "claim-route",
                "dbClaimId": 42,
                "status": "draft",
                "messages": [HumanMessage(content="submit")],
            }
        )

    assert result["status"] == "escalated"
    assert result["intakeFindings"]["routed"] is True


@pytest.mark.asyncio
async def test_governanceEscalationPersistsSourceReasonAndAdvisorMetadata():
    state = {
        "claimId": "claim-governance",
        "threadId": "thread-governance",
        "dbClaimId": 42,
        "status": "draft",
        "messages": [_submitClaimMessage(_governanceMarker("exposure-exceeded"))],
        "askHumanCount": 1,
        "unsupportedCurrencies": {"VND"},
        "intakeFindings": {"existing": True},
    }
    settings = SimpleNamespace(db_mcp_url="http://mcp-db:8000/mcp/")

    with (
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.getSettings",
            return_value=settings,
        ),
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.mcpCallTool",
            new=AsyncMock(return_value={"ok": True}),
        ) as mcpCall,
        patch("agentic_claims.agents.intake.nodes.humanEscalation.logEvent"),
    ):
        result = await humanEscalationNode(state)

    metadata = result["intakeFindings"]["escalationMetadata"]
    assert metadata["source"] == "governance"
    assert metadata["reason"] == "exposure-exceeded"
    assert result["intakeFindings"]["existing"] is True

    arguments = mcpCall.await_args.kwargs["arguments"]
    assert arguments["claimId"] == 42
    assert arguments["newStatus"] == "escalated"
    assert arguments["advisorDecision"] == "escalate_to_reviewer"
    assert arguments["advisorFindings"] == {"escalationMetadata": metadata}


@pytest.mark.parametrize(
    ("stateUpdates", "expectedReason"),
    [
        ({"validatorEscalate": True, "askHumanCount": 1}, "unsupportedScenario"),
        ({"validatorEscalate": False, "askHumanCount": 4}, "loopBound"),
    ],
)
@pytest.mark.asyncio
async def test_internalEscalationsPreserveExistingReasons(stateUpdates, expectedReason):
    state = {
        "claimId": "claim-internal",
        "threadId": "thread-internal",
        "dbClaimId": None,
        "status": "draft",
        "messages": [],
        "unsupportedCurrencies": set(),
        "intakeFindings": {},
        **stateUpdates,
    }
    settings = SimpleNamespace(db_mcp_url="http://mcp-db:8000/mcp/")

    with (
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.getSettings",
            return_value=settings,
        ),
        patch("agentic_claims.agents.intake.nodes.humanEscalation.logEvent"),
    ):
        result = await humanEscalationNode(state)

    metadata = result["intakeFindings"]["escalationMetadata"]
    assert metadata["source"] == "internal"
    assert metadata["reason"] == expectedReason


@pytest.mark.asyncio
async def test_draftDbClaimIdFlowsFromSessionQueuePayloadIntoClaimState():
    queue = SimpleNamespace(put=AsyncMock())
    request = SimpleNamespace(
        session={
            "thread_id": "thread-draft",
            "claim_id": "claim-draft",
            "employee_id": "EMP-42",
            "username": "employee",
        },
        app=SimpleNamespace(state=SimpleNamespace(graph=SimpleNamespace(aget_state=AsyncMock(return_value=None)))),
    )
    settings = SimpleNamespace(
        db_mcp_url="http://mcp-db:8000/mcp/",
        intake_agent_mode="legacy",
    )

    with (
        patch("agentic_claims.web.routers.chat.getSettings", return_value=settings),
        patch(
            "agentic_claims.web.routers.chat.mcpCallTool",
            new=AsyncMock(return_value={"id": 314}),
        ),
        patch("agentic_claims.web.routers.chat.getOrCreateQueue", return_value=queue),
        patch("agentic_claims.web.routers.chat.isPausedAtInterrupt", return_value=False),
        patch("agentic_claims.web.routers.chat.logEvent"),
    ):
        response = await postMessage(
            request,
            message="submit",
            receipt=None,
            button_value="",
        )

    assert response.status_code == 204
    queuedInput = queue.put.await_args.args[0]
    assert request.session["draft_claim_id"] == 314
    assert queuedInput["dbClaimId"] == 314

    claimState = _buildGraphInput(queuedInput)
    assert claimState["dbClaimId"] == 314
    claimState.update(
        {
            "threadId": "thread-draft",
            "validatorEscalate": True,
            "askHumanCount": 1,
            "unsupportedCurrencies": set(),
        }
    )
    with (
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.getSettings",
            return_value=settings,
        ),
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.mcpCallTool",
            new=AsyncMock(return_value={"ok": True}),
        ) as statusUpdate,
        patch("agentic_claims.agents.intake.nodes.humanEscalation.logEvent"),
    ):
        await humanEscalationNode(claimState)

    assert statusUpdate.await_args.kwargs["arguments"]["claimId"] == 314


def test_buildGraphInputPreservesAbsentDbClaimIdAsNone():
    state = _buildGraphInput({"claimId": "claim-no-draft", "message": "hello"})
    assert state["dbClaimId"] is None


@pytest.mark.asyncio
async def test_nodeContextStillCarriesIdentityDbClaimIdAndReceipt():
    receipt = {
        "fields": {"merchant": "Kopitiam"},
        "confidence": {"merchant": 0.98},
    }

    async def observe(state):
        return (
            graphModule.nodeIdentityVar.get(None),
            graphModule.dbClaimIdVar.get(None),
            graphModule.extractedReceiptVar.get(None),
        )

    wrapped = graphModule._withNodeIdentity("intake", observe)
    assert await wrapped({"dbClaimId": 42, "extractedReceipt": receipt}) == (
        "intake",
        42,
        receipt,
    )
    assert graphModule.nodeIdentityVar.get(None) is None
    assert graphModule.dbClaimIdVar.get(None) is None
    assert graphModule.extractedReceiptVar.get(None) is None
