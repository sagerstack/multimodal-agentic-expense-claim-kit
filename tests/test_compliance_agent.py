"""Unit tests for the compliance agent node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Minimal ClaimState dict for testing
def makeState(overrides: dict | None = None) -> dict:
    base = {
        "claimId": "test-claim-123",
        "status": "pending",
        "messages": [],
        "extractedReceipt": {
            "fields": {
                "category": "meals",
                "merchant": "The Canteen",
                "totalAmount": 45.0,
                "totalAmountSgd": 45.0,
            }
        },
        "violations": [],
        "intakeFindings": {"overrides": []},
        "currencyConversion": None,
        "dbClaimId": 7,
    }
    if overrides:
        base.update(overrides)
    return base


PASS_VERDICT_JSON = json.dumps({
    "verdict": "pass",
    "violations": [],
    "citedClauses": ["Section 2.1 of meals.md"],
    "requiresManagerApproval": False,
    "requiresDirectorApproval": False,
    "summary": "Claim passes all policy checks.",
    "requiresReview": False,
})

FAIL_VERDICT_JSON = json.dumps({
    "verdict": "fail",
    "violations": [
        {
            "field": "totalAmount",
            "value": "180.0",
            "limit": "SGD 100 per day",
            "clause": "Section 2.1: Daily meal cap is SGD 100",
            "severity": "major",
        }
    ],
    "citedClauses": ["Section 2.1 of meals.md"],
    "requiresManagerApproval": False,
    "requiresDirectorApproval": False,
    "summary": "Claim fails: daily meal cap exceeded.",
    "requiresReview": True,
})


@pytest.mark.asyncio
async def testCompliancePassCleanClaim():
    """Pass verdict returned for a clean, policy-compliant claim."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = PASS_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcp, patch(
        "agentic_claims.agents.compliance.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        # RAG returns policy snippets, audit log returns success
        mockMcp.side_effect = [
            [{"text": "Meal daily cap is SGD 100", "score": 0.9}],
            {"ok": True},
        ]

        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    assert "complianceFindings" in result
    assert result["complianceFindings"]["verdict"] == "pass"
    assert result["complianceFindings"]["violations"] == []
    assert "messages" in result
    assert len(result["messages"]) == 1
    assert "PASS" in result["messages"][0].content.upper()


@pytest.mark.asyncio
async def testComplianceFailViolation():
    """Fail verdict with violations returned when spending limit exceeded."""
    state = makeState({"extractedReceipt": {
        "fields": {
            "category": "meals",
            "merchant": "Fancy Restaurant",
            "totalAmount": 180.0,
            "totalAmountSgd": 180.0,
        }
    }})

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = FAIL_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcp, patch(
        "agentic_claims.agents.compliance.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        mockMcp.side_effect = [
            [{"text": "Meal daily cap is SGD 100", "score": 0.95}],
            {"ok": True},
        ]

        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    assert result["complianceFindings"]["verdict"] == "fail"
    assert len(result["complianceFindings"]["violations"]) > 0
    assert len(result["complianceFindings"]["citedClauses"]) > 0
    assert result["complianceFindings"]["requiresReview"] is True
    assert "FAIL" in result["messages"][0].content.upper()


@pytest.mark.asyncio
async def testComplianceParseErrorFallback():
    """Conservative fail/requiresReview fallback when LLM returns unparseable text."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = "Sorry, I cannot evaluate this claim right now."

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcp, patch(
        "agentic_claims.agents.compliance.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        mockMcp.side_effect = [
            [{"text": "Meal daily cap is SGD 100", "score": 0.8}],
            {"ok": True},
        ]

        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    findings = result["complianceFindings"]
    assert findings["verdict"] == "fail"
    assert findings["requiresReview"] is True
    assert "manual review" in findings["summary"].lower()


@pytest.mark.asyncio
async def testComplianceAuditLogWritten():
    """Audit log entry is written with action=compliance_check."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = PASS_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcp, patch(
        "agentic_claims.agents.compliance.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        mockMcp.side_effect = [
            {"ok": True},  # compliance_check_start audit entry
            [{"text": "Policy rules here", "score": 0.9}],
            {"ok": True},  # compliance_check audit entry
        ]

        from agentic_claims.agents.compliance.node import complianceNode

        await complianceNode(state)

    # Three MCP calls: start audit + RAG query + completion audit
    assert mockMcp.call_count == 3
    auditCall = mockMcp.call_args_list[2]
    callKwargs = auditCall.kwargs if auditCall.kwargs else auditCall[1]
    callArgs = auditCall.args if auditCall.args else auditCall[0]

    # Verify insertAuditLog was called
    toolName = callKwargs.get("toolName") or (callArgs[1] if len(callArgs) > 1 else None)
    assert toolName == "insertAuditLog"

    arguments = callKwargs.get("arguments") or (callArgs[2] if len(callArgs) > 2 else None)
    assert arguments["action"] == "compliance_check"
    assert arguments["claimId"] == 7


@pytest.mark.asyncio
async def testComplianceRagErrorProceedsWithEmptyContext():
    """Node proceeds with empty policy context when RAG MCP returns an error."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = PASS_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockMcp, patch(
        "agentic_claims.agents.compliance.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        # RAG returns error dict, audit log returns success
        mockMcp.side_effect = [
            {"error": "Qdrant unreachable"},
            {"ok": True},
        ]

        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    # Node should still complete — LLM was called with empty policy context
    assert "complianceFindings" in result
    assert mockLlm.ainvoke.called
