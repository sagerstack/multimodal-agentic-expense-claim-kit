"""Regression tests for BUG 2: advisor reviewerExplanation/ audit reasoning must be meaningful.

Cases:
1) Governance runtime offers a benign allow-only explanation (e.g., "Control B2: Allow.").
   Advisor reasoning is meaningful (e.g., duplicate/escalate). Persisted reviewerExplanation
   and audit reasoning must prefer the meaningful text, not the allow string.
2) When no governance downgrade reason exists, advisor reasoning/summary is used.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_agent_result(decision_json):
    return {
        "messages": [
            AIMessage(content="Calling tools..."),
            AIMessage(content=decision_json),
        ]
    }


class _PostResultAllow:
    def __init__(self):
        self.fired_controls = []
        self.explanation_reviewer = "Control B2: Allow."


@pytest.mark.asyncio
async def test_b6_filters_allow_and_uses_meaningful_reasoning():
    state = {
        "claimId": "test-b6-allow-filter",
        "dbClaimId": 501,
        "claimNumber": "CLM-501",
        "extractedReceipt": {"fields": {"merchant": "Cafe", "totalAmount": 12.5, "currency": "SGD"}},
        "intakeFindings": {"employeeId": "E-1"},
        "complianceFindings": {"verdict": "pass", "summary": "OK", "citedClauses": ["Meals 3.1"]},
        "fraudFindings": {"verdict": "duplicate", "summary": "Matches CLAIM-100"},
    }

    decision_json = json.dumps({
        "decision": "escalate_to_reviewer",
        "reasoning": "Exact duplicate detected for CLAIM-100.",
        "summary": "Escalating due to duplicate.",
        "citedClauses": ["Meals 3.1"],
    })

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value=_make_agent_result(decision_json))
    mock_runtime = MagicMock()
    mock_runtime.post_model_check = AsyncMock(return_value=_PostResultAllow())

    with (
        patch("agentic_claims.agents.advisor.node._getAdvisorAgent", return_value=mock_agent),
        patch("agentic_claims.agents.advisor.node.mcpCallTool", new_callable=AsyncMock) as mock_mcp,
        patch("agentic_claims.core.graph.contentHookRuntime_background", new=mock_runtime),
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Advisor executed; ensure reasoning selected is the meaningful one, not "Control B2: Allow."
    insert_calls = [c for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "insertAuditLog"]
    audit_args = insert_calls[-1].kwargs["arguments"]
    payload = json.loads(audit_args["newValue"]) if isinstance(audit_args["newValue"], str) else audit_args["newValue"]
    assert payload.get("reasoning") == "Exact duplicate detected for CLAIM-100.", payload

    update_calls = [c for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "updateClaimStatus"]
    advisor_findings = update_calls[-1].kwargs["arguments"].get("advisorFindings", {})
    assert advisor_findings.get("reviewerExplanation") == "Exact duplicate detected for CLAIM-100.", advisor_findings


@pytest.mark.asyncio
async def test_b6_falls_back_to_advisor_summary_when_no_downgrade_and_no_allow():
    state = {
        "claimId": "test-b6-fallback",
        "dbClaimId": 502,
        "claimNumber": "CLM-502",
        "extractedReceipt": {"fields": {"merchant": "Cafe", "totalAmount": 9.0, "currency": "SGD"}},
        "intakeFindings": {"employeeId": "E-2"},
        "complianceFindings": {"verdict": "pass", "summary": "OK", "citedClauses": ["Meals 3.1"]},
        "fraudFindings": {"verdict": "legit", "summary": "No issues"},
    }

    decision_json = json.dumps({
        "decision": "return_to_claimant",
        "reasoning": "Receipt image too blurry for verification.",
        "summary": "Please resubmit with a clearer image.",
    })

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value=_make_agent_result(decision_json))
    # No allow explanation from runtime
    mock_runtime = MagicMock(); mock_runtime.post_model_check = AsyncMock(return_value=MagicMock(fired_controls=[]))

    with (
        patch("agentic_claims.agents.advisor.node._getAdvisorAgent", return_value=mock_agent),
        patch("agentic_claims.agents.advisor.node.mcpCallTool", new_callable=AsyncMock) as mock_mcp,
        patch("agentic_claims.core.graph.contentHookRuntime_background", new=mock_runtime),
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        await advisorNode(state)

    # Ensure the audit payload reasoning uses advisor reasoning (meaningful) and not empty
    insert_calls = [c for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "insertAuditLog"]
    audit_args = insert_calls[-1].kwargs["arguments"]
    payload = json.loads(audit_args["newValue"]) if isinstance(audit_args["newValue"], str) else audit_args["newValue"]
    assert payload.get("reasoning") == "Receipt image too blurry for verification.", payload
