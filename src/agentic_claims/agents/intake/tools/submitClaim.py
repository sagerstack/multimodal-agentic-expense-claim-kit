"""Claim submission tool using DB MCP server."""

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings


@tool
async def submitClaim(claimData: dict, receiptData: dict) -> dict:
    """Submit a claim and its receipt to the database.

    Args:
        claimData: Claim fields (employeeId, totalAmount, currency, etc.)
        receiptData: Receipt fields (merchant, date, totalAmount, currency, lineItems, etc.)

    Returns:
        Dict with "claim" and "receipt" keys containing the inserted records,
        or error dict if submission fails
    """
    settings = getSettings()

    # Step 1: Insert claim
    claimResult = await mcpCallTool(
        serverUrl=settings.db_mcp_url, toolName="insertClaim", arguments=claimData
    )

    # If claim insertion failed, return error without attempting receipt insertion
    if isinstance(claimResult, dict) and "error" in claimResult:
        return claimResult

    # Extract claim_id for foreign key link
    claimId = claimResult.get("claim_id")
    if not claimId:
        return {"error": "insertClaim did not return claim_id"}

    # Step 2: Insert receipt with FK link to claim
    receiptDataWithFk = {**receiptData, "claimId": claimId}
    receiptResult = await mcpCallTool(
        serverUrl=settings.db_mcp_url, toolName="insertReceipt", arguments=receiptDataWithFk
    )

    # If receipt insertion failed, return error
    if isinstance(receiptResult, dict) and "error" in receiptResult:
        return receiptResult

    # Return both records
    return {"claim": claimResult, "receipt": receiptResult}
