import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


class _PostResult:
    def __init__(self, fired_controls=None):
        self.fired_controls = fired_controls or []


class _Critique:
    def __init__(self):
        self.concerns = ("Needs human confirmation.",)
        self.flags = ("confidence_gap",)
        self.confidence = 0.7


@pytest.mark.asyncio
async def test_group_c_writes_separate_governance_audit_and_overrides_status_to_escalated():
    state = {
        "claimId": "group-c-001",
        "dbClaimId": 501,
        "claimNumber": "CLAIM-501",
        "extractedReceipt": {"fields": {"merchant": "Cafe", "totalAmount": 12.5, "currency": "SGD"}},
        "intakeFindings": {"employeeId": "E-1"},
        "complianceFindings": {"verdict": "pass", "summary": "OK", "citedClauseIds": ["3.1"], "citedClauses": ["Section 3.1"]},
        "fraudFindings": {
            "verdict": "legit",
            "summary": "No issues",
            "governance": [
                {
                    "control": "B4",
                    "result": "concerns-found",
                    "reason": "llm-judge",
                    "details": {"concerns": ["Needs human confirmation."]},
                }
            ],
        },
    }

    decision_json = json.dumps({
        "decision": "auto_approve",
        "reasoning": "All clear.",
        "summary": "Approve.",
        "citedClauseIds": ["3.1"],
        "citedClauses": ["Section 3.1"],
    })

    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content=decision_json)]})

    mock_runtime = MagicMock()
    mock_runtime.post_model_check = AsyncMock(return_value=_PostResult(fired_controls=[]))
    mock_runtime.judge = AsyncMock(return_value=_Critique())

    with (
        patch("agentic_claims.agents.advisor.node._getAdvisorAgent", return_value=mock_agent),
        patch("agentic_claims.agents.advisor.node.mcpCallTool", new_callable=AsyncMock) as mock_mcp,
        patch("agentic_claims.core.graph.contentHookRuntime_background", new=mock_runtime),
    ):
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    assert result["advisorDecision"] == "auto_approve"
    assert result["status"] == "escalated"

    audit_calls = [c.kwargs["arguments"] for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "insertAuditLog"]
    advisor_audit = next(c for c in audit_calls if c["action"] == "advisor_decision")
    gov_audit = next(c for c in audit_calls if c["action"] == "governance_oversight")

    advisor_payload = json.loads(advisor_audit["newValue"])
    gov_payload = json.loads(gov_audit["newValue"])

    assert advisor_payload["decision"] == "auto_approve"
    assert gov_payload["decision"] == "require_human_review"
    assert gov_payload["governance_override"] is True

    update_call = next(c.kwargs["arguments"] for c in mock_mcp.call_args_list if c.kwargs.get("toolName") == "updateClaimStatus")
    assert update_call["newStatus"] == "escalated"
    assert update_call["advisorDecision"] == "auto_approve"
    assert update_call["advisorFindings"]["governanceOversight"]["decision"] == "require_human_review"
