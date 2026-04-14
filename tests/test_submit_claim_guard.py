"""Tests for submitClaimGuard — RED phase (13-05 TDD).

Tests Bug 3 / ROADMAP Criterion 4: the guard that detects when an LLM
AIMessage claims submission success without a matching submitClaim
tool_call and ToolMessage in the current turn.

Sources:
  - 13-05-PLAN.md must_haves (truths + artifacts)
  - docs/deep-research-systemprompt-chat-agent.md "User confirmation and consent flows"
  - ROADMAP Phase 13 Criterion 4 (Bug 3 fix)
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_claims.agents.intake.hooks.submitClaimGuard import submitClaimGuard


# ---------------------------------------------------------------------------
# Hallucination detection — submission-success language, no real tool call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testSubmitClaimGuardDetectsHallucinatedSubmission():
    """AIMessage with 'claim has been submitted' but no submitClaim tool call -> escalate."""
    aiMsg = AIMessage(content="Your claim has been submitted successfully. The claim number is CL-001.")
    state = {
        "claimId": "claim-abc",
        "threadId": "thread-xyz",
        "turnIndex": 2,
        "messages": [HumanMessage(content="Please submit"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result.get("validatorEscalate") is True


@pytest.mark.asyncio
async def testSubmitClaimGuardDetectsSuccessfullySubmittedPhrase():
    """'successfully submitted' phrase triggers the guard."""
    aiMsg = AIMessage(content="I have successfully submitted your expense claim for review.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="Go ahead"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result.get("validatorEscalate") is True


@pytest.mark.asyncio
async def testSubmitClaimGuardDetectsSubmissionCompletePhrase():
    """'submission complete' phrase triggers the guard."""
    aiMsg = AIMessage(content="Submission complete. Your claim is now in the review queue.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="Submit it"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result.get("validatorEscalate") is True


@pytest.mark.asyncio
async def testSubmitClaimGuardDetectsClaimNumberIsPhrase():
    """'claim number is' phrase triggers the guard without a tool call."""
    aiMsg = AIMessage(content="Your claim number is CLAIM-042.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="What is my claim number?"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result.get("validatorEscalate") is True


# ---------------------------------------------------------------------------
# No false positives — legitimate submission after real submitClaim tool call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testSubmitClaimGuardAllowsLegitimateSubmissionAcknowledgement():
    """Real submitClaim tool_call + ToolMessage -> guard must NOT fire."""
    submitAiMsg = AIMessage(
        content="",
        tool_calls=[{"name": "submitClaim", "id": "tc-99", "args": {"claimData": {}, "receiptData": {}}}],
    )
    submitToolMsg = ToolMessage(
        name="submitClaim",
        content='{"claim": {"id": 7, "claim_number": "CLAIM-007"}, "receipt": {"id": 3}}',
        tool_call_id="tc-99",
    )
    ackAiMsg = AIMessage(content="Your claim has been submitted. The claim number is CLAIM-007.")
    state = {
        "claimId": "claim-abc",
        "messages": [
            HumanMessage(content="Submit my claim"),
            submitAiMsg,
            submitToolMsg,
            ackAiMsg,
        ],
    }
    result = await submitClaimGuard(state)

    assert result == {}


@pytest.mark.asyncio
async def testSubmitClaimGuardAllowsSuccessfullySubmittedAfterRealCall():
    """'successfully submitted' after real tool call must not escalate."""
    submitAiMsg = AIMessage(
        content="",
        tool_calls=[{"name": "submitClaim", "id": "tc-100", "args": {}}],
    )
    submitToolMsg = ToolMessage(
        name="submitClaim",
        content='{"claim": {"id": 8, "claim_number": "CLAIM-008"}, "receipt": {}}',
        tool_call_id="tc-100",
    )
    ackAiMsg = AIMessage(content="I have successfully submitted your claim. Claim number: CLAIM-008.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="submit"), submitAiMsg, submitToolMsg, ackAiMsg],
    }
    result = await submitClaimGuard(state)

    assert result == {}


# ---------------------------------------------------------------------------
# No false positives — neutral / unrelated messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testSubmitClaimGuardIgnoresNeutralMessage():
    """Ordinary informational message -> no escalation."""
    aiMsg = AIMessage(content="Let me check the applicable policy for transport expenses.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="What policy applies?"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result == {}


@pytest.mark.asyncio
async def testSubmitClaimGuardIgnoresExtractConfirmationMessage():
    """Extraction confirmation without submission language -> no escalation."""
    aiMsg = AIMessage(content="I have extracted the receipt fields. Please confirm: Merchant: ABC, Amount: $50.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="Here is my receipt"), aiMsg],
    }
    result = await submitClaimGuard(state)

    assert result == {}


@pytest.mark.asyncio
async def testSubmitClaimGuardReturnsEmptyWhenNoMessages():
    """Empty message list -> no escalation."""
    state = {"claimId": "claim-abc", "messages": []}
    result = await submitClaimGuard(state)

    assert result == {}


@pytest.mark.asyncio
async def testSubmitClaimGuardReturnsEmptyWhenNoAIMessage():
    """No AIMessage in messages -> no escalation."""
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="Submit my claim")],
    }
    result = await submitClaimGuard(state)

    assert result == {}


# ---------------------------------------------------------------------------
# logEvent emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def testSubmitClaimGuardEmitsEscalationLogEvent():
    """intake.validator.escalate is logged on hallucination detection."""
    aiMsg = AIMessage(content="Your claim has been submitted as CLAIM-999.")
    state = {
        "claimId": "claim-abc",
        "messages": [HumanMessage(content="submit"), aiMsg],
        "turnIndex": 3,
    }
    with patch("agentic_claims.agents.intake.hooks.submitClaimGuard.logEvent") as mockLog:
        await submitClaimGuard(state)
        callArgs = [call.args[1] for call in mockLog.call_args_list]
        assert "intake.validator.escalate" in callArgs
