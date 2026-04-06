"""Compliance agent node — evaluates a submitted claim against SUTD expense policies.

Pattern: Evaluator (Anthropic agentic pattern)

Workflow (single node, no ReAct loop needed — evaluation is deterministic given context):
  1. Read extractedReceipt, violations, intakeFindings from ClaimState
  2. Query RAG MCP server for policy rules relevant to expense category + amount
  3. Call LLM (ChatOpenRouter) with full context to produce a structured JSON verdict
  4. Parse response into complianceFindings dict and write back to state
  5. Write audit_log entry via DB MCP insertAuditLog

MCP servers used:
  - mcp-rag (port 8001): searchPolicies tool
  - mcp-db (port 8002): insertAuditLog tool
"""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_claims.agents.compliance.prompts.complianceSystemPrompt import COMPLIANCE_SYSTEM_PROMPT
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.agents.shared.utils import extractJsonBlock
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _parseComplianceResponse(rawContent: str) -> dict:
    """Parse the LLM compliance response into a structured findings dict.

    Falls back to a conservative fail/requiresReview verdict if the response
    cannot be parsed as JSON — better to flag than to silently pass.
    """
    jsonStr = extractJsonBlock(rawContent)
    if jsonStr:
        try:
            parsed = json.loads(jsonStr)
            return {
                "verdict": parsed.get("verdict", "fail"),
                "violations": parsed.get("violations", []),
                "citedClauses": parsed.get("citedClauses", []),
                "requiresManagerApproval": parsed.get("requiresManagerApproval", False),
                "requiresDirectorApproval": parsed.get("requiresDirectorApproval", False),
                "summary": parsed.get("summary", "Compliance check completed."),
                "requiresReview": parsed.get("requiresReview", True),
                "rawLlmResponse": rawContent,
            }
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("JSON parse failed for compliance response", extra={"error": str(e)})

    logger.warning("Defaulting compliance findings to fail/requiresReview (parse error)")
    return {
        "verdict": "fail",
        "violations": [],
        "citedClauses": [],
        "requiresManagerApproval": False,
        "requiresDirectorApproval": False,
        "summary": "Compliance evaluation could not be parsed. Manual review required.",
        "requiresReview": True,
        "rawLlmResponse": rawContent,
    }


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def complianceNode(state: ClaimState) -> dict:
    """Evaluate claim compliance against SUTD expense policies.

    Reads claim context from state, fetches relevant policy rules via RAG MCP,
    calls the LLM to produce a structured compliance verdict, writes the
    complianceFindings to state, and logs a compliance_check audit entry.

    Args:
        state: ClaimState — expects extractedReceipt, violations, intakeFindings,
                            dbClaimId to be set by intake agent before this runs.

    Returns:
        Partial state update:
          - messages: one AIMessage summarising the verdict
          - complianceFindings: structured dict (verdict, violations, citedClauses, ...)
    """
    settings = getSettings()
    claimId = state.get("claimId", "unknown")
    logger.info("complianceNode started", extra={"claimId": claimId})

    # ------------------------------------------------------------------
    # 1. Read claim context from state
    # ------------------------------------------------------------------
    extractedReceipt = state.get("extractedReceipt") or {}
    intakeFindings = state.get("intakeFindings") or {}
    intakeViolations = state.get("violations") or []
    currencyConversion = state.get("currencyConversion")
    dbClaimId = state.get("dbClaimId")

    receiptFields = extractedReceipt.get("fields", {})
    category = receiptFields.get("category", "general")
    merchant = receiptFields.get("merchant", "unknown")

    totalAmountSgd = (
        receiptFields.get("totalAmountSgd")
        or receiptFields.get("amountSgd")
        or receiptFields.get("totalAmount")
        or 0.0
    )

    logger.info(
        "Claim context read",
        extra={"claimId": claimId, "category": category, "merchant": merchant, "amountSgd": totalAmountSgd},
    )

    # ------------------------------------------------------------------
    # 2. Fetch relevant policy rules via RAG MCP
    # ------------------------------------------------------------------
    policyQuery = f"{category} expense policy spending limit approval threshold budget {merchant}"
    logger.info("Querying RAG MCP for policy rules", extra={"query": policyQuery})

    policyResults = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": policyQuery, "limit": 8},
    )

    if isinstance(policyResults, dict) and "error" in policyResults:
        logger.warning(
            "RAG MCP returned error — proceeding with empty policy context",
            extra={"error": policyResults["error"]},
        )
        policyResults = []

    # ------------------------------------------------------------------
    # 3. Build evaluation context and LLM prompt
    # ------------------------------------------------------------------
    claimContext = {
        "claimId": claimId,
        "category": category,
        "merchant": merchant,
        "totalAmountSgd": totalAmountSgd,
        "receiptFields": receiptFields,
        "intakeViolations": intakeViolations,
        "intakeFindings": intakeFindings,
        "currencyConversion": currencyConversion,
    }

    evaluationPrompt = (
        "## Claim to Evaluate\n\n"
        f"```json\n{json.dumps(claimContext, indent=2, default=str)}\n```\n\n"
        "## Retrieved Policy Rules\n\n"
        f"```json\n{json.dumps(policyResults, indent=2, default=str)}\n```\n\n"
        "Evaluate the claim against the policy rules above.\n"
        "Return ONLY the JSON verdict object — no preamble, no markdown fences."
    )

    # ------------------------------------------------------------------
    # 4. Call LLM with 402 fallback
    # ------------------------------------------------------------------
    llm = buildAgentLlm(settings, temperature=0.1)
    try:
        response = await llm.ainvoke([
            SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT),
            HumanMessage(content=evaluationPrompt),
        ])
        rawContent = response.content

    except Exception as e:
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM returned 402 in complianceNode — falling back",
                extra={"primary": settings.openrouter_model_llm, "error": errorStr},
            )
            llm = buildAgentLlm(settings, temperature=0.1, useFallback=True)
            response = await llm.ainvoke([
                SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT),
                HumanMessage(content=evaluationPrompt),
            ])
            rawContent = response.content
        else:
            raise

    # ------------------------------------------------------------------
    # 5. Parse response into structured findings
    # ------------------------------------------------------------------
    complianceFindings = _parseComplianceResponse(rawContent)

    verdict = complianceFindings.get("verdict", "unknown").upper()
    summary = complianceFindings.get("summary", "")
    logger.info(
        "complianceNode completed",
        extra={"claimId": claimId, "verdict": verdict, "requiresReview": complianceFindings.get("requiresReview")},
    )

    # ------------------------------------------------------------------
    # 6. Write audit_log entry — non-fatal if it fails
    # ------------------------------------------------------------------
    if dbClaimId is not None:
        try:
            auditValue = json.dumps({
                "verdict": complianceFindings.get("verdict"),
                "violations": complianceFindings.get("violations"),
                "summary": summary,
            })
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": "compliance_check",
                    "newValue": auditValue,
                    "actor": "compliance_agent",
                    "oldValue": "",
                },
            )
            logger.debug("Compliance audit log written", extra={"claimId": claimId, "dbClaimId": dbClaimId})
        except Exception as e:
            logger.warning(
                "Failed to write compliance audit log — continuing",
                extra={"claimId": claimId, "error": str(e)},
            )

    summaryMsg = f"**Compliance Check**: {verdict} — {summary}"

    return {
        "messages": [AIMessage(content=summaryMsg)],
        "complianceFindings": complianceFindings,
    }
