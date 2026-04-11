"""Advisor agent node — Reflection + Routing decision for submitted claims.

Pattern: Reflection + Routing (Anthropic agentic pattern)

Workflow:
  1. Read complianceFindings and fraudFindings from ClaimState (written by parallel agents)
  2. Read dbClaimId directly from state (written by intakeNode after submitClaim)
  3. Build context message for the ReAct agent
  4. Invoke agent (with 402 fallback) to: optionally search policies, update claim
     status via DB MCP
  5. Extract advisorDecision from agent output messages
  6. Write advisor_decision audit_log entry via DB MCP insertAuditLog
  7. Return summary AIMessage only (message hygiene — no ReAct tool noise)

MCP servers used:
  - mcp-rag  (port 8001): searchPolicies — cite policy clauses in decision
  - mcp-db   (port 8002): updateClaimStatus + insertAuditLog
"""

import json
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.advisor.prompts.advisorSystemPrompt import ADVISOR_SYSTEM_PROMPT
from agentic_claims.agents.advisor.tools.searchPolicies import searchPolicies
from agentic_claims.agents.advisor.tools.updateClaimStatus import updateClaimStatus
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.agents.shared.utils import extractJsonBlock
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"auto_approve", "return_to_claimant", "escalate_to_reviewer"}

DECISION_TO_STATUS = {
    "auto_approve": "ai_approved",
    "return_to_claimant": "ai_rejected",
    "escalate_to_reviewer": "escalated",
}

DECISION_LABELS = {
    "auto_approve": "AUTO-APPROVED",
    "return_to_claimant": "RETURNED TO CLAIMANT",
    "escalate_to_reviewer": "ESCALATED FOR REVIEW",
}


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def _getAdvisorAgent(useFallback: bool = False):
    """Create the ReAct advisor agent with its two tools."""
    settings = getSettings()
    llm = buildAgentLlm(settings, temperature=0.2, useFallback=useFallback)

    return create_react_agent(
        model=llm,
        tools=[searchPolicies, updateClaimStatus],
        prompt=ADVISOR_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Context extraction helpers
# ---------------------------------------------------------------------------


def _extractClaimNumber(state: ClaimState) -> str:
    """Read claim number from state, fall back to scanning messages."""
    # Primary: written to state by intakeNode after submitClaim
    claimNumber = state.get("claimNumber")
    if claimNumber:
        return str(claimNumber)

    # Fallback: scan messages for submitClaim ToolMessage
    for msg in state.get("messages", []):
        if hasattr(msg, "name") and msg.name == "submitClaim" and hasattr(msg, "content"):
            try:
                content = (
                    json.loads(msg.content)
                    if isinstance(msg.content, str)
                    else msg.content
                )
                if isinstance(content, dict) and "claim" in content:
                    num = content["claim"].get("claim_number")
                    if num:
                        return str(num)
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
    return "CLAIM-UNKNOWN"


def _extractAdvisorDecision(messages: list) -> str:
    """Scan advisor agent output messages for the final JSON decision.

    Walks messages in reverse — last AIMessage most likely has the final JSON.
    Falls back to escalate_to_reviewer (conservative) if nothing parseable found.
    """
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else ""

        jsonStr = extractJsonBlock(content)
        if jsonStr:
            try:
                parsed = json.loads(jsonStr)
                decision = parsed.get("decision", "")
                if decision in VALID_DECISIONS:
                    return decision
            except (json.JSONDecodeError, AttributeError):
                pass

        # Plain text keyword fallback
        contentLower = content.lower()
        if "auto_approve" in contentLower:
            return "auto_approve"
        if "return_to_claimant" in contentLower:
            return "return_to_claimant"
        if "escalate_to_reviewer" in contentLower or "escalate" in contentLower:
            return "escalate_to_reviewer"

    logger.warning("Could not extract advisor decision from messages — defaulting to escalate_to_reviewer")
    return "escalate_to_reviewer"


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def _advisorErrorFallback(
    claimId: str,
    dbClaimId: int | None,
    settings,
    errorStr: str,
    complianceFindings: dict,
    fraudFindings: dict,
) -> dict:
    """Safe fallback when advisorNode fails unexpectedly.

    Escalates the claim to "escalated" with reason "advisor_error" so it is
    never silently left in "pending". Writes audit_log and updateClaimStatus
    via DB MCP (non-fatal if those calls also fail).

    Returns a valid partial state update.
    """
    logger.error(
        "advisorNode failed — applying error fallback (escalate_to_reviewer)",
        extra={"claimId": claimId, "error": errorStr},
    )

    if dbClaimId is not None:
        try:
            auditValue = json.dumps({
                "decision": "escalate_to_reviewer",
                "reason": "advisor_error",
                "error": errorStr,
                "complianceVerdict": complianceFindings.get("verdict"),
                "fraudVerdict": fraudFindings.get("verdict"),
            })
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": "advisor_decision",
                    "newValue": auditValue,
                    "actor": "advisor_agent",
                    "oldValue": "",
                },
            )
        except Exception as auditErr:
            logger.warning(
                "Error fallback: failed to write advisor audit log",
                extra={"claimId": claimId, "error": str(auditErr)},
            )

        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="updateClaimStatus",
                arguments={
                    "claimId": dbClaimId,
                    "newStatus": "escalated",
                    "actor": "advisor_agent",
                    "complianceFindings": complianceFindings,
                    "fraudFindings": fraudFindings,
                    "advisorDecision": "escalate_to_reviewer",
                    "advisorFindings": {
                        "decision": "escalate_to_reviewer",
                        "reasoning": "Advisor encountered an error and escalated the claim for manual review.",
                        "complianceVerdict": complianceFindings.get("verdict"),
                        "fraudVerdict": fraudFindings.get("verdict"),
                    },
                    "approvedBy": "",
                },
            )
        except Exception as updateErr:
            logger.warning(
                "Error fallback: failed to update claim status",
                extra={"claimId": claimId, "error": str(updateErr)},
            )

    return {
        "messages": [AIMessage(content="**Advisor Decision**: ESCALATED FOR REVIEW\n\nAdvisor encountered an error and escalated the claim for manual review.")],
        "advisorDecision": "escalate_to_reviewer",
        "status": "escalated",
    }


