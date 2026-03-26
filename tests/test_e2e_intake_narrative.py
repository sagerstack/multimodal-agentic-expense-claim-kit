"""E2E test: Intake narrative flow with DIG restaurant receipt.

Validates the full conversational intake flow:
1. Upload receipt image -> extraction with merchant, date, amount
2. Currency conversion (USD -> SGD)
3. Policy validation (meal expense under cap -> pass)
4. Summary card with CLAIM-NNN
5. User confirms -> submission
6. Success message

Prerequisites:
    - Docker services running: scripts/startup.sh
    - Valid OpenRouter API key in .env.e2e
    - Policies ingested into Qdrant

Run with: pytest -m e2e tests/test_e2e_intake_narrative.py -v
"""

import re

import pytest

from agentic_claims.cli import ConversationRunner


RECEIPT_PATH = "artifacts/receipts/receipt-pass-restaurant.jpeg"


@pytest.fixture
async def runner():
    """Create and initialize a ConversationRunner for E2E testing."""
    runner = ConversationRunner(envFile=".env.e2e")
    await runner.start()
    yield runner
    await runner.close()


@pytest.mark.e2e
async def test_intake_narrative_restaurant_receipt(runner):
    """Validate full intake narrative with DIG restaurant receipt ($16.20 USD).

    Expected narrative (aligned with sample conversation):
    A) Welcome message (from runner.start())
    B) Upload receipt -> agent extracts fields (DIG, $16.20, USD)
    C) Agent converts USD -> SGD
    D) Agent checks policy (meal expense under SGD 100 cap -> pass)
    E) Agent presents summary card with CLAIM-NNN
    F) Agent asks for confirmation (interrupt via askHuman)
    G) User confirms -> agent submits claim
    H) Agent shows success message with claim ID
    """
    # ── Turn 1: Upload receipt ──
    turn1 = await runner.send(
        "Here is my lunch receipt from DIG restaurant",
        imagePath=RECEIPT_PATH,
    )

    # Collect all text from turn1 for assertions
    allText1 = " ".join(turn1.messages).lower()
    toolNames1 = [s.name for s in turn1.steps]

    # Assert: extractReceiptFields was called
    assert "extractReceiptFields" in toolNames1, (
        f"extractReceiptFields not called. Tools called: {toolNames1}"
    )

    # Assert: Merchant extracted (DIG or dig)
    assert "dig" in allText1, (
        f"Merchant 'DIG' not found in agent messages. Messages: {turn1.messages[:2]}"
    )

    # Assert: Currency conversion happened (USD receipt)
    assert "convertCurrency" in toolNames1, (
        f"convertCurrency not called for USD receipt. Tools called: {toolNames1}"
    )

    # Assert: SGD mentioned (conversion result)
    assert "sgd" in allText1, (
        f"SGD not mentioned after currency conversion. Messages: {turn1.messages[:2]}"
    )

    # Assert: Policy check happened
    assert "searchPolicies" in toolNames1, (
        f"searchPolicies not called. Tools called: {toolNames1}"
    )

    # Assert: CLAIM-NNN pattern in summary card
    allText1Upper = " ".join(turn1.messages)
    claimIdMatch = re.search(r"CLAIM-\d{3}", allText1Upper)
    assert claimIdMatch, (
        f"CLAIM-NNN pattern not found in agent messages. Messages: {turn1.messages[-2:]}"
    )
    claimId = claimIdMatch.group(0)

    # Assert: Agent asks for confirmation (interrupt)
    # The agent should either ask via askHuman (interrupt) or in a message
    if turn1.isInterrupted:
        # askHuman interrupt triggered -- standard flow
        assert turn1.interruptQuestion, "Interrupt has no question"

        # ── Turn 2: Confirm submission ──
        turn2 = await runner.send("yes, please submit")

        allText2 = " ".join(turn2.messages).lower()
        toolNames2 = [s.name for s in turn2.steps]

        # Assert: submitClaim was called
        assert "submitClaim" in toolNames2, (
            f"submitClaim not called after confirmation. Tools called: {toolNames2}"
        )

        # Assert: Success message mentions the claim ID
        allText2Upper = " ".join(turn2.messages)
        assert claimId in allText2Upper or "submit" in allText2, (
            f"Claim ID {claimId} or submission confirmation not in response. "
            f"Messages: {turn2.messages}"
        )

    else:
        # Agent submitted without asking (non-standard but valid)
        # submitClaim should already be in turn1 tools
        assert "submitClaim" in toolNames1, (
            f"No interrupt AND no submitClaim in turn1. Tools called: {toolNames1}"
        )

    # ── Cross-turn assertions ──
    allTools = toolNames1 + ([s.name for s in turn2.steps] if turn1.isInterrupted else [])

    # Assert: All 4 required tools were called in order
    requiredTools = ["extractReceiptFields", "convertCurrency", "searchPolicies", "submitClaim"]
    for tool in requiredTools:
        assert tool in allTools, f"Required tool {tool} was never called. All tools: {allTools}"

    # Assert: Tool ordering (extract before convert, convert before policy, policy before submit)
    extractIdx = allTools.index("extractReceiptFields")
    convertIdx = allTools.index("convertCurrency")
    policyIdx = allTools.index("searchPolicies")
    submitIdx = allTools.index("submitClaim")

    assert extractIdx < convertIdx, (
        f"extractReceiptFields ({extractIdx}) should come before convertCurrency ({convertIdx})"
    )
    assert convertIdx < policyIdx, (
        f"convertCurrency ({convertIdx}) should come before searchPolicies ({policyIdx})"
    )
    assert policyIdx < submitIdx, (
        f"searchPolicies ({policyIdx}) should come before submitClaim ({submitIdx})"
    )

    # Assert: No errors in tool outputs (check for "error" in step outputs)
    for step in turn1.steps:
        if step.output:
            stepOutputLower = step.output.lower()
            assert '"error"' not in stepOutputLower or "no error" in stepOutputLower, (
                f"Tool {step.name} returned error: {step.output[:200]}"
            )


@pytest.mark.e2e
async def test_intake_narrative_has_narration(runner):
    """Validate that agent produces narration messages before tool calls.

    The corrected prompt (Plan 03) instructs the agent to narrate before each tool:
    - Before extractReceiptFields: "Let me process..." or "image" or "receipt"
    - Before convertCurrency: "Let me convert..." or mentions currency
    - Before searchPolicies: "Let me validate..." or mentions policy
    - Before submitClaim: "Submitting..." or mentions submit
    """
    turn1 = await runner.send(
        "Here is my lunch receipt",
        imagePath=RECEIPT_PATH,
    )

    allText = " ".join(turn1.messages).lower()

    # Assert: Narration before extraction (some form of "process" or "image")
    assert any(
        word in allText for word in ["process", "image", "receipt", "extract"]
    ), f"No extraction narration found. Messages: {turn1.messages[:1]}"

    # Assert: Narration about currency (some form of "convert" or "sgd" or "currency")
    assert any(
        word in allText for word in ["convert", "sgd", "currency", "usd"]
    ), f"No currency narration found. Messages: {turn1.messages}"

    # Assert: Narration about policy (some form of "policy" or "validate" or "check")
    assert any(
        word in allText for word in ["policy", "validate", "check", "compliance"]
    ), f"No policy narration found. Messages: {turn1.messages}"
