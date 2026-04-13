"""Integration tests for the policy-exception justification flow (Plan 13-12 gap closure).

Covers UAT Gap 2: after user provides justification for a policy violation, the
agent must advance to submission — not re-emit the policy-check message verbatim.

Scope: tests the hook chain (postToolFlagSetter → preModelHook → postModelHook)
using state dicts. Does NOT exercise the full LLM — that's an E2E concern outside
this plan.

preModelHook return contract (verified via grep on 2026-04-12):
  keys: {"llm_input_messages": [SystemMessage | AIMessage | HumanMessage, ...]}
  The test asserts on the `llm_input_messages` list, NOT `messages` or `directive_messages`.
  If this contract changes, update the assertion key below.

Sources:
  - 13-DEBUG-policy-exception-loop.md H1 + F1 (primary fix)
  - 13-DEBUG-policy-exception-loop.md H2 + F2 (secondary fix — prompt gap)
  - 13-DEBUG-display-regression.md H3 + Fix C (consolidated into F1)
"""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter
from agentic_claims.agents.intake.hooks.preModelHook import preModelHook


@pytest.mark.asyncio
async def test_postJustificationTurnClearsPendingAndAdvances():
    """After user replies to justification askHuman:
      - F1: postToolFlagSetter must clear clarificationPending (unchanged)
      - D1': preModelHook MUST still inject the askHuman directive because
        the last ToolMessage is askHuman and claimSubmitted=False.

    Updated for D1' (screenshot #5 fix): the directive's purpose is to prevent
    plain-text questions — it does NOT block submitClaim, so its presence on
    the post-justification turn is safe. Without D1', prose re-asks after
    askHuman resume (Phase 1 meta-questions, etc.) fly under the radar.

    Source: 13-DEBUG-policy-exception-loop.md D1' (screenshot #5).
    """
    state = {
        "messages": [
            AIMessage(
                content="Policy check: This exceeds the lunch cap of SGD 20.00.",
                tool_calls=[
                    {"name": "askHuman", "args": {"question": "..."}, "id": "call_1"}
                ],
            ),
            ToolMessage(
                content="Meeting ran late; client follow-up required",
                tool_call_id="call_1",
                name="askHuman",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 2,
        "clarificationPending": True,   # stale from an earlier convertCurrency unsupported
        "unsupportedCurrencies": {"VND"},
        "validatorRetryCount": 0,
        "validatorEscalate": False,
        "claimSubmitted": False,
    }

    flagUpdates = await postToolFlagSetter(state)
    assert flagUpdates.get("clarificationPending") is False, (
        "F1: askHuman ToolMessage must clear pending. "
        f"Got flagUpdates={flagUpdates}"
    )

    merged = {**state, **flagUpdates}
    preHookResult = await preModelHook(merged)
    injectedMessages = preHookResult.get("llm_input_messages", [])

    # D1': directive MUST fire — askHuman is last tool, claim not submitted.
    clarificationDirectives = [
        m for m in injectedMessages
        if "A clarification is pending" in getattr(m, "content", "")
    ]
    assert len(clarificationDirectives) == 1, (
        "D1': preModelHook must inject askHuman directive after askHuman resume "
        "when claim is not yet submitted. "
        f"Got {len(clarificationDirectives)} directives."
    )


@pytest.mark.asyncio
async def test_postSubmissionAskHumanDoesNotInjectDirective():
    """Symmetric to above: once the claim is submitted, the D1' trigger must
    NOT fire for the post-submission 'Submit another receipt?' askHuman.
    The intake flow is over; injecting the directive would waste tokens and
    could mislead the model about the claim's state."""
    state = {
        "messages": [
            AIMessage(
                content="Claim CLAIM-001 submitted successfully.",
                tool_calls=[
                    {"name": "askHuman", "args": {"question": "Submit another?"}, "id": "call_s"}
                ],
            ),
            ToolMessage(
                content='{"response": "no"}',
                tool_call_id="call_s",
                name="askHuman",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 3,
        "clarificationPending": False,
        "unsupportedCurrencies": set(),
        "claimSubmitted": True,
    }
    preHookResult = await preModelHook(state)
    clarificationDirectives = [
        m for m in preHookResult.get("llm_input_messages", [])
        if "A clarification is pending" in getattr(m, "content", "")
    ]
    assert len(clarificationDirectives) == 0


@pytest.mark.asyncio
async def test_justificationTurnDoesNotTriggerValidatorEscalate():
    """After F1 fix, a plain-text policy-summary AIMessage on the justification
    turn must NOT trigger the postModelHook drift predicate (since pending is cleared).

    This guards against the B1-B3 cascade described in the debug doc.
    """
    from agentic_claims.agents.intake.hooks.postModelHook import postModelHook

    state = {
        "messages": [
            # Turn state just after flag clearing and a plain-text AIMessage (no tool_calls)
            AIMessage(content="Acknowledged — proceeding to submit your claim."),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 2,
        "clarificationPending": False,    # <-- cleared by the F1 fix in the previous step
        "unsupportedCurrencies": {"VND"},
        "validatorRetryCount": 0,
        "validatorEscalate": False,
    }

    result = await postModelHook(state)
    # Drift predicate (hasContent AND NOT hasToolCalls AND clarificationPending) must be False
    # because clarificationPending is False. Hook returns empty (no rewrite, no escalate).
    assert not result.get("validatorEscalate", False)
    # No RemoveMessage injected
    removeMessageCount = sum(
        1 for m in result.get("messages", []) if m.__class__.__name__ == "RemoveMessage"
    )
    assert removeMessageCount == 0
