"""Human escalation terminal node.

Fires from the outer postIntakeRouter on any of the four escalation
triggers (CONTEXT.md "Escalation — triggers"):
  1. askHumanCount > 3 (loop-bound safety net)
  2. Critical tool failure
  3. User explicit give-up
  4. Unsupported scenario (e.g., validator_second_drift signals this
     class; user explicit is detected by Plan 05 post-tool flag setter)

Writes:
  - AIMessage with the verbatim CONTEXT.md template to state.messages
  - status="escalated" in ClaimState
  - escalationMetadata dict into intakeFindings for the reviewer
  - DB status via updateClaimStatus MCP (mirrors submitClaim.py and
    advisor/node.py — uses settings.db_mcp_url, NOT a hardcoded literal)

MCP URL convention: all call sites in this codebase call
    mcpCallTool(serverUrl=settings.db_mcp_url, ...)
This node follows the same pattern. Verified via:
    grep -rn 'db_mcp_url' src/agentic_claims/
which shows consistent use of settings.db_mcp_url across
submitClaim.py, advisor/node.py, web/routers/chat.py, graph.py.

Sources:
  - 13-CONTEXT.md "Escalation — user-facing message" (template verbatim)
  - 13-CONTEXT.md "Escalation — claim state shape"
  - 13-RESEARCH.md §6 (reviewer queue accepts "escalated" unchanged)
  - artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md L185
    (non-negotiable template)
"""

import logging
from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)

# Non-negotiable template per technical.md L185
_ESCALATION_MESSAGE = (
    "I couldn't complete this automatically. Your draft is saved. "
    "A reviewer will follow up."
)


def _classifyTrigger(state: dict) -> str:
    """Map state into the four CONTEXT.md trigger classes."""
    if state.get("validatorEscalate"):
        return "unsupportedScenario"
    if int(state.get("askHumanCount", 0)) > 3:
        return "loopBound"
    # criticalToolFailure and userGiveUp are detected by the post-tool
    # flag setter (Plan 05) which sets validatorEscalate or increments
    # askHumanCount as appropriate. Default to unsupportedScenario.
    return "unsupportedScenario"


async def humanEscalationNode(state: dict) -> dict:
    """Terminal escalation node. Persist status, emit terminal message.

    Returns:
        Partial ClaimState update with messages, status, and
        intakeFindings.escalationMetadata.
    """
    settings = getSettings()
    claimId = state.get("claimId")
    threadId = state.get("threadId")
    dbClaimId = state.get("dbClaimId")
    askHumanCount = int(state.get("askHumanCount", 0))
    unsupportedCurrencies = sorted(state.get("unsupportedCurrencies") or set())
    triggerClass = _classifyTrigger(state)
    triggeredAt = datetime.now(timezone.utc).isoformat()

    escalationMetadata = {
        "reason": triggerClass,
        "askHumanCount": askHumanCount,
        "unsupportedCurrencies": unsupportedCurrencies,
        "triggeredAt": triggeredAt,
    }

    logEvent(
        logger,
        "intake.escalation.triggered",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        threadId=threadId,
        triggerClass=triggerClass,
        askHumanCount=askHumanCount,
        unsupportedCurrencies=unsupportedCurrencies,
        message="Intake escalation triggered",
    )

    # Persist status to DB via the DB MCP (mirrors submitClaim.py /
    # advisor/node.py pattern: uses settings.db_mcp_url, not a literal).
    # If dbClaimId is missing (no submitClaim was ever called), we skip
    # the DB write but still return the ClaimState status update — the
    # reviewer cannot see claims that were never drafted, which is
    # the correct behaviour.
    if dbClaimId is not None:
        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="updateClaimStatus",
                arguments={
                    "claimId": dbClaimId,
                    "newStatus": "escalated",
                    "actor": "intake_agent",
                },
            )
            logEvent(
                logger,
                "claim.status_changed",
                logCategory="agent",
                agent="intake",
                claimId=claimId,
                dbClaimId=dbClaimId,
                oldStatus=state.get("status"),
                newStatus="escalated",
                actor="intake_agent",
                message="Claim status changed to escalated",
            )
        except Exception as exc:  # noqa: BLE001
            # Log but do not fail the escalation — the in-memory state
            # still transitions so the user sees the terminal message.
            logEvent(
                logger,
                "intake.escalation.db_write_failed",
                logCategory="agent",
                agent="intake",
                claimId=claimId,
                dbClaimId=dbClaimId,
                error=str(exc)[:200],
                message="Escalation DB write failed — continuing with in-memory state",
            )

    # Merge escalationMetadata into existing intakeFindings (preserve
    # any fields already written by the agent during this claim).
    existingFindings = dict(state.get("intakeFindings") or {})
    existingFindings["escalationMetadata"] = escalationMetadata

    return {
        "messages": [AIMessage(content=_ESCALATION_MESSAGE)],
        "status": "escalated",
        "claimSubmitted": False,
        "intakeFindings": existingFindings,
        "validatorEscalate": False,  # clear signal now that it's handled
    }
