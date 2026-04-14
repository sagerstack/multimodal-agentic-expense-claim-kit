"""SubmitClaim hallucination guard — Bug 3 / ROADMAP Criterion 4.

Detects the specific failure class where the LLM emits an AIMessage
containing submission-success language (e.g. "your claim has been
submitted", "claim number is X") without a matching submitClaim
tool_call in the current turn. When detected, signals escalation.

Orthogonal to the clarificationPending drift check in postModelHook:
  - postModelHook fires on pending-clarification plain-text AIMessages.
  - submitClaimGuard fires on false-submission-success AIMessages.
Both can fire in the same turn (unlikely but supported — both would
set validatorEscalate independently).

Pure state-in / partial-state-out. No side effects beyond logEvent calls.

Sources:
  - docs/deep-research-systemprompt-chat-agent.md "User confirmation
    and consent flows" (approval must be code-enforced, not prompt-trusted)
  - docs/deep-research-report.md "Trust boundaries" (tool output is
    source of truth; prose is not)
  - ROADMAP Phase 13 Criterion 4 (Bug 3 fix)
  - 13-CONTEXT.md (validator strategy: escalate immediately for
    submitClaim hallucinations — no soft-rewrite on this class)
"""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)

# Conservative phrase patterns — any hit triggers the guard when combined
# with no matching submitClaim tool call in the turn.
# Intent: catch fabricated success claims, not legitimate acknowledgements
# that follow a real submitClaim tool call (those are allowed because we
# also verify the tool_call + ToolMessage pair exists in the turn).
_SUBMISSION_SUCCESS_PATTERNS = [
    re.compile(r"\bclaim\s+(?:has\s+been|is|was)\s+submitted\b", re.I),
    re.compile(r"\bsuccessfully\s+submitted\b", re.I),
    re.compile(r"\bclaim\s+number\s+is\b", re.I),
    re.compile(r"\bsubmission\s+(?:complete|successful)\b", re.I),
]


def _looksLikeSubmissionSuccess(content: Any) -> bool:
    """Return True if content contains a submission-success phrase."""
    if not isinstance(content, str):
        return False
    for pat in _SUBMISSION_SUCCESS_PATTERNS:
        if pat.search(content):
            return True
    return False


async def submitClaimGuard(state: dict) -> dict:
    """Scan messages from the current turn; escalate on hallucinated success.

    Current turn = messages since the most recent HumanMessage or
    turn-start. The function inspects the latest AIMessage for
    submission-success language and checks whether a submitClaim
    tool_call exists on any AIMessage AND a matching submitClaim
    ToolMessage followed in the same turn.

    Strategy (per 13-CONTEXT.md): escalate immediately on first detection.
    No soft-rewrite for this class — submitClaim hallucinations are severe
    enough to require human review, not automatic LLM retry.

    Returns {} if no violation detected, or
    {validatorEscalate: True} when the hallucination pattern fires.
    """
    messages = state.get("messages") or []
    claimId = state.get("claimId")
    threadId = state.get("threadId")

    # Find the most recent AIMessage
    lastAi: AIMessage | None = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)),
        None,
    )
    if lastAi is None:
        return {}

    aiContent = getattr(lastAi, "content", "") or ""
    if not _looksLikeSubmissionSuccess(aiContent):
        return {}

    # Walk back from the end of messages to the most recent HumanMessage.
    # Collect any submitClaim tool_calls (on AIMessages) and any submitClaim
    # ToolMessages in that window. Both must be present for a legitimate turn.
    submitToolCallFound = False
    submitToolResultFound = False

    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                tcName = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if tcName == "submitClaim":
                    submitToolCallFound = True
        if isinstance(msg, ToolMessage):
            if getattr(msg, "name", None) == "submitClaim":
                submitToolResultFound = True

    if submitToolCallFound and submitToolResultFound:
        # Legitimate acknowledgement after a real submitClaim tool call — allow
        return {}

    # Hallucination detected: submission-success language without matching tool evidence
    logEvent(
        logger,
        "intake.validator.escalate",
        logCategory="routing",
        claimId=claimId,
        threadId=threadId,
        turnIndex=state.get("turnIndex", 0),
        reason="submitClaim_hallucination",
        agent="intake",
    )

    return {"validatorEscalate": True}
