"""Unit tests for the advisor agent node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage


def makeState(overrides: dict | None = None) -> dict:
    base = {
        "claimId": "test-advisor-001",
        "status": "submitted",
        "messages": [],
        "claimNumber": "CLAIM-007",
        "dbClaimId": 42,
        "extractedReceipt": {
            "fields": {
                "category": "meals",
                "merchant": "The Canteen",
                "totalAmount": 45.0,
                "totalAmountSgd": 45.0,
            }
        },
        "intakeFindings": {"employeeId": "1010736"},
        "complianceFindings": {
            "verdict": "pass",
            "violations": [],
            "summary": "Claim passes all policy checks.",
            "requiresReview": False,
            "requiresManagerApproval": False,
            "requiresDirectorApproval": False,
        },
        "fraudFindings": {
            "verdict": "legit",
            "flags": [],
            "summary": "No duplicates detected.",
        },
    }
    if overrides:
        base.update(overrides)
    return base


def makeAgentResult(decisionJson: str) -> dict:
    """Build a canned ainvoke result with the decision JSON in the last AIMessage."""
    return {
        "messages": [
            AIMessage(content="I will call updateClaimStatus now."),
            AIMessage(content=decisionJson),
        ]
    }


AUTO_APPROVE_JSON = json.dumps({
    "decision": "auto_approve",
    "reasoning": "Compliance pass + legit fraud check.",
    "citedClauses": [],
    "statusUpdated": True,
    "notificationsSent": ["claimant"],
    "summary": "Claim auto-approved.",
})

RETURN_CLAIMANT_JSON = json.dumps({
    "decision": "return_to_claimant",
    "reasoning": "Minor policy violations flagged.",
    "citedClauses": [],
    "statusUpdated": True,
    "notificationsSent": ["claimant"],
    "summary": "Claim returned to claimant for correction.",
})

ESCALATE_JSON = json.dumps({
    "decision": "escalate_to_reviewer",
    "reasoning": "Suspicious fraud flags require human review.",
    "citedClauses": [],
    "statusUpdated": True,
    "notificationsSent": ["claimant", "reviewer"],
    "summary": "Claim escalated for manual review.",
})


@pytest.mark.asyncio
async def testAdvisorAutoApproveCleanClaim():
    """Auto-approve routing for compliance pass + legit fraud verdict."""
    state = makeState()

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(return_value=makeAgentResult(AUTO_APPROVE_JSON))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    assert result["advisorDecision"] == "auto_approve"
    assert result["status"] == "approved"
    assert len(result["messages"]) == 1
    assert "AUTO-APPROVED" in result["messages"][0].content.upper()


@pytest.mark.asyncio
async def testAdvisorReturnToClaimantViolation():
    """Return-to-claimant routing for compliance fail with violations."""
    state = makeState({
        "complianceFindings": {
            "verdict": "fail",
            "violations": [{"field": "totalAmount", "severity": "minor"}],
            "summary": "Minor violation: slightly over limit.",
            "requiresReview": True,
            "requiresManagerApproval": False,
            "requiresDirectorApproval": False,
        }
    })

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(return_value=makeAgentResult(RETURN_CLAIMANT_JSON))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    assert result["advisorDecision"] == "return_to_claimant"
    assert result["status"] == "rejected"


@pytest.mark.asyncio
async def testAdvisorEscalateForFraud():
    """Escalation routing when fraud verdict is suspicious."""
    state = makeState({
        "fraudFindings": {
            "verdict": "suspicious",
            "flags": [{"type": "frequency_anomaly", "confidence": "medium"}],
            "summary": "High claim frequency.",
        }
    })

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(return_value=makeAgentResult(ESCALATE_JSON))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    assert result["advisorDecision"] == "escalate_to_reviewer"
    assert result["status"] == "escalated"


@pytest.mark.asyncio
async def testAdvisorDecisionFallbackEscalate():
    """Conservative escalate_to_reviewer fallback when agent output is unparseable."""
    state = makeState()

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(return_value={
        "messages": [AIMessage(content="I cannot determine the decision at this time.")]
    })

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    assert result["advisorDecision"] == "escalate_to_reviewer"
    assert result["status"] == "escalated"


@pytest.mark.asyncio
async def testAdvisorReadsDbClaimIdFromState():
    """dbClaimId is read directly from state, not from ToolMessage scanning."""
    state = makeState({"dbClaimId": 99})

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(return_value=makeAgentResult(AUTO_APPROVE_JSON))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mockMcp:
        from agentic_claims.agents.advisor.node import advisorNode

        await advisorNode(state)

    # The audit log MCP call should use claimId=99 from state
    mockMcp.assert_called_once()
    callKwargs = mockMcp.call_args.kwargs
    assert callKwargs["arguments"]["claimId"] == 99


@pytest.mark.asyncio
async def testAdvisorMessageHygiene():
    """Only the human-readable summary AIMessage is returned — no ReAct tool noise."""
    state = makeState()

    mockAgent = AsyncMock()
    # Agent returns 3 internal messages + the final decision JSON
    mockAgent.ainvoke = AsyncMock(return_value={
        "messages": [
            AIMessage(content="Checking compliance findings..."),
            ToolMessage(content='{"ok": true}', tool_call_id="tc1"),
            AIMessage(content="Now sending notification..."),
            AIMessage(content=AUTO_APPROVE_JSON),
        ]
    })

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Only 1 message in the returned state update — the summary
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], AIMessage)
    assert "Advisor Decision" in result["messages"][0].content
