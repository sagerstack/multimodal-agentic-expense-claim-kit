"""Tests for postToolFlagSetter — RED phase (13-05 TDD).

Tests the post-tool hook that scans ToolMessages and derives Phase 13
routing state flags from their contents.

Sources:
  - 13-05-PLAN.md must_haves (truths + artifacts)
  - 13-CONTEXT.md "Hook architecture — directive injection"
  - 13-02-SUMMARY.md (ClaimState field definitions)
"""

import json
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter


# ---------------------------------------------------------------------------
# convertCurrency unsupported path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterDetectsUnsupportedCurrency():
    """convertCurrency ToolMessage with {supported: false} → unsupportedCurrencies + clarificationPending."""
    toolMsg = ToolMessage(
        name="convertCurrency",
        content=json.dumps({"supported": False, "currency": "VND", "error": "unsupported", "provider": "frankfurter"}),
        tool_call_id="tc-001",
    )
    state = {
        "claimId": "claim-abc",
        "threadId": "thread-xyz",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    result = await postToolFlagSetter(state)

    assert "VND" in result.get("unsupportedCurrencies", set())
    assert result.get("clarificationPending") is True


@pytest.mark.asyncio
async def testPostToolFlagSetterIgnoresSupportedCurrency():
    """convertCurrency ToolMessage with {supported: true} → no flags set."""
    toolMsg = ToolMessage(
        name="convertCurrency",
        content=json.dumps({"supported": True, "convertedAmount": 100.0, "rate": 1.35}),
        tool_call_id="tc-002",
    )
    state = {
        "claimId": "claim-abc",
        "threadId": "thread-xyz",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    result = await postToolFlagSetter(state)

    assert not result.get("unsupportedCurrencies")
    assert not result.get("clarificationPending")


# ---------------------------------------------------------------------------
# askHuman increment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterIncrementsAskHumanCount():
    """askHuman ToolMessage → askHumanCount incremented by 1."""
    toolMsg = ToolMessage(
        name="askHuman",
        content=json.dumps({"response": "Yes, the rate is 25000"}),
        tool_call_id="tc-003",
    )
    state = {
        "claimId": "claim-abc",
        "threadId": "thread-xyz",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 2,
    }
    result = await postToolFlagSetter(state)

    assert result.get("askHumanCount") == 3


@pytest.mark.asyncio
async def testPostToolFlagSetterIncrementsFromZero():
    """askHuman ToolMessage with no existing count starts at 1."""
    toolMsg = ToolMessage(
        name="askHuman",
        content=json.dumps({"response": "USD"}),
        tool_call_id="tc-004",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), toolMsg],
    }
    result = await postToolFlagSetter(state)

    assert result.get("askHumanCount") == 1


# ---------------------------------------------------------------------------
# critical tool error (status="error")
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterEscalatesOnToolStatusError():
    """ToolMessage with status='error' → validatorEscalate: True."""
    toolMsg = ToolMessage(
        name="extractReceiptFields",
        content="VLM call failed: service unavailable",
        tool_call_id="tc-005",
        status="error",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    result = await postToolFlagSetter(state)

    assert result.get("validatorEscalate") is True


# ---------------------------------------------------------------------------
# no-op when no ToolMessages at tail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterReturnsEmptyWhenNoTrailingToolMessages():
    """No ToolMessages at tail → empty dict (no side effects)."""
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="Here is my receipt"), AIMessage(content="I will extract it")],
        "askHumanCount": 0,
    }
    result = await postToolFlagSetter(state)

    assert result == {}


@pytest.mark.asyncio
async def testPostToolFlagSetterReturnsEmptyOnEmptyMessages():
    """Empty messages list → empty dict."""
    state = {"claimId": "claim-abc", "messages": [], "askHumanCount": 0}
    result = await postToolFlagSetter(state)

    assert result == {}


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterIsIdempotentForUnsupportedCurrency():
    """Calling twice with the same state returns the same unsupportedCurrencies set."""
    toolMsg = ToolMessage(
        name="convertCurrency",
        content=json.dumps({"supported": False, "currency": "VND"}),
        tool_call_id="tc-006",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    result1 = await postToolFlagSetter(state)
    result2 = await postToolFlagSetter(state)

    assert result1.get("unsupportedCurrencies") == result2.get("unsupportedCurrencies")
    assert result1.get("clarificationPending") == result2.get("clarificationPending")


# ---------------------------------------------------------------------------
# multiple ToolMessages in same turn (e.g. convertCurrency + askHuman)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterHandlesMultipleToolMessagesInOneTurn():
    """Multiple ToolMessages at tail — all flags derived correctly."""
    unsupportedMsg = ToolMessage(
        name="convertCurrency",
        content=json.dumps({"supported": False, "currency": "THB"}),
        tool_call_id="tc-007a",
    )
    askHumanMsg = ToolMessage(
        name="askHuman",
        content=json.dumps({"response": "30"}),
        tool_call_id="tc-007b",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), unsupportedMsg, askHumanMsg],
        "askHumanCount": 1,
    }
    result = await postToolFlagSetter(state)

    assert "THB" in result.get("unsupportedCurrencies", set())
    assert result.get("clarificationPending") is True
    assert result.get("askHumanCount") == 2


