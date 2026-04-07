"""Unit tests for the advisor agent node."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage


def makeState(overrides: dict | None = None) -> dict:
    base = {
        "claimId": "test-advisor-001",
        "status": "pending",
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
    assert result["status"] == "ai_approved"
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
    assert result["status"] == "ai_rejected"


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

    # Three MCP calls: start audit entry + insertAuditLog + updateClaimStatus
    assert mockMcp.call_count == 3
    # First call is advisor_decision_start audit entry
    startCall = mockMcp.call_args_list[0].kwargs
    assert startCall["arguments"]["claimId"] == 99
    assert startCall["toolName"] == "insertAuditLog"
    assert startCall["arguments"]["action"] == "advisor_decision_start"
    # Second call is insertAuditLog (advisor_decision)
    secondCall = mockMcp.call_args_list[1].kwargs
    assert secondCall["arguments"]["claimId"] == 99
    assert secondCall["toolName"] == "insertAuditLog"
    # Third call is updateClaimStatus with approvedBy="agent"
    thirdCall = mockMcp.call_args_list[2].kwargs
    assert thirdCall["arguments"]["claimId"] == 99
    assert thirdCall["toolName"] == "updateClaimStatus"
    assert thirdCall["arguments"]["approvedBy"] == "agent"


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


# ---------------------------------------------------------------------------
# BUG-019: advisor error recovery tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testAdvisorNodeSilentFailureRecovery():
    """BUG-019: unhandled exception in agent.ainvoke must NOT leave claim in pending.

    advisorNode must catch the exception, escalate the claim to 'escalated',
    write an advisor_decision audit entry with reason 'advisor_error', and
    return a valid state update instead of propagating the exception.
    """
    state = makeState()

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(side_effect=RuntimeError("Unexpected network timeout"))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mockMcp:
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Must return a valid state update — not raise
    assert result["advisorDecision"] == "escalate_to_reviewer"
    assert result["status"] == "escalated"
    assert len(result["messages"]) == 1

    # Must still attempt to persist status change (updateClaimStatus call)
    mcpCalls = mockMcp.call_args_list
    toolNames = [c.kwargs["toolName"] for c in mcpCalls]
    assert "updateClaimStatus" in toolNames


@pytest.mark.asyncio
async def testAdvisorNodeErrorWritesAuditLog():
    """BUG-019: advisor error recovery writes an advisor_decision audit log entry."""
    state = makeState({"dbClaimId": 77})

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(side_effect=ValueError("LLM response malformed"))

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

    mcpCalls = mockMcp.call_args_list
    toolNames = [c.kwargs["toolName"] for c in mcpCalls]
    # insertAuditLog must be called with advisor_decision action (not just the _start entry)
    assert "insertAuditLog" in toolNames
    auditCall = next(
        c for c in mcpCalls
        if c.kwargs["toolName"] == "insertAuditLog"
        and c.kwargs["arguments"].get("action") == "advisor_decision"
    )
    assert auditCall.kwargs["arguments"]["action"] == "advisor_decision"
    auditPayload = json.loads(auditCall.kwargs["arguments"]["newValue"])
    assert auditPayload.get("decision") == "escalate_to_reviewer"


@pytest.mark.asyncio
async def testAdvisorNodeErrorWithNoDbClaimIdDoesNotCallMcp():
    """BUG-019: if dbClaimId is missing, advisor error recovery skips MCP calls gracefully."""
    state = makeState({"dbClaimId": None})

    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(side_effect=RuntimeError("timeout"))

    with patch(
        "agentic_claims.agents.advisor.node._getAdvisorAgent",
        return_value=mockAgent,
    ), patch(
        "agentic_claims.agents.advisor.node.mcpCallTool",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mockMcp:
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Valid state update, no MCP calls (dbClaimId is None)
    assert result["status"] == "escalated"
    assert mockMcp.call_count == 0
