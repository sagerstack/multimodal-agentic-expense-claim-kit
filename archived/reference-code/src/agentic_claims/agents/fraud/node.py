"""Fraud detection agent node — identifies duplicate and anomalous expense claims.

Author: jamesoon
Pattern: Tool Call (Anthropic agentic pattern)

Workflow:
  1. Read extractedReceipt and intakeFindings from ClaimState
  2. Run three targeted DB queries via DB MCP (duplicate check, recent claims, merchant history)
  3. Call LLM with structured query results to produce a JSON fraud verdict
  4. Parse verdict into fraudFindings dict and write to state

MCP servers used:
  - mcp-db (port 8002): executeQuery tool (SELECT-only) via queryClaimsHistory helpers

The LLM step adds reasoning for edge cases (near-duplicates, amount anomalies).
For an exact duplicate match, the verdict is set deterministically before the LLM call
to avoid hallucination (rule always beats model output).
"""

import json
import logging
import re
import statistics

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter

from agentic_claims.agents.fraud.prompts.fraudSystemPrompt import FRAUD_SYSTEM_PROMPT
from agentic_claims.agents.fraud.tools.queryClaimsHistory import (
    claimsByMerchantAndEmployee,
    exactDuplicateCheck,
    recentClaimsByEmployee,
)
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _buildFraudLlm(settings, useFallback: bool = False) -> ChatOpenRouter:
    """Instantiate ChatOpenRouter for fraud reasoning.

    Low temperature for deterministic verdicts.
    """
    modelName = (
        settings.openrouter_fallback_model_llm if useFallback
        else settings.openrouter_model_llm
    )

    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=0.1,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Bypass SSL verification (Zscaler corporate proxy) — same workaround as intake node
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    return llm


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _extractJsonBlock(text: str) -> str | None:
    """Extract first JSON object from LLM response (handles fences and raw JSON)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    raw = re.search(r"\{.*\}", text, re.DOTALL)
    if raw:
        return raw.group(0)
    return None


def _parseFraudResponse(rawContent: str) -> dict:
    """Parse LLM fraud response into structured findings dict.

    Falls back to 'suspicious / requiresReview' if JSON cannot be parsed.
    """
    jsonStr = _extractJsonBlock(rawContent)
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
    realDupes = [
        row for row in duplicates
        if isinstance(row, dict) and "error" not in row
    ]
    if realDupes:
        claimNums = [row.get("claim_number", str(row.get("id", "?"))) for row in realDupes]
        return True, claimNums
    return False, []


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
    logger.info("fraudNode started", extra={"claimId": claimId})

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
        extra={"employeeId": employeeId, "merchant": merchant, "date": receiptDate, "amount": totalAmountSgd},
    )

    # ------------------------------------------------------------------
    # 2. Run DB queries in sequence (all read-only via DB MCP)
    # ------------------------------------------------------------------
    duplicates, recentClaims, merchantHistory = await _runDbQueries(
        employeeId, merchant, receiptDate, totalAmountSgd
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
            "flags": [{
                "type": "duplicate",
                "description": f"Exact duplicate of: {', '.join(duplicateClaimNums)}",
                "confidence": "high",
                "relatedClaimNumber": duplicateClaimNums[0] if duplicateClaimNums else None,
            }],
            "duplicateClaims": duplicateClaimNums,
            "summary": f"Exact duplicate of existing claim(s): {', '.join(duplicateClaimNums)}",
            "rawLlmResponse": None,
        }
        return {
            "messages": [AIMessage(content=f"**Fraud Check**: DUPLICATE — {fraudFindings['summary']}")],
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
        "Return ONLY the JSON verdict object — no preamble, no markdown fences."
    )

    # ------------------------------------------------------------------
    # 5. Call LLM with 402 fallback
    # ------------------------------------------------------------------
    llm = _buildFraudLlm(settings)
    try:
        response = await llm.ainvoke([
            SystemMessage(content=FRAUD_SYSTEM_PROMPT),
            HumanMessage(content=fraudPrompt),
        ])
        rawContent = response.content

    except Exception as e:
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM returned 402 in fraudNode — falling back",
                extra={"error": errorStr},
            )
            llm = _buildFraudLlm(settings, useFallback=True)
            response = await llm.ainvoke([
                SystemMessage(content=FRAUD_SYSTEM_PROMPT),
                HumanMessage(content=fraudPrompt),
            ])
            rawContent = response.content
        else:
            raise

    # ------------------------------------------------------------------
    # 6. Parse response
    # ------------------------------------------------------------------
    fraudFindings = _parseFraudResponse(rawContent)

    verdict = fraudFindings.get("verdict", "unknown").upper()
    summary = fraudFindings.get("summary", "")
    logger.info(
        "fraudNode completed",
        extra={"claimId": claimId, "verdict": verdict},
    )

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
) -> tuple[list, list, list]:
    """Run the three DB queries needed for fraud assessment.

    Returns (duplicates, recentClaims, merchantHistory).
    Errors in individual queries are logged and return empty lists so that
    a single DB failure does not crash the whole fraud check.
    """
    try:
        duplicates = await exactDuplicateCheck(employeeId, merchant, receiptDate, amountSgd)
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
        1 for row in recentClaims
        if isinstance(row, dict) and merchant.lower() in str(row.get("merchant", "")).lower()
    )
