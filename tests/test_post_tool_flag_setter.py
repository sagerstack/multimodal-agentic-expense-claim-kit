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