async def advisorNode(state: ClaimState) -> dict:
    """Make the final claim routing decision and take action.

    Reads complianceFindings and fraudFindings from state, builds a context
    message for the ReAct agent, then invokes the agent to: update claim
    status in DB, send email notifications (and optionally cite policy clauses).

    Args:
        state: ClaimState — expects complianceFindings, fraudFindings, dbClaimId,
               claimNumber, extractedReceipt, intakeFindings to be set.

    Returns:
        Partial state update:
          - messages: [AIMessage] with human-readable decision summary only
          - advisorDecision: one of "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
          - status: DB-aligned status string ("ai_approved" | "ai_rejected" | "escalated")
    """
    settings = getSettings()
    claimId = state.get("claimId", "unknown")
    logger.info("advisorNode started", extra={"claimId": claimId})

    # ------------------------------------------------------------------
    # 1. Read findings and identifiers from state
    # ------------------------------------------------------------------
    complianceFindings = state.get("complianceFindings") or {}
    fraudFindings = state.get("fraudFindings") or {}
    intakeFindings = state.get("intakeFindings") or {}
    extractedReceipt = state.get("extractedReceipt") or {}
    receiptFields = extractedReceipt.get("fields", {})

    # Read dbClaimId directly from state (written by intakeNode after submitClaim)
    dbClaimIdEarly = state.get("dbClaimId")

    # Write start audit entry so the timeline shows "Processing"
    if dbClaimIdEarly is not None:
        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimIdEarly,
                    "action": "advisor_decision_start",
                    "newValue": json.dumps({"status": "processing"}),
                    "actor": "advisor_agent",
                    "oldValue": "",
                },
            )
        except Exception:
            pass
    dbClaimId = state.get("dbClaimId")
    claimNumber = _extractClaimNumber(state)

    if dbClaimId is None:
        logger.warning("dbClaimId not found in state — DB update may be skipped by agent", extra={"claimId": claimId})

    employeeId = (
        intakeFindings.get("employeeId")
        or receiptFields.get("employeeId")
        or "unknown"
    )
    merchant = receiptFields.get("merchant", "unknown")
    totalAmountSgd = (
        receiptFields.get("totalAmountSgd")
        or receiptFields.get("amountSgd")
        or receiptFields.get("totalAmount")
        or 0.0
    )

    logger.info(
        "Advisor context built",
        extra={
            "claimId": claimId,
            "dbClaimId": dbClaimId,
            "claimNumber": claimNumber,
            "employeeId": employeeId,
            "complianceVerdict": complianceFindings.get("verdict"),
            "fraudVerdict": fraudFindings.get("verdict"),
        },
    )

    # ------------------------------------------------------------------
    # 2. Build context message for the ReAct agent
    # ------------------------------------------------------------------
    advisorContext = {
        "sessionClaimId": claimId,
        "dbClaimId": dbClaimId,
        "claimNumber": claimNumber,
        "employeeId": employeeId,
        "merchant": merchant,
        "totalAmountSgd": totalAmountSgd,
        "complianceFindings": complianceFindings,
        "fraudFindings": fraudFindings,
        "intakeFindings": intakeFindings,
    }

    contextMessage = (
        "## Claim Review Context\n\n"
        f"```json\n{json.dumps(advisorContext, indent=2, default=str)}\n```\n\n"
        "Apply the decision rules from your system prompt.\n"
        "Follow the mandatory workflow: decide → updateClaimStatus.\n"
        "End with the final JSON summary.\n"
        "/no_think"
    )

    # ------------------------------------------------------------------
    # 3. Invoke ReAct agent with 402 fallback
    # ------------------------------------------------------------------
    modelName = settings.openrouter_model_llm
    agent = _getAdvisorAgent()
    agentInput = {"messages": [HumanMessage(content=contextMessage)]}

    logger.info(
        "advisorNode LLM request",
        extra={
            "claimId": claimId,
            "model": modelName,
            "userPrompt": contextMessage[:2000],
        },
    )
    llmStartTime = time.time()

    try:
        result = await agent.ainvoke(agentInput)
        llmElapsed = round(time.time() - llmStartTime, 2)

        # Log all agent output messages for debugging
        agentMessages = result.get("messages", [])
        lastContent = agentMessages[-1].content if agentMessages else ""
        logger.info(
            "advisorNode LLM response",
            extra={
                "claimId": claimId,
                "model": modelName,
                "elapsedSeconds": llmElapsed,
                "messageCount": len(agentMessages),
                "lastMessageContent": lastContent[:2000] if isinstance(lastContent, str) else str(lastContent)[:2000],
            },
        )

    except Exception as e:
        llmElapsed = round(time.time() - llmStartTime, 2)
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM returned 402 in advisorNode — falling back",
                extra={"error": errorStr, "elapsedSeconds": llmElapsed},
            )
            try:
                fallbackAgent = _getAdvisorAgent(useFallback=True)
                result = await fallbackAgent.ainvoke(agentInput)
            except Exception as fallbackErr:
                return await _advisorErrorFallback(
                    claimId=claimId,
                    dbClaimId=dbClaimId,
                    settings=settings,
                    errorStr=str(fallbackErr),
                    complianceFindings=complianceFindings,
                    fraudFindings=fraudFindings,
                )
        else:
            # BUG-019: any unexpected exception must not leave the claim stuck in "pending".
            return await _advisorErrorFallback(
                claimId=claimId,
                dbClaimId=dbClaimId,
                settings=settings,
                errorStr=errorStr,
                complianceFindings=complianceFindings,
                fraudFindings=fraudFindings,
            )

    # ------------------------------------------------------------------
    # 4. Extract decision from agent output
    # ------------------------------------------------------------------
    advisorDecision = _extractAdvisorDecision(result["messages"])
    newStatus = DECISION_TO_STATUS.get(advisorDecision, "escalated")
    approvedBy = "agent" if advisorDecision == "auto_approve" else ""

    logger.info(
        "advisorNode completed",
        extra={"claimId": claimId, "advisorDecision": advisorDecision, "newStatus": newStatus},
    )

    # ------------------------------------------------------------------
    # 5. Write advisor_decision audit log and persist findings to claims table
    # ------------------------------------------------------------------
    # Extract LLM reasoning text from agent output
    agentMessages = result.get("messages", [])
    advisorReasoningText = ""
    for msg in reversed(agentMessages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            advisorReasoningText = msg.content
            break

    advisorFindingsPayload = {
        "decision": advisorDecision,
        "reasoning": advisorReasoningText,
        "complianceVerdict": complianceFindings.get("verdict"),
        "fraudVerdict": fraudFindings.get("verdict"),
    }

    if dbClaimId is not None:
        try:
            auditValue = json.dumps({
                "decision": advisorDecision,
                "complianceVerdict": complianceFindings.get("verdict"),
                "fraudVerdict": fraudFindings.get("verdict"),
            })
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="insertAuditLog",
                arguments={
                    "claimId": dbClaimId,
                    "action": "advisor_decision",
                    "newValue": auditValue,
                    "actor": "advisor_agent",
                    "oldValue": "",
                },
            )
            logger.debug("Advisor audit log written", extra={"claimId": claimId, "dbClaimId": dbClaimId})
        except Exception as e:
            logger.warning(
                "Failed to write advisor audit log — continuing",
                extra={"claimId": claimId, "error": str(e)},
            )

        try:
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="updateClaimStatus",
                arguments={
                    "claimId": dbClaimId,
                    "newStatus": newStatus,
                    "actor": "advisor_agent",
                    "complianceFindings": complianceFindings,
                    "fraudFindings": fraudFindings,
                    "advisorDecision": advisorDecision,
                    "advisorFindings": advisorFindingsPayload,
                    "approvedBy": approvedBy,
                },
            )
            logger.debug("Advisor updateClaimStatus written", extra={"claimId": claimId, "newStatus": newStatus, "approvedBy": approvedBy})
        except Exception as e:
            logger.warning(
                "Failed to write advisor updateClaimStatus — continuing",
                extra={"claimId": claimId, "error": str(e)},
            )

    # ------------------------------------------------------------------
    # 6. Build human-readable summary — only this message goes into state
    # ------------------------------------------------------------------
    label = DECISION_LABELS.get(advisorDecision, advisorDecision.upper())
    summaryMsg = (
        f"**Advisor Decision**: {label}\n\n"
        f"Compliance: **{complianceFindings.get('verdict', 'unknown').upper()}** — "
        f"{complianceFindings.get('summary', '')}\n\n"
        f"Fraud: **{fraudFindings.get('verdict', 'unknown').upper()}** — "
        f"{fraudFindings.get('summary', '')}"
    )

    return {
        "messages": [AIMessage(content=summaryMsg)],
        "advisorDecision": advisorDecision,
        "status": newStatus,
    }
