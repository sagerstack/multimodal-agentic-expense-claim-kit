"""Unit tests for the fraud agent node."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def makeState(overrides: dict | None = None) -> dict:
    base = {
        "claimId": "test-fraud-claim-001",
        "status": "pending",
        "messages": [],
        "extractedReceipt": {
            "fields": {
                "category": "meals",
                "merchant": "The Canteen",
                "date": "2026-04-06",
                "totalAmount": 45.0,
                "totalAmountSgd": 45.0,
            }
        },
        "intakeFindings": {"employeeId": "1010736"},
        "dbClaimId": 12,
    }
    if overrides:
        base.update(overrides)
    return base


LEGIT_VERDICT_JSON = json.dumps({
    "verdict": "legit",
    "flags": [],
    "duplicateClaims": [],
    "summary": "No duplicates or anomalies detected. Claim appears legitimate.",
})

SUSPICIOUS_VERDICT_JSON = json.dumps({
    "verdict": "suspicious",
    "flags": [
        {
            "type": "frequency_anomaly",
            "description": "5 claims from The Canteen in the last 30 days",
            "confidence": "medium",
            "relatedClaimNumber": None,
        }
    ],
    "duplicateClaims": [],
    "summary": "Suspicious: high claim frequency from same merchant.",
})


@pytest.mark.asyncio
async def testFraudLegitNoDuplicates():
    """Legit verdict returned when no duplicates or anomalies found."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = LEGIT_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockDbMcp, patch(
        "agentic_claims.agents.fraud.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockAuditMcp, patch(
        "agentic_claims.agents.fraud.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        # All 3 DB queries return empty (no history)
        mockDbMcp.return_value = []
        mockAuditMcp.return_value = {"ok": True}

        from agentic_claims.agents.fraud.node import fraudNode

        result = await fraudNode(state)

    assert "fraudFindings" in result
    assert result["fraudFindings"]["verdict"] == "legit"
    assert result["fraudFindings"]["flags"] == []
    assert result["fraudFindings"]["duplicateClaims"] == []
    assert "messages" in result
    assert "LEGIT" in result["messages"][0].content.upper()


@pytest.mark.asyncio
async def testFraudExactDuplicateShortCircuit():
    """Exact duplicate detection bypasses LLM call entirely."""
    state = makeState()

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock()

    duplicateRow = {
        "id": 5,
        "claim_number": "CLAIM-005",
        "employee_id": "1010736",
        "status": "ai_approved",
        "total_amount": "45.00",
        "merchant": "The Canteen",
        "receipt_date": "2026-04-06",
    }

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockDbMcp, patch(
        "agentic_claims.agents.fraud.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockAuditMcp, patch(
        "agentic_claims.agents.fraud.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        # First call (exactDuplicateCheck) returns a match; others return empty
        mockDbMcp.side_effect = [[duplicateRow], [], []]
        mockAuditMcp.return_value = {"ok": True}

        from agentic_claims.agents.fraud.node import fraudNode

        result = await fraudNode(state)

    assert result["fraudFindings"]["verdict"] == "duplicate"
    assert len(result["fraudFindings"]["flags"]) > 0
    assert result["fraudFindings"]["flags"][0]["type"] == "duplicate"
    assert "CLAIM-005" in result["fraudFindings"]["duplicateClaims"]
    assert "DUPLICATE" in result["messages"][0].content.upper()
    # LLM must NOT have been called
    mockLlm.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def testFraudSuspiciousFrequencyAnomaly():
    """Suspicious verdict with frequency_anomaly flag from LLM reasoning."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = SUSPICIOUS_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    recentClaims = [
        {"claim_number": f"CLAIM-{i:03d}", "merchant": "The Canteen", "total_amount": "40.00"}
        for i in range(5)
    ]

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockDbMcp, patch(
        "agentic_claims.agents.fraud.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockAuditMcp, patch(
        "agentic_claims.agents.fraud.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        # No exact duplicate, but many recent claims
        mockDbMcp.side_effect = [[], recentClaims, []]
        mockAuditMcp.return_value = {"ok": True}

        from agentic_claims.agents.fraud.node import fraudNode

        result = await fraudNode(state)

    assert result["fraudFindings"]["verdict"] == "suspicious"
    assert len(result["fraudFindings"]["flags"]) > 0
    assert any(f["type"] == "frequency_anomaly" for f in result["fraudFindings"]["flags"])


@pytest.mark.asyncio
async def testFraudAuditLogWritten():
    """Audit log entry written with action=fraud_check and correct claimId."""
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = LEGIT_VERDICT_JSON

    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockDbMcp, patch(
        "agentic_claims.agents.fraud.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockAuditMcp, patch(
        "agentic_claims.agents.fraud.node.buildAgentLlm",
        return_value=mockLlm,
    ):
        mockDbMcp.return_value = []
        mockAuditMcp.return_value = {"ok": True}

        from agentic_claims.agents.fraud.node import fraudNode

        await fraudNode(state)

    # Two calls: fraud_check_start + fraud_check completion audit
    assert mockAuditMcp.call_count == 2
    # Find the completion audit call (not the start entry)
    completionCall = next(
        c for c in mockAuditMcp.call_args_list
        if c.kwargs["arguments"].get("action") == "fraud_check"
    )
    arguments = completionCall.kwargs["arguments"]
    assert arguments["action"] == "fraud_check"
    assert arguments["claimId"] == 12
    assert arguments["actor"] == "fraud_agent"


@pytest.mark.asyncio
async def testFraudSanitizePreventsInjection():
    """_sanitize escapes single quotes to prevent SQL injection."""
    from agentic_claims.agents.fraud.tools.queryClaimsHistory import _sanitize

    # Standard name with apostrophe
    assert _sanitize("O'Reilly") == "O''Reilly"

    # Classic injection attempt
    result = _sanitize("'; DROP TABLE claims; --")
    assert "''" in result
    assert "'" not in result.replace("''", "")
