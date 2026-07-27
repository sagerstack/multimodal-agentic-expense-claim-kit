"""Tests for B3 grounded-output downgrade logic in the advisor agent node.

Proves the downgrade behavior deterministically by mocking the LLM/agent
plus the contentHookRuntime_background. We control:
  - What decision the advisor makes
  - What B3 controls fire from the GroundingValidator (via post_model_check)
Then assert: decision downgraded to escalate_to_reviewer, B3 governance
embedded in advisorFindings, updateClaimStatus called with escalate_to_reviewer
(NOT ai_approved), reasoning includes "[Governance B3]".

Scenarios (3 cases):
  Case A — ungrounded auto_approve (decision=auto_approve, compliance=fail) →
           inline consistency check fires → downgrade to escalate_to_reviewer
  Case B — hallucinated citation (citedClauses not in compliance.citedClauses) →
           GroundingValidator fires B3 grounding-failed → downgrade
  Case C — legit auto_approve (all verified, amounts matching, valid citations) →
           no downgrade, no B3 governance embed
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_mock_fired_control(controlId="B3", result="grounding-failed", name="Output grounding"):
    """Build a mock fired_control dict for B3 governance."""
    return {
        "controlId": controlId,
        "name": name,
        "result": result,
        "entityTypes": None,
        "signalValue": None,
    }


def _make_mock_post_result(fired_controls=None):
    """Build a mock ContentHookResult-like object for post_model_check return."""
    mock = MagicMock()
    mock.fired_controls = fired_controls or []
    return mock


def _mock_runtime_with_post(post_result):
    """Build a mock for contentHookRuntime_background where .post_model_check returns post_result."""
    runtime = MagicMock()
    runtime.post_model_check = AsyncMock(return_value=post_result)
    return runtime


def make_state(overrides=None):
    """Base advisor state — happy path (compliance=pass, fraud=legit)."""
    base = {
        "claimId": "test-b3-001",
        "status": "pending",
        "messages": [],
        "claimNumber": "CLAIM-B3-007",
        "dbClaimId": 42,
        "extractedReceipt": {
            "fields": {
                "category": "meals",
                "merchant": "The Canteen",
                "totalAmount": 45.0,
                "totalAmountSgd": 45.0,
                "date": "2025-01-15",
                "currency": "SGD",
            }
        },
        "intakeFindings": {"employeeId": "1010736"},
        "complianceFindings": {
            "verdict": "pass",
            "violations": [],
            "citedClauses": ["Policy 3.1", "Section 4.2"],
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


def _make_agent_result(decision_json):
    """Build a canned ainvoke result with the decision JSON in the last AIMessage."""
    return {
        "messages": [
            AIMessage(content="I will call updateClaimStatus now."),
            AIMessage(content=decision_json),
        ]
    }


# Auto-approve decision — valid case (compliance=pass, fraud=legit)
AUTO_APPROVE_LEGIT_JSON = json.dumps({
    "decision": "auto_approve",
    "reasoning": "Compliance pass + legit fraud check.",
    "citedClauses": ["Policy 3.1"],  # ⊆ compliance.citedClauses
    "statusUpdated": True,
    "notificationsSent": ["claimant"],
    "summary": "Claim auto-approved.",
})

# Auto-approve WITH compliance=fail — ungrounded decision (Case A)
AUTO_APPROVE_UNGROUNDED_JSON = json.dumps({
    "decision": "auto_approve",
    "reasoning": "I think this is fine.",
    "citedClauses": ["Policy 3.1"],
    "statusUpdated": True,
    "notificationsSent": ["claimant"],
    "summary": "Claim auto-approved.",
})

# Auto-approve with hallucinated citation — cites clause NOT in compliance.citedClauses (Case B)
AUTO_APPROVE_HALLUCINATED_JSON = json.dumps({
    "decision": "auto_approve",
    "reasoning": "Section 99 (fake) clearly allows this.",
    "citedClauses": ["Section 99 (fake)"],  # NOT in compliance.citedClauses
    "statusUpdated": True,
    "notificationsSent": ["claimant"],
    "summary": "Claim auto-approved.",
})


def _patch_advisor_node(
    mock_agent_result,
    mock_post_result,
):
    """Patch _getAdvisorAgent, mcpCallTool, contentHookRuntime_background for advisorNode tests."""
    mock_agent = AsyncMock()
    mock_agent.ainvoke = AsyncMock(return_value=_make_agent_result(mock_agent_result))
    mock_runtime = _mock_runtime_with_post(mock_post_result)
    return (
        patch("agentic_claims.agents.advisor.node._getAdvisorAgent", return_value=mock_agent),
        patch("agentic_claims.agents.advisor.node.mcpCallTool", new_callable=AsyncMock, return_value={"ok": True}),
        # Patch contentHookRuntime_background where advisor does the lazy import
        patch("agentic_claims.core.graph.contentHookRuntime_background", new=mock_runtime),
    )


# ---------------------------------------------------------------------------
# Case A: ungrounded auto_approve — inline consistency check fires
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_case_a_ungrounded_auto_approve_downgraded():
    """Case A: advisor decides auto_approve + compliance=fail → MUST downgrade.

    Simulates an ungrounded advisor decision: LLM hallucinates auto_approve
    despite compliance=fail. The inline decision-consistency check fires.

    Asserts:
      - result.advisorDecision == "escalate_to_reviewer"
      - result.status == "escalated" (NOT "ai_approved")
      - reasoning field includes "[Governance B3]"
      - updateClaimStatus MCP call receives escalate_to_reviewer
      - advisorFindings governance contains B3 entry
    """
    state = make_state({
        "complianceFindings": {
            "verdict": "fail",  # ← triggers inline consistency check failure
            "violations": [{"field": "totalAmount", "severity": "major"}],
            "citedClauses": [],
            "summary": "Major violation.",
            "requiresReview": True,
        },
        "fraudFindings": {
            "verdict": "clean",
            "flags": [],
            "summary": "No issues.",
        },
    })

    # Post-check returns no fired controls (GroundingValidator passes field checks;
    # the inline check is what catches the bad decision)
    mock_post_result = _make_mock_post_result(fired_controls=[])

    agent_patch, mcp_patch, runtime_patch = _patch_advisor_node(
        mock_agent_result=AUTO_APPROVE_UNGROUNDED_JSON,
        mock_post_result=mock_post_result,
    )

    with agent_patch, mcp_patch as mock_mcp, runtime_patch:
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Assert 1: decision downgraded
    assert result["advisorDecision"] == "escalate_to_reviewer", (
        f"Expected escalate_to_reviewer, got {result['advisorDecision']}"
    )

    # Assert 2: status NOT ai_approved
    assert result["status"] != "ai_approved", (
        f"Status must NOT be ai_approved (would mean downgrade failed), got {result['status']}"
    )
    assert result["status"] == "escalated", (
        f"Expected status=escalated, got {result['status']}"
    )

    # Assert 3: updateClaimStatus received escalate_to_reviewer (not auto_approve / not approved)
    update_calls = [
        c for c in mock_mcp.call_args_list
        if c.kwargs.get("toolName") == "updateClaimStatus"
    ]
    assert len(update_calls) == 1, f"Expected 1 updateClaimStatus call, got {len(update_calls)}"
    update_call = update_calls[0].kwargs
    assert update_call["arguments"]["advisorDecision"] == "escalate_to_reviewer", (
        f"updateClaimStatus should receive escalate_to_reviewer, "
        f"got {update_call['arguments']['advisorDecision']}"
    )
    assert update_call["arguments"]["approvedBy"] != "agent", (
        f"approvedBy must NOT be 'agent' (would mean persisted as approved), "
        f"got {update_call['arguments']['approvedBy']}"
    )

    # Assert 4: advisorFindings.reasoning includes "[Governance B3]"
    advisor_findings = update_call["arguments"]["advisorFindings"]
    assert "[Governance B3]" in advisor_findings.get("reasoning", ""), (
        f"advisorFindings.reasoning must include '[Governance B3]', "
        f"got: {advisor_findings.get('reasoning', '')[:200]}"
    )

    # Assert 5: advisorFindings.governance contains B3 entry
    governance_list = advisor_findings.get("governance", [])
    assert any(
        g.get("control") == "B3" for g in governance_list
    ), f"advisorFindings.governance must contain a B3 entry, got: {governance_list}"


# ---------------------------------------------------------------------------
# Case B: hallucinated citation — GroundingValidator fires B3 grounding-failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_case_b_hallucinated_citation_grounding_validator_fires():
    """Case B: advisor cites a clause NOT in compliance.citedClauses → GroundingValidator fires.

    Inline consistency check passes (compliance=pass, fraud=clean, decision=auto_approve).
    But advisor cites "Section 99 (fake)" which is NOT in compliance.citedClauses.
    We mock post_model_check to fire B3 grounding-failed (simulating GroundingValidator detection).

    Asserts:
      - decision downgraded to escalate_to_reviewer
      - B3 governance embedded in advisorFindings
      - updateClaimStatus receives escalate_to_reviewer
    """
    state = make_state({
        "complianceFindings": {
            "verdict": "pass",
            "violations": [],
            "citedClauses": ["Policy 3.1"],  # "Section 99 (fake)" NOT in this list
            "summary": "Pass.",
            "requiresReview": False,
        },
        "fraudFindings": {
            "verdict": "clean",
            "flags": [],
            "summary": "No issues.",
        },
    })

    # Mock GroundingValidator firing B3 grounding-failed (cited_clauses ⊄ rag_clauses)
    mock_post_result = _make_mock_post_result(
        fired_controls=[_make_mock_fired_control(
            controlId="B3", result="grounding-failed", name="Output grounding",
        )],
    )

    agent_patch, mcp_patch, runtime_patch = _patch_advisor_node(
        mock_agent_result=AUTO_APPROVE_HALLUCINATED_JSON,
        mock_post_result=mock_post_result,
    )

    with agent_patch, mcp_patch as mock_mcp, runtime_patch:
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Assert 1: decision downgraded because GroundingValidator fired B3
    assert result["advisorDecision"] == "escalate_to_reviewer", (
        f"Expected downgrade to escalate_to_reviewer (B3 fired), "
        f"got {result['advisorDecision']}"
    )

    # Assert 2: status NOT ai_approved
    assert result["status"] != "ai_approved", (
        f"Status must NOT be ai_approved, got {result['status']}"
    )

    # Assert 3: updateClaimStatus receives escalate_to_reviewer
    update_calls = [
        c for c in mock_mcp.call_args_list
        if c.kwargs.get("toolName") == "updateClaimStatus"
    ]
    assert len(update_calls) == 1
    update_call = update_calls[0].kwargs
    assert update_call["arguments"]["advisorDecision"] == "escalate_to_reviewer"

    # Assert 4: advisorFindings.governance contains B3 entry
    governance_list = update_call["arguments"]["advisorFindings"].get("governance", [])
    b3_entries = [g for g in governance_list if g.get("control") == "B3"]
    assert len(b3_entries) >= 1, (
        f"Expected B3 entry in advisorFindings.governance, got: {governance_list}"
    )


# ---------------------------------------------------------------------------
# Case C: legit auto_approve — no downgrade, no governance embed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_b3_case_c_legit_auto_approve_not_downgraded():
    """Case C: advisor decides auto_approve with everything verified → NO downgrade.

    Compliance=pass, fraud=legit, citedClauses ⊆ compliance.citedClauses,
    amounts match. GroundingValidator returns no fired controls.

    Asserts:
      - decision stays "auto_approve" (NOT downgraded)
      - status == "ai_approved"
      - updateClaimStatus receives auto_approve + approvedBy="agent"
      - advisorFindings.governance is empty/absent (or no B3 entry)
    """
    state = make_state()  # defaults: compliance=pass, fraud=legit, valid citations

    # GroundingValidator passes (no fired controls)
    mock_post_result = _make_mock_post_result(fired_controls=[])

    agent_patch, mcp_patch, runtime_patch = _patch_advisor_node(
        mock_agent_result=AUTO_APPROVE_LEGIT_JSON,
        mock_post_result=mock_post_result,
    )

    with agent_patch, mcp_patch as mock_mcp, runtime_patch:
        from agentic_claims.agents.advisor.node import advisorNode

        result = await advisorNode(state)

    # Assert 1: decision NOT downgraded
    assert result["advisorDecision"] == "auto_approve", (
        f"Expected decision to stay auto_approve (no downgrade), "
        f"got {result['advisorDecision']}"
    )

    # Assert 2: status ai_approved
    assert result["status"] == "ai_approved", (
        f"Expected status=ai_approved, got {result['status']}"
    )

    # Assert 3: updateClaimStatus receives auto_approve + approvedBy="agent"
    update_calls = [
        c for c in mock_mcp.call_args_list
        if c.kwargs.get("toolName") == "updateClaimStatus"
    ]
    assert len(update_calls) == 1
    update_call = update_calls[0].kwargs
    assert update_call["arguments"]["advisorDecision"] == "auto_approve"
    assert update_call["arguments"]["approvedBy"] == "agent"
    assert update_call["arguments"]["newStatus"] == "ai_approved"

    # Assert 4: advisorFindings.governance does NOT contain B3 entry
    governance_list = update_call["arguments"]["advisorFindings"].get("governance", [])
    b3_entries = [g for g in governance_list if g.get("control") == "B3"]
    assert len(b3_entries) == 0, (
        f"Expected NO B3 entry for legit approval, got: {b3_entries}"
    )

    # Assert 5: reasoning should NOT include "[Governance B3]" (no override)
    reasoning = update_call["arguments"]["advisorFindings"].get("reasoning", "")
    assert "[Governance B3]" not in reasoning, (
        f"Legit approval reasoning must NOT have '[Governance B3]': {reasoning[:200]}"
    )
