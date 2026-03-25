"""Claim submission tool using DB MCP server."""

import json
import logging

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)


@tool
async def submitClaim(claimData: dict, receiptData: dict, intakeFindings: dict | None = None) -> dict:
    """Submit a claim and its receipt to the database atomically.

    Args:
        claimData: Claim fields (employeeId, totalAmount, currency, etc.)
        receiptData: Receipt fields (merchant, date, totalAmount, currency, lineItems, etc.)
        intakeFindings: Agent observations (mismatches, overrides, red flags) for audit trail

    Returns:
        Dict with "claim" and "receipt" keys containing the inserted records,
        or error dict if submission fails
    """
    settings = getSettings()

    # Log tool entry
    logger.info(
        "submitClaim tool called",
        extra={
            "claimDataKeys": list(claimData.keys()),
            "receiptDataKeys": list(receiptData.keys()),
            "hasFindingsData": intakeFindings is not None,
        }
    )

    # Merge all data into single MCP call arguments
    mergedArgs = {
        **claimData,
        **{f"receipt{k[0].upper()}{k[1:]}": v for k, v in receiptData.items()},
        "intakeFindings": intakeFindings or {},
    }

    # Log before MCP call
    logger.info(
        "Calling MCP insertClaim tool",
        extra={
            "serverUrl": settings.db_mcp_url,
            "toolName": "insertClaim",
            "argumentKeys": list(mergedArgs.keys()),
        }
    )

    # Single atomic MCP call to insert both claim and receipt
    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="insertClaim",
        arguments=mergedArgs
    )

    # Log result type
    logger.info(
        "MCP call completed",
        extra={
            "resultType": type(result).__name__,
            "resultPreview": str(result)[:200] if not isinstance(result, dict) else None,
        }
    )

    # Handle string response: try parsing as JSON
    if isinstance(result, str):
        logger.info("Parsing string response as JSON", extra={"rawText": result[:200]})
        try:
            result = json.loads(result)
            logger.info("JSON parse successful", extra={"parsedType": type(result).__name__})
        except (ValueError, TypeError) as e:
            logger.error("JSON parse failed", extra={"error": str(e)}, exc_info=True)
            return {"error": f"insertClaim returned unparseable response: {result[:200]}"}

    # Log tool exit
    if isinstance(result, dict):
        logger.info(
            "submitClaim tool completed",
            extra={
                "success": "error" not in result,
                "hasClaimData": "claim" in result,
                "hasReceiptData": "receipt" in result,
            }
        )
    else:
        logger.warning(
            "submitClaim tool returned unexpected type",
            extra={"resultType": type(result).__name__}
        )

    return result
