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
    """After user replies to justification askHuman, the next preModelHook call
    must NOT inject the 'ROUTING DIRECTIVE: A clarification is pending' message.

    Traces the state machine: previous turn set clarificationPending=True (VND
    unsupported); user supplied manual rate (askHuman resolved); later user
    replies to policy-exception justification (another askHuman) — at this point
    the pending directive must be gone so the LLM is free to emit submitClaim.
    """
    # Simulate end of justification turn: trailing ToolMessage is the askHuman result
    state = {
        "messages": [
            # Older turns condensed — we care about the trailing tool run
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
    }

    flagUpdates = await postToolFlagSetter(state)
    assert flagUpdates.get("clarificationPending") is False, (
        "F1: askHuman ToolMessage must clear pending. "
        f"Got flagUpdates={flagUpdates}"
    )

    # Apply the update (simulate LangGraph merge) then invoke preModelHook
    merged = {**state, **flagUpdates}
    preHookResult = await preModelHook(merged)
    injectedMessages = preHookResult.get("llm_input_messages", [])

    # The directive we DO NOT want to see in the next LLM call
    forbiddenSubstring = "A clarification is pending"
    for msg in injectedMessages:
        msgText = getattr(msg, "content", "")
        assert forbiddenSubstring not in msgText, (
            "preModelHook must not inject clarification-pending directive after "
            "the pending state has been resolved. "
            f"Offending message: {msgText!r}"
        )


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
