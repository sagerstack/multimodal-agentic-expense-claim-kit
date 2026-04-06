"""Compliance agent node — evaluates a submitted claim against SUTD expense policies.

Author: jamesoon
Pattern: Evaluator (Anthropic agentic pattern)

Workflow (single node, no ReAct loop needed — evaluation is deterministic given context):
  1. Read extractedReceipt, violations, intakeFindings from ClaimState
  2. Query RAG MCP server for policy rules relevant to expense category + amount
  3. Call LLM (ChatOpenRouter) with full context to produce a structured JSON verdict
  4. Parse response into complianceFindings dict and write back to state

MCP servers used:
  - mcp-rag (port 8001): searchPolicies tool
"""

import json
import logging
import re

import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter

from agentic_claims.agents.compliance.prompts.complianceSystemPrompt import COMPLIANCE_SYSTEM_PROMPT
# Reuse the shared MCP client — no new infrastructure needed
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _buildComplianceLlm(settings, useFallback: bool = False) -> ChatOpenRouter:
    """Instantiate ChatOpenRouter for the compliance evaluator.

    Low temperature (0.1) for deterministic, consistent policy verdicts.
    Falls back to secondary model on 402 quota errors (same pattern as intake).
    """
    modelName = (
        settings.openrouter_fallback_model_llm if useFallback
        else settings.openrouter_model_llm
    )

    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=0.1,  # Low — compliance verdicts must be consistent
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Bypass SSL verification (Zscaler corporate proxy) — same workaround as intake node
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    return llm


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------


def _extractJsonBlock(text: str) -> str | None:
    """Pull the first JSON object out of an LLM response string.

    Handles both ```json fenced blocks and raw inline JSON objects.
    """
    # 1. Try fenced code block: ```json { ... } ```
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)

    # 2. Try bare JSON object spanning the whole string
    raw = re.search(r"\{.*\}", text, re.DOTALL)
    if raw:
        return raw.group(0)

    return None


def _parseComplianceResponse(rawContent: str) -> dict:
    """Parse the LLM compliance response into a structured findings dict.

    Falls back to a conservative "fail / requiresReview" verdict if the
    response cannot be parsed as JSON — better to flag than to silently pass.
    """
    jsonStr = _extractJsonBlock(rawContent)
    if jsonStr:
        try:
            parsed = json.loads(jsonStr)
            # Normalise to expected schema, providing safe defaults for any missing keys
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

    # Safe fallback — conservative: mark for review, do not auto-approve
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
    then calls the LLM to produce a structured compliance verdict.

    Args:
        state: ClaimState — expects extractedReceipt, violations, intakeFindings to be set
                            by the intake agent before this node runs.

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

    receiptFields = extractedReceipt.get("fields", {})
    category = receiptFields.get("category", "general")
    merchant = receiptFields.get("merchant", "unknown")

    # Prefer SGD total; fall back through common field names
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
    # Build a rich query to maximise recall of relevant clauses
    policyQuery = (
        f"{category} expense policy spending limit approval threshold budget {merchant}"
    )
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
    # 3. Build evaluation context for the LLM
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
    # 4. Call LLM with 402 fallback (same pattern as intake node)
    # ------------------------------------------------------------------
    llm = _buildComplianceLlm(settings)
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
            llm = _buildComplianceLlm(settings, useFallback=True)
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

    # Human-readable message appended to conversation (visible in Chainlit thinking panel)
    summaryMsg = f"**Compliance Check**: {verdict} — {summary}"

    return {
        "messages": [AIMessage(content=summaryMsg)],
        "complianceFindings": complianceFindings,
    }
