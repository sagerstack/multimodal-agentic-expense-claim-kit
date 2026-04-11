"""Claim submission tool using DB MCP server."""

import json
import logging
import time
import uuid
from datetime import datetime

from langchain_core.tools import tool

from agentic_claims.agents.intake.auditLogger import flushSteps
from agentic_claims.agents.intake.extractionContext import extractedReceiptVar, sessionClaimIdVar
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.web.employeeIdContext import employeeIdVar
from agentic_claims.web.imagePathContext import imagePathVar

logger = logging.getLogger(__name__)

# Field mapping: agent vocabulary -> MCP parameter names
CLAIM_FIELD_MAP = {
    "claimantId": "employeeId",
    "employeeId": "employeeId",
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
async def submitClaim(
    claimData: dict,
    receiptData: dict,
    intakeFindings: dict | None = None,
    threadId: str | None = None,
    sessionClaimId: str | None = None,
) -> dict:
    """Submit a claim and its receipt to the database atomically.

    Args:
        claimData: Claim fields using agent vocabulary:
            - claimantId (required, maps to employeeId)
            - amountSgd (required, maps to totalAmount)
            - status (optional, defaults to 'pending')
            - currency (optional, defaults to 'SGD')
            - expenseDate (optional)
            - originalAmount, originalCurrency, convertedAmount, exchangeRate,
              conversionDate (optional)
        receiptData: Receipt fields using agent vocabulary:
            - merchant (required)
            - date (required, maps to receiptDate)
            - totalAmount (required, maps to receiptTotalAmount)
            - currency (optional, maps to receiptCurrency)
            - lineItems or items (optional)
            - taxAmount, paymentMethod, imagePath (optional)
        intakeFindings: Agent observations (mismatches, overrides, red flags) for audit trail
        threadId: Conversation thread ID for idempotency (optional)
        sessionClaimId: Session-scoped UUID for flushing buffered audit steps (optional)

    Returns:
        Dict with "claim" and "receipt" keys containing the inserted records,
        or note key if duplicate detected, or error dict if submission fails
    """
    settings = getSettings()
    toolStart = time.time()

    # Server-side employee ID override (BUG-015 fix)
    serverEmployeeId = employeeIdVar.get(None)
    if serverEmployeeId:
        logEvent(
            logger,
            "claim.employee_id_injected",
            logCategory="agent",
            actorType="app",
            agent="intake",
            employeeId=serverEmployeeId,
            toolName="submitClaim",
            status="completed",
            payload={
                "serverEmployeeId": serverEmployeeId,
                "llmProvidedId": claimData.get("claimantId"),
            },
            message="Server-side employee ID override applied",
        )
        claimData["claimantId"] = serverEmployeeId

    # Server-side image path injection (BUG-020 fix)
    # The LLM does not reliably pass imagePath through receiptData, so we inject
    # it server-side from the context var set by the chat router. Only inject if
    # the receiptData does not already carry an imagePath.
    serverImagePath = imagePathVar.get(None)
    if serverImagePath and not receiptData.get("imagePath"):
        logger.info(
            "Server-side image path injection",
            extra={"serverImagePath": serverImagePath},
        )
        receiptData["imagePath"] = serverImagePath

    logEvent(
        logger,
        "claim.submission_started",
        logCategory="agent",
        actorType="agent",
        agent="intake",
        employeeId=serverEmployeeId,
        toolName="submitClaim",
        status="started",
        payload={
            "claimData": claimData,
            "receiptData": receiptData,
            "intakeFindings": intakeFindings,
        },
        message="Claim submission started",
    )

    # Build MCP arguments by mapping agent vocabulary to MCP parameter names
    mergedArgs = {}

    # Handle required fields with pass-through + fallback
    mergedArgs["status"] = claimData.get("status", "pending")
    mergedArgs["intakeFindings"] = intakeFindings or {}
    if serverEmployeeId:
        mergedArgs["intakeFindings"]["employeeId"] = serverEmployeeId

    # BUG-028: inject confidenceScores from VLM extraction context if LLM omitted them
    extractedReceipt = extractedReceiptVar.get(None)
    if extractedReceipt:
        findings = mergedArgs["intakeFindings"]
        if not findings.get("confidenceScores"):
            confidence = extractedReceipt.get("confidence") or extractedReceipt.get(
                "confidenceScores"
            )
            if confidence and isinstance(confidence, dict):
                findings["confidenceScores"] = confidence
                mergedArgs["intakeFindings"] = findings

    # Final submissions are intentionally non-idempotent. The DB MCP fallback
    # path creates a unique internal key when idempotencyKey is omitted, so
    # duplicate receipts produce separate claims and fraud detection handles
    # duplicate classification after insert.

    # If agent provides claimNumber, pass through but log warning (legacy path)
    if "claimNumber" in claimData:
        mergedArgs["claimNumber"] = claimData["claimNumber"]
        logger.warning(
            "Agent provided claimNumber (legacy behavior, DB should generate it)",
            extra={"claimNumber": claimData["claimNumber"]},
        )

    # Map claim fields through CLAIM_FIELD_MAP
    unmappedClaimKeys = []
    for agentKey, value in claimData.items():
        if agentKey in ("claimNumber", "status"):
            continue  # Already handled above

        if agentKey in CLAIM_FIELD_MAP:
            mcpKey = CLAIM_FIELD_MAP[agentKey]
            mergedArgs[mcpKey] = value
        elif agentKey in (
            "currency",
            "category",
            "originalAmount",
            "originalCurrency",
            "convertedAmount",
            "convertedCurrency",
            "exchangeRate",
            "conversionDate",
        ):
            # Pass through known MCP-accepted fields (currency, category, conversion)
            mergedArgs[agentKey] = value
        else:
            unmappedClaimKeys.append(agentKey)

    if unmappedClaimKeys:
        logger.warning("Unmapped claim keys", extra={"unmappedKeys": unmappedClaimKeys})

    # Validate and normalize category
    VALID_CATEGORIES = {"meals", "transport", "accommodation", "office_supplies", "general"}
    if "category" in mergedArgs and mergedArgs["category"] not in VALID_CATEGORIES:
        logger.warning("Invalid category from LLM", extra={"category": mergedArgs["category"]})
        mergedArgs["category"] = "general"

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

    # Auto-generate deterministic receiptNumber if receipt data exists but no receiptNumber provided
    if hasReceiptData and "receiptNumber" not in mergedArgs:
        # Use date-based receipt number for determinism
        receiptDate = mergedArgs.get("receiptDate", "")
        if receiptDate:
            mergedArgs["receiptNumber"] = f"REC-{receiptDate.replace('-', '')}"
        else:
            # Fallback if date missing
            mergedArgs["receiptNumber"] = f"REC-{uuid.uuid4().hex[:8]}"

    # Normalize receiptDate to YYYY-MM-DD format (PostgreSQL DATE column requirement)
    if "receiptDate" in mergedArgs and mergedArgs["receiptDate"]:
        rawDate = str(mergedArgs["receiptDate"])
        for fmt in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ):
            try:
                parsed = datetime.strptime(rawDate, fmt)
                mergedArgs["receiptDate"] = parsed.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # Ensure lineItems is a list (PostgreSQL JSONB expects valid JSON)
    if "lineItems" in mergedArgs and not isinstance(mergedArgs["lineItems"], list):
        mergedArgs["lineItems"] = [mergedArgs["lineItems"]] if mergedArgs["lineItems"] else []

    logEvent(
        logger,
        "tool.start",
        logCategory="agent",
        actorType="agent",
        agent="intake",
        employeeId=serverEmployeeId,
        toolName="insertClaim",
        mcpServer=settings.db_mcp_url,
        status="started",
        payload={"arguments": mergedArgs},
        message="Calling MCP insertClaim tool",
    )

    # Single atomic MCP call to insert both claim and receipt
    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url, toolName="insertClaim", arguments=mergedArgs
    )

    logEvent(
        logger,
        "tool.end",
        logCategory="agent",
        actorType="agent",
        agent="intake",
        employeeId=serverEmployeeId,
        toolName="insertClaim",
        mcpServer=settings.db_mcp_url,
        status="completed",
        elapsedMs=round((time.time() - toolStart) * 1000),
        payload={"result": result},
        message="MCP insertClaim tool completed",
    )

    # Handle string response: try parsing as JSON
    if isinstance(result, str):
        logger.info("Parsing string response as JSON", extra={"rawText": result[:200]})
        try:
            result = json.loads(result)
            logger.info("JSON parse successful", extra={"parsedType": type(result).__name__})
        except (ValueError, TypeError) as e:
            logEvent(
                logger,
                "claim.submission_failed",
                level=logging.ERROR,
                logCategory="agent",
                actorType="agent",
                agent="intake",
                employeeId=serverEmployeeId,
                toolName="submitClaim",
                status="failed",
                elapsedMs=round((time.time() - toolStart) * 1000),
                errorType=type(e).__name__,
                payload={"error": str(e), "result": result},
                message="Claim submission returned unparseable response",
            )
            return {"error": f"insertClaim returned unparseable response: {result[:200]}"}

    # Log tool exit
    if isinstance(result, dict):
        claimRecord = result.get("claim", {}) if isinstance(result.get("claim"), dict) else {}
        logEvent(
            logger,
            "claim.submission_failed" if "error" in result else "claim.submission_completed",
            level=logging.ERROR if "error" in result else logging.INFO,
            logCategory="agent",
            actorType="agent",
            agent="intake",
            employeeId=serverEmployeeId,
            dbClaimId=claimRecord.get("id"),
            claimNumber=claimRecord.get("claim_number") or claimRecord.get("claimNumber"),
            toolName="submitClaim",
            status="failed" if "error" in result else "completed",
            elapsedMs=round((time.time() - toolStart) * 1000),
            errorType="ToolError" if "error" in result else None,
            payload={"result": result},
            message="Claim submission failed"
            if "error" in result
            else "Claim submission completed",
        )
        # BUG-027: flush buffered audit steps now that the DB claim ID is known.
        # Use sessionClaimIdVar as fallback when LLM doesn't pass sessionClaimId.
        effectiveSessionClaimId = sessionClaimId or sessionClaimIdVar.get(None)
        if effectiveSessionClaimId and "claim" in result and isinstance(result["claim"], dict):
            dbClaimId = result["claim"].get("id")
            if dbClaimId:
                await flushSteps(sessionClaimId=effectiveSessionClaimId, dbClaimId=dbClaimId)
    else:
        logger.warning(
            "submitClaim tool returned unexpected type", extra={"resultType": type(result).__name__}
        )

    return result
