"""Unit tests for Phase 13 intake hook modules.

Coverage:
  - preModelHook: directive injection on flags, no directive when no flags,
    both directives when both flags set, ephemeral channel (no state.messages write)
  - postModelHook: no-op on clean, no-op when tool_calls present, soft-rewrite
    on first drift, escalate on second drift
  - postToolFlagSetter: representative tests (full coverage in test_post_tool_flag_setter.py)
    — VND unsupported sets flags, supported currency no-ops, askHuman increments count
  - submitClaimGuard: representative tests (full coverage in test_submit_claim_guard.py)
    — legitimate ack allowed, hallucination escalates, non-submission no-ops

Sources:
  - 13-07-PLAN.md test matrix
  - 13-CONTEXT.md hook architecture
  - src/agentic_claims/agents/intake/hooks/
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agentic_claims.agents.intake.hooks.postModelHook import postModelHook
from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter
from agentic_claims.agents.intake.hooks.preModelHook import preModelHook
from agentic_claims.agents.intake.hooks.submitClaimGuard import submitClaimGuard


# ── preModelHook ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preModelHookInjectsDirectiveWhenUnsupportedCurrencySet():
    """unsupportedCurrencies non-empty → SystemMessage directive injected with currency name."""
    state = {
        "messages": [HumanMessage(content="Process receipt")],
        "unsupportedCurrencies": {"VND"},
        "clarificationPending": False,
    }
    result = await preModelHook(state)

    assert "llm_input_messages" in result
    # Ephemeral channel — must NOT write state.messages
    assert "messages" not in result
    systemDirectives = [m for m in result["llm_input_messages"] if isinstance(m, SystemMessage)]
    assert len(systemDirectives) == 1
    assert "VND" in systemDirectives[0].content


@pytest.mark.asyncio
async def test_preModelHookInjectsBothDirectivesWhenBothFlagsSet():
    """Both unsupportedCurrencies and clarificationPending → two SystemMessage directives."""
    state = {
        "messages": [HumanMessage(content="Continue")],
        "unsupportedCurrencies": {"VND", "THB"},
        "clarificationPending": True,
    }
    result = await preModelHook(state)

    systemDirectives = [m for m in result["llm_input_messages"] if isinstance(m, SystemMessage)]
    assert len(systemDirectives) == 2


@pytest.mark.asyncio
async def test_preModelHookNoDirectiveWhenNoFlags():
    """No flags set → no SystemMessage directives; base messages pass through unchanged."""
    state = {
        "messages": [HumanMessage(content="Process receipt")],
        "unsupportedCurrencies": set(),
        "clarificationPending": False,
    }
    result = await preModelHook(state)

    systemDirectives = [m for m in result["llm_input_messages"] if isinstance(m, SystemMessage)]
    assert len(systemDirectives) == 0
    # Base messages still present — one HumanMessage should be in the list
    assert len(result["llm_input_messages"]) == 1


@pytest.mark.asyncio
async def test_preModelHookDirectivePrependedBeforeBaseMessages():
    """Directives appear BEFORE base messages in llm_input_messages."""
    state = {
        "messages": [HumanMessage(content="Submit my receipt")],
        "unsupportedCurrencies": {"VND"},
        "clarificationPending": False,
    }
    result = await preModelHook(state)

    messages = result["llm_input_messages"]
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage), "Directive should be first"
    assert isinstance(messages[1], HumanMessage), "Base message should be second"


@pytest.mark.asyncio
async def test_preModelHookNeverWritesStateDotMessages():
    """Return value must not contain 'messages' key — ephemeral channel only."""
    state = {
        "messages": [HumanMessage(content="x")],
        "unsupportedCurrencies": {"EUR"},
        "clarificationPending": True,
    }
    result = await preModelHook(state)

    assert "messages" not in result, (
        "preModelHook must use llm_input_messages (ephemeral), never write state.messages"
    )


# ── postModelHook ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_postModelHookNoOpOnCleanResponse():
    """No clarificationPending → hook returns empty dict (no drift)."""
    cleanAi = AIMessage(content="All done.", id="ai-clean")
    state = {
        "messages": [cleanAi],
        "clarificationPending": False,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)

    assert result == {}


@pytest.mark.asyncio
async def test_postModelHookNoOpWhenHasToolCalls():
    """AIMessage with tool_calls + clarificationPending → no drift (tool calls take precedence)."""
    ai = AIMessage(
        content="Let me check.",
        id="ai-with-tools",
        tool_calls=[{"name": "searchPolicies", "args": {"query": "x"}, "id": "c1"}],
    )
    state = {
        "messages": [ai],
        "clarificationPending": True,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)

    assert result == {}


@pytest.mark.asyncio
async def test_postModelHookNoOpWhenNoAiMessage():
    """No AIMessage in messages → empty dict (nothing to inspect)."""
    state = {
        "messages": [HumanMessage(content="Hello")],
        "clarificationPending": True,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)

    assert result == {}


@pytest.mark.asyncio
async def test_postModelHookSoftRewritesFirstDrift():
    """First drift (validatorRetryCount=0): returns RemoveMessage + corrective SystemMessage."""
    badAi = AIMessage(content="What currency is this?", id="ai-drift-1")
    state = {
        "messages": [HumanMessage(content="Submit"), badAi],
        "clarificationPending": True,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)

    assert "messages" in result, "Soft-rewrite must include messages (RemoveMessage + directive)"
    # RemoveMessage with matching id should appear in the messages list
    messageIds = [getattr(m, "id", None) for m in result["messages"]]
    assert "ai-drift-1" in messageIds, "RemoveMessage for drifted AI message must be present"
    assert result.get("validatorRetryCount") == 1
    # Must NOT escalate on first drift
    assert not result.get("validatorEscalate")


@pytest.mark.asyncio
async def test_postModelHookEscalatesOnSecondDrift():
    """Second drift (validatorRetryCount=1): returns validatorEscalate=True, no soft-rewrite."""
    badAi = AIMessage(content="What?", id="ai-drift-2")
    state = {
        "messages": [badAi],
        "clarificationPending": True,
        "validatorRetryCount": 1,
    }
    result = await postModelHook(state)

    assert result.get("validatorEscalate") is True
    # On second drift the hook escalates — no soft-rewrite message needed
    # (validatorEscalate is the ONLY required signal)


@pytest.mark.asyncio
async def test_postModelHookNoOpWhenAiHasEmptyContent():
    """AIMessage with empty content (e.g. pure tool-call message) → no drift."""
    ai = AIMessage(content="", id="ai-empty")
    state = {
        "messages": [ai],
        "clarificationPending": True,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)

    assert result == {}


# ── postToolFlagSetter — representative tests ───────────────────────────────
# Full coverage lives in tests/test_post_tool_flag_setter.py (10 tests).
# These tests confirm the key contracts expected by test_intake_hooks.py spec.


@pytest.mark.asyncio
async def test_postToolFlagSetterDetectsUnsupportedCurrency():
    """convertCurrency {supported: false, currency: VND} → unsupportedCurrencies + clarificationPending."""
    tm = ToolMessage(
        content='{"supported": false, "currency": "VND", "error": "unsupported"}',
        tool_call_id="tc-1",
        name="convertCurrency",
    )
    state = {"messages": [HumanMessage(content="x"), tm]}
    result = await postToolFlagSetter(state)

    assert result.get("unsupportedCurrencies") == {"VND"}
    assert result.get("clarificationPending") is True


@pytest.mark.asyncio
async def test_postToolFlagSetterNoFlagsOnSupportedCurrency():
    """convertCurrency {supported: true} → no flags set."""
    tm = ToolMessage(
        content='{"supported": true, "convertedAmount": 13.5, "rate": 1.35}',
        tool_call_id="tc-2",
        name="convertCurrency",
    )
    state = {"messages": [tm]}
    result = await postToolFlagSetter(state)

    assert "unsupportedCurrencies" not in result
    assert not result.get("clarificationPending")


@pytest.mark.asyncio
async def test_postToolFlagSetterIncrementsAskHumanCount():
    """askHuman ToolMessage → askHumanCount incremented by 1 from prior count."""
    tm = ToolMessage(content="user_answered", tool_call_id="tc-3", name="askHuman")
    state = {"messages": [tm], "askHumanCount": 2}
    result = await postToolFlagSetter(state)

    assert result.get("askHumanCount") == 3


@pytest.mark.asyncio
async def test_postToolFlagSetterIdempotentOnSameUnsupportedCurrency():
    """Calling postToolFlagSetter twice with the same state produces the same set (idempotent)."""
    tm = ToolMessage(
        content='{"supported": false, "currency": "VND"}',
        tool_call_id="tc-4",
        name="convertCurrency",
    )
    state = {"messages": [tm]}
    r1 = await postToolFlagSetter(state)
    r2 = await postToolFlagSetter(state)

    assert r1.get("unsupportedCurrencies") == r2.get("unsupportedCurrencies") == {"VND"}


# ── submitClaimGuard — representative tests ─────────────────────────────────
# Full coverage lives in tests/test_submit_claim_guard.py (11 tests).
# These tests confirm the key contracts expected by test_intake_hooks.py spec.


@pytest.mark.asyncio
async def test_submitClaimGuardAllowsLegitimateAcknowledgement():
    """Real submitClaim tool_call + ToolMessage present → guard returns {} (no escalation)."""
    callAi = AIMessage(
        content="",
        id="ai-call",
        tool_calls=[{"name": "submitClaim", "args": {}, "id": "sc-1"}],
    )
    toolResult = ToolMessage(
        content='{"claimNumber": "CL-001", "dbClaimId": 42}',
        tool_call_id="sc-1",
        name="submitClaim",
    )
    ackAi = AIMessage(
        content="Your claim has been submitted as CL-001.",
        id="ai-ack",
    )
    state = {
        "messages": [
            HumanMessage(content="Please submit"),
            callAi,
            toolResult,
            ackAi,
        ],
    }
    result = await submitClaimGuard(state)

    assert result == {}


@pytest.mark.asyncio
async def test_submitClaimGuardEscalatesOnHallucinatedSuccess():
    """AIMessage claiming success with no submitClaim tool call → validatorEscalate=True."""
    badAi = AIMessage(
        content="Your claim has been submitted as CL-999.",
        id="ai-halluc",
    )
    state = {
        "messages": [HumanMessage(content="Do it"), badAi],
    }
    result = await submitClaimGuard(state)

    assert result.get("validatorEscalate") is True


@pytest.mark.asyncio
async def test_submitClaimGuardNoOpOnNonSubmissionContent():
    """Ordinary AI message without submission language → empty dict (no false positive)."""
    ai = AIMessage(content="Let me check the policy.", id="ai-plain")
    state = {"messages": [ai]}
    result = await submitClaimGuard(state)

    assert result == {}
