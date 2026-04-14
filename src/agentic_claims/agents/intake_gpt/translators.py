"""State translators for intake-gpt wrapper integration."""

from __future__ import annotations

from typing import Any


def buildIntakeGptInput(state: dict) -> dict[str, Any]:
    """Project outer ClaimState into the intake-gpt subgraph input."""
    return {
        "claimId": state.get("claimId", ""),
        "threadId": state.get("threadId"),
        "status": state.get("status", "draft"),
        "messages": state.get("messages", []),
        "intakeGpt": state.get("intakeGpt"),
        "extractedReceipt": state.get("extractedReceipt"),
        "violations": state.get("violations"),
        "currencyConversion": state.get("currencyConversion"),
        "claimSubmitted": state.get("claimSubmitted"),
        "claimNumber": state.get("claimNumber"),
        "intakeFindings": state.get("intakeFindings"),
        "dbClaimId": state.get("dbClaimId"),
    }


def mergeIntakeGptResult(state: dict, result: dict) -> dict[str, Any]:
    """Translate subgraph output back into outer ClaimState updates."""
    merged: dict[str, Any] = {}

    resultMessages = result.get("messages")
    if resultMessages is not None:
        priorCount = len(state.get("messages") or [])
        newMessages = list(resultMessages)[priorCount:]
        if newMessages:
            merged["messages"] = newMessages

    if "intakeGpt" in result:
        merged["intakeGpt"] = result["intakeGpt"]

    for key in (
        "claimSubmitted",
        "claimNumber",
        "dbClaimId",
        "extractedReceipt",
        "currencyConversion",
        "violations",
        "intakeFindings",
    ):
        if key in result:
            merged[key] = result[key]

    return merged
