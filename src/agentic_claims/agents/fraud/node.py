"""Fraud detection agent node — identifies duplicate and anomalous expense claims.

Pattern: Tool Call (Anthropic agentic pattern)

Workflow:
  1. Read extractedReceipt and intakeFindings from ClaimState
  2. Run three targeted DB queries via DB MCP (duplicate check, recent claims, merchant history)
  3. Apply rule-based exact duplicate check — short-circuits LLM if true
  4. For non-duplicates: call LLM with structured query results to produce a JSON fraud verdict
  5. Parse verdict into fraudFindings dict and write to state
  6. Write audit_log entry via DB MCP insertAuditLog

MCP servers used:
  - mcp-db (port 8002): executeQuery (via queryClaimsHistory helpers) and insertAuditLog
"""

import json
import logging
import statistics
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_claims.agents.fraud.prompts.fraudSystemPrompt import FRAUD_SYSTEM_PROMPT
from agentic_claims.agents.fraud.tools.queryClaimsHistory import (
    claimsByMerchantAndEmployee,
    exactDuplicateCheck,
    recentClaimsByEmployee,
)
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.agents.shared.utils import extractJsonBlock
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parseFraudResponse(rawContent: str) -> dict:
    """Parse LLM fraud response into structured findings dict.

    Falls back to 'suspicious / requiresReview' if JSON cannot be parsed.
    """
    jsonStr = extractJsonBlock(rawContent)
    if jsonStr:
        try:
            parsed = json.loads(jsonStr)
            return {
                "verdict": parsed.get("verdict", "suspicious"),
                "flags": parsed.get("flags", []),
                "duplicateClaims": parsed.get("duplicateClaims", []),
                "summary": parsed.get("summary", "Fraud check completed."),
                "rawLlmResponse": rawContent,
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("JSON parse failed for fraud response", extra={"error": str(e)})

    logger.warning("Defaulting fraud findings to suspicious (parse error)")
    return {
        "verdict": "suspicious",
        "flags": [],
        "duplicateClaims": [],
        "summary": "Fraud evaluation could not be parsed. Manual review required.",
        "rawLlmResponse": rawContent,
    }


# ---------------------------------------------------------------------------
# Rule-based pre-check (exact duplicate — no LLM needed)
# ---------------------------------------------------------------------------


def _isExactDuplicate(duplicates: list[dict]) -> tuple[bool, list[str]]:
    """Return (True, [claim_numbers]) if real duplicate rows were found."""
    realDupes = [row for row in duplicates if isinstance(row, dict) and "error" not in row]
    if realDupes:
        claimNums = [row.get("claim_number", str(row.get("id", "?"))) for row in realDupes]
        return True, claimNums
    return False, []


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _computeAverage(merchantHistory: list[dict]) -> float | None:
    """Compute average receipt_amount from merchant history rows."""
    amounts = []
    for row in merchantHistory:
        val = row.get("receipt_amount") or row.get("total_amount")
        if val is not None:
            try:
                amounts.append(float(val))
            except (TypeError, ValueError):
                pass
    if len(amounts) > 1:
        return round(statistics.mean(amounts), 2)
    return None


def _countMerchantIn30Days(recentClaims: list[dict], merchant: str) -> int:
    """Count how many recent claims are from the specified merchant."""
    return sum(
        1
        for row in recentClaims
        if isinstance(row, dict) and merchant.lower() in str(row.get("merchant", "")).lower()
    )


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def fraudNode(state: ClaimState) -> dict:
    """Detect duplicate and anomalous expense claims.

    Runs three DB queries to gather evidence, then calls the LLM to reason
    about the combined signals. An exact duplicate match short-circuits the
    LLM call — the rule-based verdict is always used in that case.

    Args:
        state: ClaimState — expects extractedReceipt and intakeFindings to be
               set by the intake agent before this node runs.

    Returns:
        Partial state update:
          - messages: one AIMessage summarising the fraud verdict
          - fraudFindings: structured dict (verdict, flags, duplicateClaims, summary)
    """
    settings = getSettings()
    claimId = state.get("claimId", "unknown")
    dbClaimId = state.get("dbClaimId")
    logger.info("fraudNode started", extra={"claimId": claimId})

    # Write start audit entry so the timeline shows "Processing"
    if dbClaimId is not None:
        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": "fraud_check_start",
                    "newValue": json.dumps({"status": "processing"}),
                    "actor": "fraud_agent",
                    "oldValue": "",
                },
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 1. Read claim context from state
    # ------------------------------------------------------------------
    extractedReceipt = state.get("extractedReceipt") or {}
    intakeFindings = state.get("intakeFindings") or {}

    receiptFields = extractedReceipt.get("fields", {})
    employeeId = intakeFindings.get("employeeId") or receiptFields.get("employeeId", "unknown")
    merchant = receiptFields.get("merchant", "unknown")
    receiptDate = receiptFields.get("date") or receiptFields.get("receiptDate", "")
    totalAmountSgd = (
        receiptFields.get("totalAmountSgd")
        or receiptFields.get("amountSgd")
        or receiptFields.get("totalAmount")
        or 0.0
    )

    logger.info(
        "Fraud check context",
        extra={
            "employeeId": employeeId,
            "merchant": merchant,
            "date": receiptDate,
            "amount": totalAmountSgd,
        },
    )

    # ------------------------------------------------------------------
    # 2. Run DB queries in sequence (all read-only via DB MCP)
    # ------------------------------------------------------------------
    duplicates, recentClaims, merchantHistory = await _runDbQueries(
        employeeId, merchant, receiptDate, totalAmountSgd, dbClaimId
    )

    # ------------------------------------------------------------------
    # 3. Rule-based exact duplicate check (bypasses LLM)
    # ------------------------------------------------------------------
    isDuplicate, duplicateClaimNums = _isExactDuplicate(duplicates)
    if isDuplicate:
        logger.info(
            "Exact duplicate detected — short-circuiting LLM",
            extra={"duplicates": duplicateClaimNums, "claimId": claimId},
        )
        fraudFindings = {
            "verdict": "duplicate",
            "flags": [
                {
                    "type": "duplicate",
                    "description": f"Exact duplicate of: {', '.join(duplicateClaimNums)}",
                    "confidence": "high",
                    "relatedClaimNumber": duplicateClaimNums[0] if duplicateClaimNums else None,
                }
            ],
            "duplicateClaims": duplicateClaimNums,
            "summary": f"Exact duplicate of existing claim(s): {', '.join(duplicateClaimNums)}",
            "rawLlmResponse": None,
        }
        await _writeAuditLog(settings, dbClaimId, claimId, fraudFindings)
        return {
            "messages": [
                AIMessage(content=f"**Fraud Check**: DUPLICATE — {fraudFindings['summary']}")
            ],
            "fraudFindings": fraudFindings,
        }

    # ------------------------------------------------------------------
    # 4. Build LLM context for anomaly / near-duplicate reasoning
    # ------------------------------------------------------------------
    avgMerchantAmount = _computeAverage(merchantHistory)
    merchantFrequency30d = _countMerchantIn30Days(recentClaims, merchant)

    llmContext = {
        "currentClaim": {
            "claimId": claimId,
            "employeeId": employeeId,
            "merchant": merchant,
            "receiptDate": receiptDate,
            "totalAmountSgd": totalAmountSgd,
        },
        "exactDuplicateResults": duplicates,
        "recentClaims30Days": recentClaims,
        "merchantHistory": merchantHistory,
        "statistics": {
            "averageAmountAtMerchant": avgMerchantAmount,
            "claimsAtMerchantLast30Days": merchantFrequency30d,
            "totalClaimsLast30Days": len(recentClaims),
        },
    }

    fraudPrompt = (
        "## Current Claim Under Review\n\n"
        f"```json\n{json.dumps(llmContext, indent=2, default=str)}\n```\n\n"
        "Assess whether this claim is legitimate, suspicious, or a duplicate.\n"
        "Return ONLY the JSON verdict object — no preamble, no markdown fences.\n"
        "/no_think"
    )

    # ------------------------------------------------------------------
    # 5. Call LLM with 402 fallback
    # ------------------------------------------------------------------
    modelName = settings.openrouter_model_llm
    llm = buildAgentLlm(settings, temperature=0.1)
    llmMessages = [
        SystemMessage(content=FRAUD_SYSTEM_PROMPT),
        HumanMessage(content=fraudPrompt),
    ]

    logger.info(
        "fraudNode LLM request",
        extra={
            "claimId": claimId,
            "model": modelName,
            "systemPrompt": FRAUD_SYSTEM_PROMPT,
            "userPrompt": fraudPrompt,
        },
    )
    llmStartTime = time.time()

    try:
        response = await llm.ainvoke(llmMessages)
        rawContent = response.content
        llmElapsed = round(time.time() - llmStartTime, 2)

        logger.info(
            "fraudNode LLM response",
            extra={
                "claimId": claimId,
                "model": modelName,
                "elapsedSeconds": llmElapsed,
                "responseLength": len(rawContent) if rawContent else 0,
                "rawResponse": rawContent[:2000] if rawContent else None,
            },
        )

    except Exception as e:
        llmElapsed = round(time.time() - llmStartTime, 2)
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM returned 402 in fraudNode — falling back",
                extra={"error": errorStr, "elapsedSeconds": llmElapsed},
            )
            llm = buildAgentLlm(settings, temperature=0.1, useFallback=True)
            try:
                response = await llm.ainvoke(llmMessages)
                rawContent = response.content
            except Exception as fallbackErr:
                logger.error(
                    "Fallback LLM also failed in fraudNode",
                    extra={"error": str(fallbackErr)},
                    exc_info=True,
                )
                rawContent = None
        else:
            logger.error(
                "LLM call failed in fraudNode",
                extra={"error": errorStr, "elapsedSeconds": llmElapsed},
                exc_info=True,
            )
            rawContent = None

    # Handle LLM failure: return a conservative requiresReview verdict so the
    # graph can continue to advisor instead of crashing.
    if rawContent is None:
        fraudFindings = {
            "verdict": "suspicious",
            "flags": [],
            "duplicateClaims": [],
            "summary": (
                "Fraud check could not be completed (LLM unavailable). Manual review required."
            ),
            "rawLlmResponse": None,
        }
        logger.warning("fraudNode returning error fallback verdict", extra={"claimId": claimId})
        await _writeAuditLog(settings, dbClaimId, claimId, fraudFindings)
        return {
            "messages": [
                AIMessage(
                    content="**Fraud Check**: SUSPICIOUS — LLM unavailable. Manual review required."
                )
            ],
            "fraudFindings": fraudFindings,
        }

    # ------------------------------------------------------------------
    # 6. Parse response
    # ------------------------------------------------------------------
    fraudFindings = _parseFraudResponse(rawContent)

    verdict = fraudFindings.get("verdict", "unknown").upper()
    summary = fraudFindings.get("summary", "")
    logger.info("fraudNode completed", extra={"claimId": claimId, "verdict": verdict})

    await _writeAuditLog(settings, dbClaimId, claimId, fraudFindings)

    return {
        "messages": [AIMessage(content=f"**Fraud Check**: {verdict} — {summary}")],
        "fraudFindings": fraudFindings,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _runDbQueries(
    employeeId: str,
    merchant: str,
    receiptDate: str,
    amountSgd: float,
    excludeClaimId: int | None = None,
) -> tuple[list, list, list]:
    """Run the three DB queries needed for fraud assessment.

    Returns (duplicates, recentClaims, merchantHistory).
    Errors in individual queries are logged and return empty lists so that
    a single DB failure does not crash the whole fraud check.
    """
    try:
        duplicates = await exactDuplicateCheck(
            employeeId,
            merchant,
            receiptDate,
            amountSgd,
            excludeClaimId=excludeClaimId,
        )
    except Exception as e:
        logger.error("exactDuplicateCheck failed", extra={"error": str(e)}, exc_info=True)
        duplicates = []

    try:
        recentClaims = await recentClaimsByEmployee(employeeId, days=30)
    except Exception as e:
        logger.error("recentClaimsByEmployee failed", extra={"error": str(e)}, exc_info=True)
        recentClaims = []

    try:
        merchantHistory = await claimsByMerchantAndEmployee(employeeId, merchant)
    except Exception as e:
        logger.error("claimsByMerchantAndEmployee failed", extra={"error": str(e)}, exc_info=True)
        merchantHistory = []

    return duplicates, recentClaims, merchantHistory


async def _writeAuditLog(settings, dbClaimId, claimId: str, fraudFindings: dict) -> None:
    """Write a fraud_check audit log entry — non-fatal on failure."""
    if dbClaimId is None:
        return
    try:
        auditValue = json.dumps(
            {
                "verdict": fraudFindings.get("verdict"),
                "flags": fraudFindings.get("flags"),
                "summary": fraudFindings.get("summary"),
            }
        )
        await mcpCallTool(
            serverUrl=settings.db_mcp_url,
            toolName="insertAuditLog",
            arguments={
                "claimId": dbClaimId,
                "action": "fraud_check",
                "newValue": auditValue,
                "actor": "fraud_agent",
                "oldValue": "",
            },
        )
        logger.debug("Fraud audit log written", extra={"claimId": claimId, "dbClaimId": dbClaimId})
    except Exception as e:
        logger.warning(
            "Failed to write fraud audit log — continuing",
            extra={"claimId": claimId, "error": str(e)},
        )
