"""Claim submission tool using DB MCP server."""

import json
import logging
import random
from datetime import datetime

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)

# Field mapping: agent vocabulary -> MCP parameter names
CLAIM_FIELD_MAP = {
    "claimantId": "employeeId",
    "amountSgd": "totalAmount",
}

RECEIPT_FIELD_MAP = {
    "merchant": "merchant",
    "date": "receiptDate",
    "totalAmount": "receiptTotalAmount",
    "currency": "receiptCurrency",
    "lineItems": "lineItems",
    "items": "lineItems",
    "taxAmount": "taxAmount",
    "paymentMethod": "paymentMethod",
    "imagePath": "imagePath",
}


@tool
async def submitClaim(claimData: dict, receiptData: dict, intakeFindings: dict | None = None) -> dict:
    """Submit a claim and its receipt to the database atomically.

    Args:
        claimData: Claim fields using agent vocabulary:
            - claimantId (required, maps to employeeId)
            - amountSgd (required, maps to totalAmount)
            - claimNumber (optional, auto-generated if missing)
            - status (optional, defaults to 'pending')
            - currency (optional, defaults to 'SGD')
            - expenseDate (optional)
            - originalAmount, originalCurrency, convertedAmount, exchangeRate, conversionDate (optional)
        receiptData: Receipt fields using agent vocabulary:
            - merchant (required)
            - date (required, maps to receiptDate)
            - totalAmount (required, maps to receiptTotalAmount)
            - currency (optional, maps to receiptCurrency)
            - lineItems or items (optional)
            - taxAmount, paymentMethod, imagePath (optional)
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

    # Build MCP arguments by mapping agent vocabulary to MCP parameter names
    mergedArgs = {}

    # Handle required fields with pass-through + fallback
    mergedArgs["claimNumber"] = claimData.get("claimNumber", f"CLAIM-{random.randint(1, 999):03d}")
    mergedArgs["status"] = claimData.get("status", "pending")
    mergedArgs["intakeFindings"] = intakeFindings or {}

    # Map claim fields through CLAIM_FIELD_MAP
    unmappedClaimKeys = []
    for agentKey, value in claimData.items():
        if agentKey in ("claimNumber", "status"):
            continue  # Already handled above

        if agentKey in CLAIM_FIELD_MAP:
            mcpKey = CLAIM_FIELD_MAP[agentKey]
            mergedArgs[mcpKey] = value
        elif agentKey in ("currency", "originalAmount", "originalCurrency", "convertedAmount",
                          "convertedCurrency", "exchangeRate", "conversionDate"):
            # Pass through known MCP-accepted currency conversion fields
            mergedArgs[agentKey] = value
        else:
            unmappedClaimKeys.append(agentKey)

    if unmappedClaimKeys:
        logger.warning("Unmapped claim keys", extra={"unmappedKeys": unmappedClaimKeys})

    # Map receipt fields through RECEIPT_FIELD_MAP
    unmappedReceiptKeys = []
    hasReceiptData = False
    for agentKey, value in receiptData.items():
        if agentKey in RECEIPT_FIELD_MAP:
            mcpKey = RECEIPT_FIELD_MAP[agentKey]
            mergedArgs[mcpKey] = value
            hasReceiptData = True
        elif agentKey == "receiptNumber":
            # Pass through receiptNumber
            mergedArgs["receiptNumber"] = value
            hasReceiptData = True
        else:
            unmappedReceiptKeys.append(agentKey)

    if unmappedReceiptKeys:
        logger.warning("Unmapped receipt keys", extra={"unmappedKeys": unmappedReceiptKeys})

    # Auto-generate receiptNumber if receipt data exists but no receiptNumber provided
    if hasReceiptData and "receiptNumber" not in mergedArgs:
        mergedArgs["receiptNumber"] = f"REC-{random.randint(1, 999):03d}"

    # Normalize receiptDate to YYYY-MM-DD format (PostgreSQL DATE column requirement)
    if "receiptDate" in mergedArgs and mergedArgs["receiptDate"]:
        rawDate = str(mergedArgs["receiptDate"])
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
            try:
                parsed = datetime.strptime(rawDate, fmt)
                mergedArgs["receiptDate"] = parsed.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # Ensure lineItems is a list (PostgreSQL JSONB expects valid JSON)
    if "lineItems" in mergedArgs and not isinstance(mergedArgs["lineItems"], list):
        mergedArgs["lineItems"] = [mergedArgs["lineItems"]] if mergedArgs["lineItems"] else []

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
