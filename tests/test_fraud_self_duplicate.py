"""Regression test for BUG 1: self-duplicate false positive in fraud agent.

Ensures exact duplicate detection excludes the current claim row and only
returns true duplicates from history.
"""

from unittest.mock import AsyncMock, patch

import pytest


def _state():
    return {
        "claimId": "CLAIM-219-session",
        "dbClaimId": 219,
        "extractedReceipt": {
            "fields": {
                "merchant": "The Canteen",
                "date": "2026-04-10",
                "totalAmount": 20.0,
                "totalAmountSgd": 20.0,
            }
        },
        "intakeFindings": {"employeeId": "EMP001"},
    }


@pytest.mark.asyncio
async def test_fraud_exact_duplicate_excludes_current_row():
    state = _state()

    # DB returns the current claim row and one historical true duplicate
    current_row = {
        "id": 219,
        "claim_number": "CLAIM-219",
        "employee_id": "EMP001",
        "total_amount": 20.0,
        "merchant": "The Canteen",
        "receipt_date": "2026-04-10",
    }
    historical_dupe = {
        "id": 110,
        "claim_number": "CLAIM-110",
        "employee_id": "EMP001",
        "total_amount": 20.0,
        "merchant": "The Canteen",
        "receipt_date": "2026-03-28",
    }

    # exactDuplicateCheck (first DB query) returns both rows; other queries return empty
    side_effect_results = [[current_row, historical_dupe], [], []]

    with patch(
        "agentic_claims.agents.fraud.tools.queryClaimsHistory.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockDbMcp, patch(
        "agentic_claims.agents.fraud.node.mcpCallTool",
        new_callable=AsyncMock,
    ) as mockAuditMcp, patch(
        "agentic_claims.agents.fraud.node.buildGovernedAgentLlm",
        return_value=AsyncMock(ainvoke=AsyncMock()),
    ):
        mockDbMcp.side_effect = side_effect_results
        mockAuditMcp.return_value = {"ok": True}

        from agentic_claims.agents.fraud.node import fraudNode

        result = await fraudNode(state)

    # The agent should still classify as duplicate (based on historical_dupe),
    # but must NOT list the current claim number
    assert result["fraudFindings"]["verdict"] == "duplicate"
    dupes = result["fraudFindings"]["duplicateClaims"]
    assert "CLAIM-219" not in dupes
    assert "CLAIM-110" in dupes
