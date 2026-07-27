"""Tests for B6 reviewer explanation surfacing via advisor audit payload.

Validates that when the governance runtime provides a reviewer-facing
explanation, advisor.node writes it into the advisor_decision audit_log
payload as `reasoning`, and also persists it into advisorFindings.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_agent_result(decision_json):
    return {
        "messages": [
            AIMessage(content="I will update now."),
            AIMessage(content=decision_json),
        ]
    }


class _PostResult:
    def __init__(self, reviewer_explanation: str | None):
        self.fired_controls = []
        # Prefer attribute names that our extractor checks first
        self.explanation_reviewer = reviewer_explanation


@pytest.mark.asyncio
async def test_b6_reviewer_explanation_written_to_advisor_audit_and_findings():
    # Arrange: minimal valid state
    state = {
        "claimId": "test-b6-001",
        "dbClaimId": 77,
        "claimNumber": "CLM-B6-001",
        "extractedReceipt": {"fields": {"merchant": "Cafe", "totalAmount": 12.5, "currency": "SGD"}},
        "intakeFindings": {"employeeId": "E-1"},
        "complianceFindings": {"verdict": "pass", "summary": "OK", "citedClauses": ["Meals 3.1"]},
        "fraudFindings": {"verdict": "legit", "summary": "No issues"},
    }

    decision_json = json.dumps({
        "decision": "escalate_to_reviewer",
        "reasoning": "LLM summary (will be overridden)",
        "summary": "Needs review",
        "citedClauses": ["Meals 3.1"],
    })

    # Mock agent and runtime
    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value=_make_agent_result(decision_json))
    mock_runtime = MagicMock()
    mock_runtime.post_model_check = AsyncMock(return_value=_PostResult("Please review receipt legibility and policy cap."))

    with (
        patch("agentic_claims.agents.advisor.node._getAdvisorAgent", return_value=mock_agent),
        patch("agentic_claims.agents.advisor.node.mcpCallTool", new_callable=AsyncMock) as mock_mcp,
        patch("agentic_claims.core.graph.contentHookRuntime_background", new=mock_runtime),
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Advisor should have executed and returned a valid decision
    assert result["advisorDecision"] in ("escalate_to_reviewer", "auto_approve", "return_to_claimant")

    # Find insertAuditLog call and inspect payload JSON
    insert_calls = [c for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "insertAuditLog"]
    assert insert_calls, "Expected an insertAuditLog call for advisor_decision"
    audit_args = insert_calls[-1].kwargs["arguments"]
    assert audit_args["action"] == "advisor_decision"
    audit_payload = json.loads(audit_args["newValue"]) if isinstance(audit_args["newValue"], str) else audit_args["newValue"]
    assert audit_payload.get("reasoning") == "Please review receipt legibility and policy cap.", (
        f"Audit payload must carry reviewer explanation, got: {audit_payload}"
    )

    # Find updateClaimStatus call and ensure advisorFindings carries reviewerExplanation
    update_calls = [c for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "updateClaimStatus"]
    assert update_calls, "Expected updateClaimStatus call"
    update_payload = update_calls[-1].kwargs["arguments"].get("advisorFindings", {})
    assert update_payload.get("reviewerExplanation") == "Please review receipt legibility and policy cap.", (
        f"advisorFindings should include reviewerExplanation, got: {update_payload}"
    )
