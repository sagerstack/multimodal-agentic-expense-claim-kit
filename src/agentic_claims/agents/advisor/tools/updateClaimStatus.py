"""Advisor tool: update claim status in the database via DB MCP.

Calls the DB MCP server's `updateClaimStatus` tool to persist the advisor's
routing decision back to PostgreSQL and create an audit log entry.

Status transitions driven by advisor decision:
  auto_approve        → "ai_approved"
  return_to_claimant  → "ai_rejected"
  escalate_to_reviewer → "escalated"
"""

import logging

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)

# Maps advisor decision strings to DB status values
DECISION_TO_STATUS = {
    "auto_approve": "ai_approved",
    "return_to_claimant": "ai_rejected",
    "escalate_to_reviewer": "escalated",
}


@tool
async def updateClaimStatus(dbClaimId: int, decision: str, reasoning: str) -> dict:
    """Update the expense claim status in the database.

    Maps advisor routing decision to a DB status and writes an audit log entry.

    Args:
        dbClaimId: Integer primary key of the claim in the `claims` table.
        decision: Advisor routing decision — one of:
                  "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
        reasoning: One-sentence explanation for the audit log actor field.

    Returns:
        Updated claim record dict from the DB MCP server,
        or error dict if the update failed.
    """
    settings = getSettings()

    newStatus = DECISION_TO_STATUS.get(decision, "escalated")
    actor = f"advisor_agent:{decision}"

    logger.info(
        "updateClaimStatus called",
        extra={"dbClaimId": dbClaimId, "decision": decision, "newStatus": newStatus},
    )

    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="updateClaimStatus",
        arguments={
            "claimId": dbClaimId,
            "newStatus": newStatus,
            "actor": actor,
        },
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(
            "updateClaimStatus MCP call failed",
            extra={"error": result["error"], "dbClaimId": dbClaimId},
        )

    return result
