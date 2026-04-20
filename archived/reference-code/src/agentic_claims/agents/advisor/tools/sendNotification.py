"""Advisor tool: send email notification via Email MCP.

Author: jamesoon

Wraps the Email MCP server's `sendClaimNotification` tool so the Advisor
Agent can notify the claimant and/or reviewer after making its routing decision.

Email addresses follow the SUTD convention:
  claimant → {employeeId}@sutd.edu.sg
  reviewer → expenses-reviewer@sutd.edu.sg  (shared reviewer inbox)
"""

import logging

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)

# Shared reviewer inbox for escalations
REVIEWER_EMAIL = "expenses-reviewer@sutd.edu.sg"

# Subject line templates per decision
SUBJECT_TEMPLATES = {
    "auto_approve": "Expense Claim {claimNumber} Approved",
    "return_to_claimant": "Action Required: Expense Claim {claimNumber} Returned",
    "escalate_to_reviewer": "Escalation: Expense Claim {claimNumber} Requires Review",
}


@tool
async def sendNotification(
    recipientType: str,
    employeeId: str,
    claimNumber: str,
    decision: str,
    message: str,
) -> dict:
    """Send a claim decision notification email via the Email MCP server.

    Args:
        recipientType: "claimant" or "reviewer"
                       - "claimant"  → {employeeId}@sutd.edu.sg
                       - "reviewer"  → expenses-reviewer@sutd.edu.sg
        employeeId: Employee ID of the claimant (used to build claimant email).
        claimNumber: Human-readable claim number (e.g. "CLAIM-001") for subject line.
        decision: Advisor routing decision for selecting the email subject template.
                  One of: "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
        message: Body text of the notification. Should be concise and actionable.

    Returns:
        Result dict from Email MCP server, or error dict on failure.
    """
    settings = getSettings()

    # Resolve recipient email address
    if recipientType == "claimant":
        toEmail = f"{employeeId}@sutd.edu.sg"
        status = "approved" if decision == "auto_approve" else (
            "returned" if decision == "return_to_claimant" else "escalated"
        )
    else:
        toEmail = REVIEWER_EMAIL
        status = "escalated"

    subject = SUBJECT_TEMPLATES.get(decision, "Expense Claim Update: {claimNumber}").format(
        claimNumber=claimNumber
    )

    logger.info(
        "sendNotification called",
        extra={
            "recipientType": recipientType,
            "toEmail": toEmail,
            "claimNumber": claimNumber,
            "decision": decision,
        },
    )

    result = await mcpCallTool(
        serverUrl=settings.email_mcp_url,
        toolName="sendClaimNotification",
        arguments={
            "to": toEmail,
            "claimNumber": claimNumber,
            "status": status,
            "message": message,
        },
    )

    if isinstance(result, dict) and "error" in result:
        logger.error(
            "sendNotification MCP call failed",
            extra={"error": result["error"], "toEmail": toEmail},
        )

    return result
