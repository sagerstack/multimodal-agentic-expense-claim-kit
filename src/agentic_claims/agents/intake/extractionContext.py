"""Request-scoped context variables for intake agent processing.

extractedReceiptVar: Set by intakeNode after extractReceiptFields completes.
    Read by submitClaim to inject confidenceScores into intakeFindings.

sessionClaimIdVar: Set by the chat router before graph invocation.
    Read by submitClaim as fallback for flushSteps when LLM omits sessionClaimId.
"""

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

extractedReceiptVar: ContextVar[dict | None] = ContextVar("extractedReceiptVar", default=None)
sessionClaimIdVar: ContextVar[str | None] = ContextVar("sessionClaimIdVar", default=None)


def trustedExtractedReceipt(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Resolve canonical receipt evidence exclusively from trusted graph state."""
    intakeGpt = state.get("intakeGpt")
    slots = intakeGpt.get("slots") if isinstance(intakeGpt, Mapping) else None
    candidates = (
        slots.get("extractedReceipt") if isinstance(slots, Mapping) else None,
        state.get("extractedReceipt"),
    )
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        fields = candidate.get("fields")
        if not isinstance(fields, Mapping):
            fields = candidate.get("extractedFields")
        confidence = candidate.get("confidence")
        if not isinstance(confidence, Mapping):
            confidence = candidate.get("confidenceScores")
        if not isinstance(fields, Mapping) and not isinstance(confidence, Mapping):
            continue

        canonical = dict(candidate)
        canonical.pop("extractedFields", None)
        canonical.pop("confidenceScores", None)
        if isinstance(fields, Mapping):
            canonical["fields"] = dict(fields)
        if isinstance(confidence, Mapping):
            canonical["confidence"] = dict(confidence)
        return canonical
    return None