# ---------------------------------------------------------------------------
# logEvent emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testPostToolFlagSetterEmitsLogEventOnUnsupportedCurrency():
    """logEvent is called with intake.hook.post_tool.flag_set on flag-set."""
    toolMsg = ToolMessage(
        name="convertCurrency",
        content=json.dumps({"supported": False, "currency": "IDR"}),
        tool_call_id="tc-008",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    with patch("agentic_claims.agents.intake.hooks.postToolFlagSetter.logEvent") as mockLog:
        await postToolFlagSetter(state)
        callArgs = [call.args[1] for call in mockLog.call_args_list]
        assert "intake.hook.post_tool.flag_set" in callArgs


# ---------------------------------------------------------------------------
# F1: clarificationPending clear-on-askHuman (Plan 13-12 gap closure)
# Source: 13-DEBUG-policy-exception-loop.md F1; 13-DEBUG-display-regression.md Fix C
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postToolFlagSetterClearsClarificationPendingOnAskHumanResume():
    """F1: When an askHuman ToolMessage lands in the trailing run AND
    clarificationPending is True, the hook must write clarificationPending=False.

    Source: 13-DEBUG-policy-exception-loop.md F1 (H1 root cause fix).
    Source: 13-DEBUG-display-regression.md "Fix C" (consolidated here).
    """
    state = {
        "messages": [
            # Prior AIMessage with askHuman tool_call omitted (only trailing tool run matters)
            ToolMessage(
                content="User says: rate is 1 VND = 0.00005 SGD",
                tool_call_id="call_ask_1",
                name="askHuman",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 0,
        "clarificationPending": True,   # set earlier by a convertCurrency unsupported turn
        "unsupportedCurrencies": {"VND"},
    }
    result = await postToolFlagSetter(state)

    assert result.get("clarificationPending") is False, (
        "askHuman ToolMessage must resolve the pending clarification flag. "
        f"Got: {result}"
    )
    assert result.get("askHumanCount") == 1  # existing behavior preserved


@pytest.mark.asyncio
async def test_postToolFlagSetterDoesNotClearClarificationOnConvertCurrencyRetry():
    """F1 edge: convertCurrency retry should NOT clear a pending clarification.
    Only askHuman (a user answer) clears it. convertCurrency resetting the flag
    would create a false 'resolved' state when it's actually another unsupported hit.
    """
    state = {
        "messages": [
            ToolMessage(
                content='{"supported": false, "currency": "IDR"}',
                tool_call_id="call_conv_2",
                name="convertCurrency",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 0,
        "clarificationPending": True,
        "unsupportedCurrencies": {"VND"},
    }
    result = await postToolFlagSetter(state)
    # New unsupported currency detected — flag stays True (or is re-set True).
    assert result.get("clarificationPending") is True
    assert "IDR" in result.get("unsupportedCurrencies", set())


@pytest.mark.asyncio
async def test_postToolFlagSetterClearClarificationIdempotent():
    """Running the clear-case twice produces the same output (idempotency contract)."""
    state = {
        "messages": [
            ToolMessage(
                content="justification text",
                tool_call_id="call_ask_2",
                name="askHuman",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 2,
        "clarificationPending": True,
        "unsupportedCurrencies": set(),
    }
    r1 = await postToolFlagSetter(state)
    r2 = await postToolFlagSetter(state)
    assert r1.get("clarificationPending") == r2.get("clarificationPending") is False


@pytest.mark.asyncio
async def test_postToolFlagSetterAskHumanNoOpWhenAlreadyClear():
    """If clarificationPending is already False and an askHuman ToolMessage lands,
    the clear is a no-op (don't add clarificationPending key to updates just to write False)."""
    state = {
        "messages": [
            ToolMessage(
                content="ok",
                tool_call_id="call_ask_3",
                name="askHuman",
            ),
        ],
        "claimId": "c1",
        "threadId": "t1",
        "askHumanCount": 0,
        "clarificationPending": False,   # already clear
        "unsupportedCurrencies": set(),
    }
    result = await postToolFlagSetter(state)
    # Either the key is absent, or it is False. Both are semantically identical for
    # last-write-wins bool, but the minimal-update contract prefers absence.
    assert result.get("clarificationPending", False) is False


# ---------------------------------------------------------------------------
# F3: set clarificationPending after searchPolicies so drift detection fires
# for policy-exception path (Plan 13 Bug 2 fix)
# Source: 13-DEBUG-policy-exception-loop.md F3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postToolFlagSetterSetsClarificationOnSearchPolicies():
    """F3: searchPolicies ToolMessage → clarificationPending=True.

    Rationale: after a policy search the agent typically needs to either
    confirm with the user (compliant path: 'does this look correct?') or
    elicit a justification (violation path). Both require askHuman. If the
    LLM emits the question as plain text instead of calling askHuman, the
    existing preModelHook drift detection (which reads clarificationPending)
    can rewrite the turn. Without this flag set the drift detection never
    fires and the agent loops.

    Source: 13-DEBUG-policy-exception-loop.md F3.
    """
    toolMsg = ToolMessage(
        name="searchPolicies",
        content=json.dumps([
            {"text": "Meals cap SGD 50/person", "section": "2.1", "score": 0.82}
        ]),
        tool_call_id="tc-sp-1",
    )
    state = {
        "claimId": "claim-abc",
        "threadId": "thread-xyz",
        "messages": [AIMessage(content=""), toolMsg],
        "askHumanCount": 0,
    }
    result = await postToolFlagSetter(state)

    assert result.get("clarificationPending") is True, (
        f"searchPolicies ToolMessage must set clarificationPending=True. Got: {result}"
    )


@pytest.mark.asyncio
async def test_postToolFlagSetterSearchPoliciesPlusAskHumanStaysPending():
    """If searchPolicies and askHuman both land in the same turn (unusual but
    possible when searchPolicies is followed immediately by askHuman in the
    same tool batch), clarificationPending should end True — a new pending
    state was established by the policy search. Last-write-wins semantic."""
    searchMsg = ToolMessage(
        name="searchPolicies",
        content=json.dumps([{"text": "some policy", "section": "1"}]),
        tool_call_id="tc-sp-2a",
    )
    askMsg = ToolMessage(
        name="askHuman",
        content=json.dumps({"response": "ok"}),
        tool_call_id="tc-sp-2b",
    )
    state = {
        "claimId": "claim-abc",
        "messages": [AIMessage(content=""), searchMsg, askMsg],
        "askHumanCount": 0,
        "clarificationPending": True,
    }
    result = await postToolFlagSetter(state)

    assert result.get("clarificationPending") is True


# ── Issue 2 (screenshot #6): Phase 1 step-9 confirmation gate ───────────────
# Source: 13-DEBUG-phase1-skip.md (CLAIM-018). After extractReceiptFields
# resumes, the model must emit askHuman("Do the details above look correct?")
# before calling searchPolicies. This was skipped in CLAIM-018 — model jumped
# straight to searchPolicies after the manual-rate askHuman. The flag-setter
# maintains `phase1ConfirmationPending` so preModelHook can inject a directive.

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter


@pytest.mark.asyncio
async def test_postToolFlagSetterSetsPhase1ConfirmationOnExtractReceiptFields():
    """extractReceiptFields ToolMessage → phase1ConfirmationPending=True."""
    tm = ToolMessage(
        content='{"fields": {"merchant": "X"}}',
        tool_call_id="tc-1",
        name="extractReceiptFields",
    )
    state = {"messages": [HumanMessage(content="Upload"), tm]}
    result = await postToolFlagSetter(state)

    assert result.get("phase1ConfirmationPending") is True


@pytest.mark.asyncio
async def test_postToolFlagSetterClearsPhase1ConfirmationOnConfirmationAskHuman():
    """askHuman resume with a 'correct' question pattern AND
    phase1ConfirmationPending=True → clears the flag."""
    ai = AIMessage(
        content="",
        tool_calls=[{
            "name": "askHuman",
            "args": {"question": "Do the details above look correct?"},
            "id": "call_conf",
        }],
    )
    tm = ToolMessage(content='{"response": "yes"}', tool_call_id="call_conf", name="askHuman")
    state = {
        "messages": [ai, tm],
        "phase1ConfirmationPending": True,
    }
    result = await postToolFlagSetter(state)

    assert result.get("phase1ConfirmationPending") is False


@pytest.mark.asyncio
async def test_postToolFlagSetterKeepsPhase1ConfirmationOnManualRateAskHuman():
    """Manual-rate askHuman ('exchange rate?') must NOT clear the flag. Only
    the step-9 confirmation question (containing 'correct') clears it."""
    ai = AIMessage(
        content="",
        tool_calls=[{
            "name": "askHuman",
            "args": {"question": "Can you share the exchange rate to SGD?"},
            "id": "call_rate",
        }],
    )
    tm = ToolMessage(content='{"response": "1.35"}', tool_call_id="call_rate", name="askHuman")
    state = {
        "messages": [ai, tm],
        "phase1ConfirmationPending": True,
    }
    result = await postToolFlagSetter(state)

    # Flag must remain True — only confirmation question clears it.
    # The key is not written back to False (idempotent no-op on non-match).
    assert result.get("phase1ConfirmationPending") is not False


@pytest.mark.asyncio
async def test_postToolFlagSetterPhase1FlagNoOpWhenFlagAlreadyFalse():
    """If phase1ConfirmationPending is already False, askHuman resume is a no-op
    for that flag (idempotent)."""
    ai = AIMessage(
        content="",
        tool_calls=[{
            "name": "askHuman",
            "args": {"question": "Do the details look correct?"},
            "id": "call_1",
        }],
    )
    tm = ToolMessage(content='{"response": "yes"}', tool_call_id="call_1", name="askHuman")
    state = {
        "messages": [ai, tm],
        "phase1ConfirmationPending": False,
    }
    result = await postToolFlagSetter(state)

    assert "phase1ConfirmationPending" not in result or result.get("phase1ConfirmationPending") is False
