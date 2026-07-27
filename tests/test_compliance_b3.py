"""Deterministic tests for B3 grounded-output validation on the compliance agent.

Proves the compliance downgrade behavior deterministically by mocking:
  - The LLM response (rawContent via buildGovernedAgentLlm → mock_llm)
  - The RAG MCP searchPolicies response (via mcpCallTool side_effect)
  - The contentHookRuntime_background (via patch)
  - The DB MCP audit log (via mcpCallTool side_effect)

Scenarios (2 cases):
  Case A — hallucinated citation: compliance verdict=pass but citedClauses
           contains a clause NOT in the retrieved RAG -> assert verdict
           downgraded to requires_review + B3 governance embed.
  Case B — clean compliance: citedClauses is a subset of retrieved RAG ->
           assert verdict NOT downgraded, no B3 governance embed.

Pattern follows tests/test_advisor_b3_downgrade.py and tests/test_compliance_agent.py.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_mock_fired_control(controlId="B3", result="grounding-failed", name="Output grounding"):
    return {
        "controlId": controlId,
        "name": name,
        "result": result,
        "entityTypes": None,
        "signalValue": None,
    }


def _make_mock_post_result(fired_controls=None):
    mock = MagicMock()
    mock.fired_controls = fired_controls or []
    return mock


def _mock_runtime_with_post(post_result):
    runtime = MagicMock()
    runtime.post_model_check = AsyncMock(return_value=post_result)
    return runtime


def makeState(overrides=None):
    base = {
        "claimId": "test-compliance-b3-001",
        "status": "pending",
        "messages": [],
        "claimNumber": "CLAIM-CB3-007",
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
        "violations": [],
        "currencyConversion": None,
    }
    if overrides:
        base.update(overrides)
    return base


# Retrieved RAG sections (what compliance actually got from searchPolicies)
RETRIEVED_POLICIES = [
    {"section": "Section 2.1", "category": "meals", "score": 0.9,
     "text": "Meal daily cap is SGD 100"},
    {"section": "Section 2.2", "category": "meals", "score": 0.85,
     "text": "Meal single transaction cap is SGD 75"},
]


# Compliance LLM output that CLEANLY cites retrieved clauses (no hallucination)
PASS_VERDICT_CLEAN_CITATIONS = json.dumps({
    "verdict": "pass",
    "violations": [],
    "citedClauses": ["Section 2.1", "Section 2.2"],  # ⊆ retrieved
    "requiresManagerApproval": False,
    "requiresDirectorApproval": False,
    "summary": "Claim passes all policy checks.",
    "requiresReview": False,
})

# Compliance LLM output that HALLUCINATES a clause (NOT in retrieved RAG)
PASS_VERDICT_HALLUCINATED = json.dumps({
    "verdict": "pass",
    "violations": [],
    "citedClauses": ["Section 99 (fake)", "Section 2.1"],  # "Section 99" not retrieved
    "requiresManagerApproval": False,
    "requiresDirectorApproval": False,
    "summary": "Claim passes all policy checks.",
    "requiresReview": False,
})


# ---------------------------------------------------------------------------
# Case A: hallucinated citation -> downgrade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_b3_case_a_hallucinated_citation_downgraded():
    """Case A: verdict='pass' but citedClauses contains a clause NOT in retrieved RAG.

    Inline consistency check fires:
      cited_clauses = {Section 99 (fake), Section 2.1}
      retrieved     = {Section 2.1, Section 2.2}
      Section 99 (fake) is in cited but NOT retrieved -> hallucinated citation
      -> grounding_failed = True

    Disposition:
      verdict pass -> requires_review (downgrade, never fail->pass)
      requiresReview=True
      complianceFindings.governance contains B3 entry
    """
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = PASS_VERDICT_HALLUCINATED
    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)
    # _default_params used for sdkParams logging
    mockLlm._default_params = {}

    mockRuntime = _mock_runtime_with_post(_make_mock_post_result(fired_controls=[]))

    # mcpCallTool call order in complianceNode:
    #   1. insertAuditLog (compliance.started audit entry)
    #   2. searchPolicies (RAG retrieval) -> RETRIEVED_POLICIES
    #   3. insertAuditLog (compliance_check audit entry after parsing)
    mockMcp = AsyncMock(side_effect=[
        {"ok": True},  # initial start audit
        RETRIEVED_POLICIES,  # searchPolicies
        {"ok": True},  # post-parsing audit
    ])

    with patch(
        "agentic_claims.agents.compliance.node.buildGovernedAgentLlm",
        return_value=mockLlm,
    ), patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new=mockMcp,
    ), patch(
        "agentic_claims.core.graph.contentHookRuntime_background",
        new=mockRuntime,
    ):
        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    findings = result["complianceFindings"]
    # Assert 1: verdict downgraded from "pass" -> "requires_review"
    assert findings["verdict"] == "requires_review", (
        f"Expected verdict downgraded to requires_review, got {findings['verdict']}"
    )
    # Assert 2: requiresReview=True
    assert findings.get("requiresReview") is True, (
        f"Expected requiresReview=True, got {findings.get('requiresReview')}"
    )
    # Assert 3: governance contains a B3 entry
    governance = findings.get("governance", [])
    assert any(
        g.get("control") == "B3" for g in governance
    ), f"Expected B3 in complianceFindings.governance, got: {governance}"


# ---------------------------------------------------------------------------
# Case B: clean compliance -> no downgrade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_b3_case_b_clean_not_downgraded():
    """Case B: citedClauses is a subset of retrieved -> NOT downgraded.

    Inline consistency check passes:
      cited_clauses = {Section 2.1, Section 2.2}
      retrieved     = {Section 2.1, Section 2.2, ...}
      cited ⊆ retrieved -> no hallucination
      -> grounding_failed = False

    No downgrade, no B3 governance embed.
    """
    state = makeState()

    mockLlmResponse = MagicMock()
    mockLlmResponse.content = PASS_VERDICT_CLEAN_CITATIONS
    mockLlm = AsyncMock()
    mockLlm.ainvoke = AsyncMock(return_value=mockLlmResponse)
    mockLlm._default_params = {}

    mockRuntime = _mock_runtime_with_post(_make_mock_post_result(fired_controls=[]))

    mockMcp = AsyncMock(side_effect=[RETRIEVED_POLICIES, {"ok": True}])

    with patch(
        "agentic_claims.agents.compliance.node.buildGovernedAgentLlm",
        return_value=mockLlm,
    ), patch(
        "agentic_claims.agents.compliance.node.mcpCallTool",
        new=mockMcp,
    ), patch(
        "agentic_claims.core.graph.contentHookRuntime_background",
        new=mockRuntime,
    ):
        from agentic_claims.agents.compliance.node import complianceNode

        result = await complianceNode(state)

    findings = result["complianceFindings"]
    # Assert 1: verdict NOT downgraded
    assert findings["verdict"] == "pass", (
        f"Expected verdict NOT downgraded, got {findings['verdict']}"
    )
    # Assert 2: requiresReview stays False (or None)
    assert not findings.get("requiresReview"), (
        f"Expected requiresReview to be falsy, got {findings.get('requiresReview')}"
    )
    # Assert 3: NO B3 in governance (or no governance at all)
    governance = findings.get("governance", [])
    b3_entries = [g for g in governance if g.get("control") == "B3"]
    assert len(b3_entries) == 0, (
        f"Clean compliance should have NO B3 entry, got: {b3_entries}"
    )
