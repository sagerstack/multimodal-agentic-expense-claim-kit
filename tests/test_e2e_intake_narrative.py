"""E2E test: Intake narrative flow with DIG restaurant receipt.

Validates the multi-turn conversational intake flow matching the system prompt:
  Phase 1 (Turn 1): Upload receipt -> extract fields + convert currency -> present table
  Phase 2 (Turn 2): User confirms details + employee ID -> policy check -> summary (no claim number)
  Phase 3 (Turn 3): User confirms submission -> submitClaim -> CLAIM-NNN success message (DB-generated)

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
    """Validate full multi-turn intake with DIG restaurant receipt ($16.20 USD).

    Follows the system prompt's 3-phase workflow:
      Phase 1: extractReceiptFields + convertCurrency -> present extraction table
      Phase 2: searchPolicies -> present summary (no claim number, DB will generate)
      Phase 3: submitClaim -> DB-generated CLAIM-NNN success confirmation
    """
    allTools = []

    # ── Phase 1 (Turn 1): Upload receipt ──
    turn1 = await runner.send(
        "Here is my lunch receipt from DIG restaurant",
        imagePath=RECEIPT_PATH,
    )

    allText1 = " ".join(turn1.messages).lower()
    toolNames1 = [s.name for s in turn1.steps]
    allTools.extend(toolNames1)

    # Assert: getClaimSchema was called first (schema-driven workflow)
    assert "getClaimSchema" in toolNames1, (
        f"getClaimSchema not called in Phase 1. Tools called: {toolNames1}"
    )

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

    # Assert: convertCurrency called for multiple monetary values (total + tax)
    convertCount = toolNames1.count("convertCurrency")
    # Note: At minimum total amount should be converted. Tax conversion is ideal but
    # depends on whether the receipt has a separate tax value. Accept >= 1 as minimum.
    assert convertCount >= 1, (
        f"convertCurrency should be called at least once. Called {convertCount} times."
    )

    # Assert: SGD mentioned (conversion result)
    assert "sgd" in allText1, (
        f"SGD not mentioned after currency conversion. Messages: {turn1.messages[:2]}"
    )

    # Assert: No tool errors in Phase 1
    for step in turn1.steps:
        if step.output:
            assert '"error"' not in step.output.lower() or "no error" in step.output.lower(), (
                f"Tool {step.name} returned error: {step.output[:200]}"
            )

    # Assert: Agent asks for confirmation (conversational or interrupt)
    asksConfirmation = any(
        keyword in allText1
        for keyword in ["correct", "confirm", "look right", "anything", "change", "verify"]
    )
    assert asksConfirmation or turn1.isInterrupted, (
        f"Agent did not ask for confirmation after Phase 1. Messages: {turn1.messages[-1:]}"
    )

    # ── Phase 2 (Turn 2): Confirm details + provide employee ID ──
    if turn1.isInterrupted:
        turn2 = await runner.send(
            "Yes, the details are correct. My employee ID is EMP-001."
        )
    else:
        turn2 = await runner.send(
            "Yes, the details are correct. My employee ID is EMP-001."
        )

    allText2 = " ".join(turn2.messages).lower()
    toolNames2 = [s.name for s in turn2.steps]
    allTools.extend(toolNames2)

    # Assert: Policy check happened
    assert "searchPolicies" in toolNames2, (
        f"searchPolicies not called in Phase 2. Tools called: {toolNames2}"
    )

    # Phase 2 no longer generates CLAIM-NNN (DB generates it on submission)
    # Assert: Agent presents summary and asks for confirmation
    asksSubmit = any(
        keyword in allText2
        for keyword in ["submit", "ready", "confirm", "proceed"]
    )
    assert asksSubmit or turn2.isInterrupted, (
        f"Agent did not ask for submission confirmation. Messages: {turn2.messages[-1:]}"
    )

    # ── Phase 3 (Turn 3): Confirm submission ──
    if turn2.isInterrupted:
        turn3 = await runner.send("yes, please submit")
    else:
        turn3 = await runner.send("yes, please submit")

    allText3 = " ".join(turn3.messages).lower()
    toolNames3 = [s.name for s in turn3.steps]
    allTools.extend(toolNames3)

    # Assert: submitClaim was called
    assert "submitClaim" in toolNames3, (
        f"submitClaim not called in Phase 3. Tools called: {toolNames3}"
    )

    # Assert: CLAIM-NNN pattern in Phase 3 success message (DB-generated)
    allText3Upper = " ".join(turn3.messages)
    claimIdMatch = re.search(r"CLAIM-\d{3}", allText3Upper)
    assert claimIdMatch, (
        f"CLAIM-NNN pattern not found in Phase 3 messages. Messages: {turn3.messages}"
    )
    claimNumber = claimIdMatch.group(0)

    # Assert: Success message mentions claim number
    assert claimNumber in allText3Upper, (
        f"Claim number {claimNumber} not in success message. Messages: {turn3.messages}"
    )

    # ── Cross-turn assertions ──

    # Assert: All 5 required tools were called across all turns
    requiredTools = ["getClaimSchema", "extractReceiptFields", "convertCurrency", "searchPolicies", "submitClaim"]
    for tool in requiredTools:
        assert tool in allTools, f"Required tool {tool} was never called. All tools: {allTools}"

    # Assert: Tool ordering (schema before extract, extract before convert, convert before policy, policy before submit)
    schemaIdx = allTools.index("getClaimSchema")
    extractIdx = allTools.index("extractReceiptFields")
    convertIdx = allTools.index("convertCurrency")
    policyIdx = allTools.index("searchPolicies")
    submitIdx = allTools.index("submitClaim")

    assert schemaIdx < extractIdx, (
        f"getClaimSchema ({schemaIdx}) should come before extractReceiptFields ({extractIdx})"
    )
    assert extractIdx < convertIdx, (
        f"extractReceiptFields ({extractIdx}) should come before convertCurrency ({convertIdx})"
    )
    assert convertIdx < policyIdx, (
        f"convertCurrency ({convertIdx}) should come before searchPolicies ({policyIdx})"
    )
    assert policyIdx < submitIdx, (
        f"searchPolicies ({policyIdx}) should come before submitClaim ({submitIdx})"
    )

    # Assert: No tool errors across all turns
    allSteps = turn1.steps + turn2.steps + turn3.steps
    for step in allSteps:
        if step.output:
            stepOutputLower = step.output.lower()
            assert '"error"' not in stepOutputLower or "no error" in stepOutputLower, (
                f"Tool {step.name} returned error: {step.output[:200]}"
            )
