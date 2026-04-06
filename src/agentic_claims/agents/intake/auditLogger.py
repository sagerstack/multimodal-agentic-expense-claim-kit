"""Intake audit logging helper with buffer + flush pattern.

During intake processing the DB claim ID doesn't exist yet, so audit steps are
buffered in memory keyed by the session claimId (a UUID string). When the claim
is successfully inserted, flushSteps writes all buffered entries to audit_log
via the DB MCP server's insertAuditLog tool.

This module never raises — audit logging failures are logged as warnings but
must never crash the intake pipeline.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)

# Module-level buffer: sessionClaimId -> list of pending audit entries
_auditBuffer: dict[str, list[dict]] = {}


def bufferStep(sessionClaimId: str, action: str, details: dict) -> None:
    """Buffer an audit step for later flushing.

    Called during intake processing before the DB claim ID exists.
    Idempotent per action: if the action is already buffered for this session
    (from a prior turn's message scan), it is silently skipped. This prevents
    BUG-018 where multi-turn conversations cause duplicate audit_log rows.

    Args:
        sessionClaimId: Session-scoped UUID string (from ClaimState.claimId)
        action: Audit action label (e.g., 'receipt_uploaded', 'ai_extraction')
        details: Structured data for this step (confidence, violations, etc.)
    """
    if sessionClaimId not in _auditBuffer:
        _auditBuffer[sessionClaimId] = []

    # BUG-018: skip if this action is already buffered for this session
    existing = _auditBuffer[sessionClaimId]
    if any(e["action"] == action for e in existing):
        logger.debug(
            "Audit step already buffered — skipping duplicate",
            extra={"sessionClaimId": sessionClaimId, "action": action},
        )
        return

    entry = {
        "action": action,
        "details": details,
        "bufferedAt": datetime.now(timezone.utc).isoformat(),
    }
    existing.append(entry)
    logger.debug(
        "Audit step buffered",
        extra={"sessionClaimId": sessionClaimId, "action": action},
    )


async def flushSteps(sessionClaimId: str, dbClaimId: int, actor: str = "intake_agent") -> None:
    """Flush all buffered audit steps to the DB for a given session.

    Called after the claim is successfully inserted and the DB claim ID is known.
    Each buffered entry is written via the insertAuditLog MCP tool. Failures are
    logged as warnings but do not abort the flush loop or raise to the caller.

    Args:
        sessionClaimId: Session-scoped UUID string matching the buffer key
        dbClaimId: Integer primary key of the inserted claim row
        actor: Actor label written to audit_log (default: 'intake_agent')
    """
    entries = _auditBuffer.get(sessionClaimId, [])
    if not entries:
        logger.debug(
            "No buffered audit steps to flush",
            extra={"sessionClaimId": sessionClaimId},
        )
        return

    logger.info(
        "Flushing buffered audit steps",
        extra={"sessionClaimId": sessionClaimId, "count": len(entries), "dbClaimId": dbClaimId},
    )

    settings = getSettings()

    for entry in entries:
        try:
            newValue = json.dumps(entry["details"])
            oldValue = entry.get("bufferedAt", "")
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": entry["action"],
                    "newValue": newValue,
                    "actor": actor,
                    "oldValue": oldValue,
                },
            )
            logger.debug(
                "Audit step flushed",
                extra={"action": entry["action"], "dbClaimId": dbClaimId},
            )
        except Exception as e:
            logger.warning(
                "Failed to flush audit step — continuing",
                extra={"action": entry.get("action"), "error": str(e)},
            )

    # Clear buffer for this session after flush attempt
    _auditBuffer.pop(sessionClaimId, None)
    logger.info(
        "Audit buffer cleared",
        extra={"sessionClaimId": sessionClaimId},
    )


async def logIntakeStep(
    claimId: int,
    action: str,
    details: dict[str, Any],
    actor: str = "intake_agent",
) -> None:
    """Write a single audit step directly (non-buffered) when DB claim ID is known.

    Args:
        claimId: Integer primary key of the claim row
        action: Audit action label
        details: Structured data for this step
        actor: Actor label written to audit_log
    """
    settings = getSettings()
    try:
        newValue = json.dumps(details)
        await mcpCallTool(
            serverUrl=settings.db_mcp_url,
            toolName="insertAuditLog",
            arguments={
                "claimId": claimId,
                "action": action,
                "newValue": newValue,
                "actor": actor,
                "oldValue": "",
            },
        )
        logger.debug(
            "Direct audit step written",
            extra={"claimId": claimId, "action": action},
        )
    except Exception as e:
        logger.warning(
            "Failed to write direct audit step — continuing",
            extra={"claimId": claimId, "action": action, "error": str(e)},
        )
