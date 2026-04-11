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
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_claims.agents.compliance.prompts.complianceSystemPrompt import COMPLIANCE_SYSTEM_PROMPT
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.agents.shared.utils import extractJsonBlock
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
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
            logEvent(
                logger,
                "compliance.parse_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="compliance",
                message="JSON parse failed for compliance response",
                error=str(e),
            )

    logEvent(
        logger,
        "compliance.parse_fallback",
        level=logging.WARNING,
        logCategory="agent",
        agent="compliance",
        message="Defaulting compliance findings to fail/requiresReview (parse error)",
    )
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
    dbClaimId = state.get("dbClaimId")
    logEvent(
        logger,
        "compliance.started",
        logCategory="agent",
        agent="compliance",
        claimId=claimId,
        message="Compliance agent started",
    )

    # Write start audit entry so the timeline shows "Processing"
    if dbClaimId is not None:
        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": "compliance_check_start",
                    "newValue": json.dumps({"status": "processing"}),
                    "actor": "compliance_agent",
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
    intakeViolations = state.get("violations") or []
    currencyConversion = state.get("currencyConversion")

    receiptFields = extractedReceipt.get("fields", {})
    category = receiptFields.get("category", "general")
    merchant = receiptFields.get("merchant", "unknown")

    totalAmountSgd = (
        receiptFields.get("totalAmountSgd")
        or receiptFields.get("amountSgd")
        or receiptFields.get("totalAmount")
        or 0.0
    )

    logEvent(
        logger,
        "compliance.context_read",
        logCategory="agent",
        agent="compliance",
        claimId=claimId,
        category=category,
        merchant=merchant,
        amountSgd=totalAmountSgd,
        message="Claim context read",
    )

    # ------------------------------------------------------------------
    # 2. Fetch relevant policy rules via RAG MCP
    # ------------------------------------------------------------------
    policyQuery = f"{category} expense policy spending limit approval threshold budget {merchant}"
    logEvent(
        logger,
        "compliance.rag_query",
        logCategory="agent",
        agent="compliance",
        claimId=claimId,
        query=policyQuery,
        message="Querying RAG MCP for policy rules",
    )

    policyResults = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": policyQuery, "limit": 8},
    )

    if isinstance(policyResults, dict) and "error" in policyResults:
        logEvent(
            logger,
            "compliance.rag_error",
            level=logging.WARNING,
            logCategory="agent",
            agent="compliance",
            claimId=claimId,
            error=policyResults["error"],
            message="RAG MCP returned error — proceeding with empty policy context",
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
        "Return ONLY the JSON verdict object — no preamble, no markdown fences.\n"
        "/no_think"
    )

    # ------------------------------------------------------------------
    # 4. Call LLM with 402 fallback
    # ------------------------------------------------------------------
    modelName = settings.openrouter_model_llm
    llm = buildAgentLlm(settings, temperature=0.1)
    llmMessages = [
        SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT),
        HumanMessage(content=evaluationPrompt),
    ]

    # Log the exact SDK params to debug why OpenRouter takes 500s vs 0.1s direct
    sdkParams = llm._default_params
    try:
        sdkParamsLog = {k: str(v)[:200] for k, v in sdkParams.items()}
    except Exception:
        sdkParamsLog = {}
    logEvent(
        logger,
        "compliance.llm_request",
        logCategory="agent",
        agent="compliance",
        claimId=claimId,
        model=modelName,
        payload={
            "systemPrompt": COMPLIANCE_SYSTEM_PROMPT,
            "userPrompt": evaluationPrompt,
            "sdkParams": sdkParamsLog,
        },
        message="Compliance LLM request",
    )
    llmStartTime = time.time()

    try:
        response = await llm.ainvoke(llmMessages)
        rawContent = response.content
        llmElapsed = round(time.time() - llmStartTime, 2)

        logEvent(
            logger,
            "compliance.llm_response",
            logCategory="agent",
            agent="compliance",
            claimId=claimId,
            model=modelName,
            elapsedSeconds=llmElapsed,
            responseLength=len(rawContent) if rawContent else 0,
            payload={"rawResponse": rawContent[:2000] if rawContent else None},
            message="Compliance LLM response",
        )

    except Exception as e:
        llmElapsed = round(time.time() - llmStartTime, 2)
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logEvent(
                logger,
                "compliance.llm_402_fallback",
                level=logging.WARNING,
                logCategory="agent",
                agent="compliance",
                claimId=claimId,
                model=settings.openrouter_model_llm,
                elapsedSeconds=llmElapsed,
                error=errorStr,
                message="Primary LLM returned 402 in complianceNode — falling back",
            )
            llm = buildAgentLlm(settings, temperature=0.1, useFallback=True)
            try:
                response = await llm.ainvoke(llmMessages)
                rawContent = response.content
            except Exception as fallbackErr:
                logEvent(
                    logger,
                    "compliance.llm_fallback_error",
                    level=logging.ERROR,
                    logCategory="agent",
                    agent="compliance",
                    claimId=claimId,
                    error=str(fallbackErr),
                    message="Fallback LLM also failed in complianceNode",
                )
                rawContent = None
        else:
            logEvent(
                logger,
                "compliance.llm_error",
                level=logging.ERROR,
                logCategory="agent",
                agent="compliance",
                claimId=claimId,
                elapsedSeconds=llmElapsed,
                error=errorStr,
                message="LLM call failed in complianceNode",
            )
            rawContent = None

    # Handle LLM failure: return a conservative requiresReview verdict so the
    # graph can continue to fraud + advisor instead of crashing.
    if rawContent is None:
        complianceFindings = {
            "verdict": "error",
            "violations": [],
            "citedClauses": [],
            "requiresReview": True,
            "summary": "Compliance check could not be completed (LLM unavailable). Manual review required.",
        }
        logEvent(
            logger,
            "compliance.fallback",
            level=logging.WARNING,
            logCategory="agent",
            agent="compliance",
            claimId=claimId,
            message="complianceNode returning error fallback verdict",
        )

        if dbClaimId is not None:
            try:
                auditValue = json.dumps({
                    "verdict": "error",
                    "violations": [],
                    "summary": complianceFindings["summary"],
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
            except Exception:
                pass

        return {
            "messages": [AIMessage(content="**Compliance Check**: ERROR — LLM unavailable. Manual review required.")],
            "complianceFindings": complianceFindings,
        }

    # ------------------------------------------------------------------
    # 5. Parse response into structured findings
    # ------------------------------------------------------------------
    complianceFindings = _parseComplianceResponse(rawContent)

    verdict = complianceFindings.get("verdict", "unknown").upper()
    summary = complianceFindings.get("summary", "")
    logEvent(
        logger,
        "compliance.completed",
        logCategory="agent",
        agent="compliance",
        claimId=claimId,
        verdict=verdict,
        requiresReview=complianceFindings.get("requiresReview"),
        message="Compliance agent completed",
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
            logEvent(
                logger,
                "compliance.audit_log_written",
                level=logging.DEBUG,
                logCategory="agent",
                agent="compliance",
                claimId=claimId,
                dbClaimId=dbClaimId,
                message="Compliance audit log written",
            )
        except Exception as e:
            logEvent(
                logger,
                "compliance.audit_log_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="compliance",
                claimId=claimId,
                error=str(e),
                message="Failed to write compliance audit log — continuing",
            )

    summaryMsg = f"**Compliance Check**: {verdict} — {summary}"

    return {
        "messages": [AIMessage(content=summaryMsg)],
        "complianceFindings": complianceFindings,
    }
