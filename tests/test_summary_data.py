"""Unit tests for BUG-013 guard and step-driven progressPct."""

import json

from agentic_claims.web.sseHelpers import _calcProgressPct, _extractSummaryData


# --- Helper to build thinkingEntries ---


def _makeToolEntry(name: str, output: dict | None = None) -> dict:
    """Build a thinkingEntries tool entry."""
    return {
        "type": "tool",
        "name": name,
        "elapsed": 1.2,
        "output": json.dumps(output or {}),
    }


def _makeExtractEntry() -> dict:
    """Build an extractReceiptFields entry with valid receipt data."""
    return _makeToolEntry(
        "extractReceiptFields",
        {
            "fields": {
                "merchant": "DIG",
                "totalAmount": "16.20",
                "currency": "USD",
                "category": "meals",
            },
            "confidence": {"merchant": 0.95, "totalAmount": 0.90},
        },
    )


def _makeSubmitEntry(claimNumber: str = "CLAIM-007") -> dict:
    """Build a submitClaim entry with valid claim data."""
    return _makeToolEntry(
        "submitClaim",
        {"claim": {"claim_number": claimNumber, "id": 7}},
    )


# --- BUG-013 Guard Tests ---


def testBug013SuppressesSubmittedWhenNoToolCall():
    """When no submitClaim tool entry AND graphState not submitted, submitted=False."""
    entries = [_makeExtractEntry()]
    graphState = {"claimSubmitted": False, "extractedReceipt": None}

    result = _extractSummaryData(entries, graphState=graphState)
    assert result is not None
    assert result["submitted"] is False
    assert result["claimNumber"] == ""


def testBug013AllowsSubmittedWhenToolCallExists():
    """When submitClaim tool entry exists with valid data, submitted=True."""
    entries = [_makeExtractEntry(), _makeSubmitEntry("CLAIM-007")]
    graphState = {}

    result = _extractSummaryData(entries, graphState=graphState)
    assert result is not None
    assert result["submitted"] is True
    assert result["claimNumber"] == "CLAIM-007"


def testBug013AllowsSubmittedFromGraphStatePriorTurn():
    """When graphState has claimSubmitted=True from prior turn, submitted=True preserved."""
    entries = [_makeExtractEntry()]
    graphState = {
        "claimSubmitted": True,
        "claimNumber": "CLAIM-005",
        "extractedReceipt": {
            "fields": {
                "merchant": "DIG",
                "totalAmount": "16.20",
                "currency": "USD",
                "category": "meals",
            }
        },
    }

    result = _extractSummaryData(entries, graphState=graphState)
    assert result is not None
    assert result["submitted"] is True


# --- Step-Driven progressPct Tests ---


def testProgressPctExtractOnly():
    """extractReceiptFields only -> 33%."""
    entries = [_makeToolEntry("extractReceiptFields")]
    assert _calcProgressPct(entries, None) == 33


def testProgressPctSearchPolicies():
    """extractReceiptFields + searchPolicies -> 50%."""
    entries = [
        _makeToolEntry("extractReceiptFields"),
        _makeToolEntry("searchPolicies"),
    ]
    assert _calcProgressPct(entries, None) == 50


def testProgressPctUserConfirmed():
    """askHuman or convertCurrency -> 66%."""
    entries = [
        _makeToolEntry("extractReceiptFields"),
        _makeToolEntry("searchPolicies"),
        _makeToolEntry("convertCurrency"),
    ]
    assert _calcProgressPct(entries, None) == 66

    entriesAskHuman = [
        _makeToolEntry("extractReceiptFields"),
        _makeToolEntry("askHuman"),
    ]
    assert _calcProgressPct(entriesAskHuman, None) == 66


def testProgressPctSubmitClaim():
    """submitClaim -> 100%."""
    entries = [
        _makeToolEntry("extractReceiptFields"),
        _makeToolEntry("searchPolicies"),
        _makeToolEntry("submitClaim"),
    ]
    assert _calcProgressPct(entries, None) == 100


def testProgressPctFromGraphStatePriorTurn():
    """Empty thinkingEntries but graphState has extractedReceipt -> 33%."""
    entries = []
    graphState = {
        "extractedReceipt": {
            "fields": {"merchant": "DIG", "totalAmount": "16.20"}
        }
    }
    assert _calcProgressPct(entries, graphState) == 33
