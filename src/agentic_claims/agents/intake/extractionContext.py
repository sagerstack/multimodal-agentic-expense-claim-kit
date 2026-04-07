"""Request-scoped context variables for intake agent processing.

extractedReceiptVar: Set by intakeNode after extractReceiptFields completes.
    Read by submitClaim to inject confidenceScores into intakeFindings.

sessionClaimIdVar: Set by the chat router before graph invocation.
    Read by submitClaim as fallback for flushSteps when LLM omits sessionClaimId.
"""

from contextvars import ContextVar

extractedReceiptVar: ContextVar[dict | None] = ContextVar("extractedReceiptVar", default=None)
sessionClaimIdVar: ContextVar[str | None] = ContextVar("sessionClaimIdVar", default=None)
