"""Advisor agent node — reflection + routing decision for submitted claims.

Author: jamesoon
Pattern: Reflection + Routing (Anthropic agentic pattern)

Workflow:
  1. Read complianceFindings and fraudFindings from ClaimState (written by parallel agents)
  2. Extract the DB claim ID from the submitClaim ToolMessage in conversation history
  3. Apply decision rules (with LLM reflection via create_react_agent for edge cases)
  4. Call updateClaimStatus (DB MCP) to persist the decision
  5. Call sendNotification (Email MCP) for claimant and reviewer if escalating
  6. Extract advisorDecision from agent output and write to state

MCP servers used:
  - mcp-rag  (port 8001): searchPolicies  — cite policy clauses in decision
  - mcp-db   (port 8002): updateClaimStatus — persist routing decision + audit log
  - mcp-email (port 8004): sendClaimNotification — notify claimant and/or reviewer

The node uses create_react_agent (same as intake) so the LLM can call tools
in any order needed — handles edge cases where extra policy lookups are required.
"""

import json
import logging
import re

import httpx
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openrouter import ChatOpenRouter
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.advisor.prompts.advisorSystemPrompt import ADVISOR_SYSTEM_PROMPT
from agentic_claims.agents.advisor.tools.searchPolicies import searchPolicies
from agentic_claims.agents.advisor.tools.sendNotification import sendNotification
from agentic_claims.agents.advisor.tools.updateClaimStatus import updateClaimStatus
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)

# Valid advisor decision strings (used for parsing and validation)
VALID_DECISIONS = {"auto_approve", "return_to_claimant", "escalate_to_reviewer"}


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------


def _buildAdvisorLlm(settings, useFallback: bool = False) -> ChatOpenRouter:
    """Instantiate ChatOpenRouter for the advisor's reflection loop.

    Slightly higher temperature than compliance/fraud (0.2) to allow
    nuanced reasoning while still being deterministic enough for routing.
    """
    modelName = (
        settings.openrouter_fallback_model_llm if useFallback
        else settings.openrouter_model_llm
    )

    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=0.2,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Bypass SSL verification (Zscaler corporate proxy) — same workaround as intake node
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    return llm


def _getAdvisorAgent(useFallback: bool = False):
    """Create the ReAct advisor agent with its three tools."""
    settings = getSettings()
    llm = _buildAdvisorLlm(settings, useFallback)

    return create_react_agent(
        model=llm,
        tools=[searchPolicies, updateClaimStatus, sendNotification],
        prompt=ADVISOR_SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Context extraction helpers
# ---------------------------------------------------------------------------


def _extractDbClaimId(state: ClaimState) -> int | None:
    """Scan conversation messages for the submitClaim ToolMessage.

    The intake agent's submitClaim tool returns a JSON response containing
    the DB integer primary key under claim.id. This is the ID needed by
    updateClaimStatus.

    Returns None if not found (advisor will log a warning and skip DB update).
    """
    for msg in state.get("messages", []):
        if (
            hasattr(msg, "name")
            and msg.name == "submitClaim"
            and hasattr(msg, "content")
        ):
            try:
                content = (
                    json.loads(msg.content)
                    if isinstance(msg.content, str)
                    else msg.content
                )
                if isinstance(content, dict) and "claim" in content:
                    claimRecord = content["claim"]
                    dbId = claimRecord.get("id")
                    if dbId is not None:
                        logger.info(
                            "Extracted DB claim ID from submitClaim ToolMessage",
                            extra={"dbClaimId": dbId},
                        )
                        return int(dbId)
            except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
                pass
    return None


def _extractClaimNumber(state: ClaimState) -> str:
    """Extract the human-readable claim number (e.g. CLAIM-001) from messages."""
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

    Looks for a JSON block with a "decision" key in the last AIMessage.
    Falls back to "escalate_to_reviewer" if nothing parseable is found.
    """
    # Walk messages in reverse — most likely the last AIMessage has the final JSON
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else ""

        # Try to find a JSON object with a "decision" key
        jsonStr = _extractJsonBlock(content)
        if jsonStr:
            try:
                parsed = json.loads(jsonStr)
                decision = parsed.get("decision", "")
                if decision in VALID_DECISIONS:
                    return decision
            except (json.JSONDecodeError, AttributeError):
                pass

        # Try plain text keywords as fallback
        contentLower = content.lower()
        if "auto_approve" in contentLower:
            return "auto_approve"
        if "return_to_claimant" in contentLower:
            return "return_to_claimant"
        if "escalate_to_reviewer" in contentLower or "escalate" in contentLower:
            return "escalate_to_reviewer"

    # Conservative default
    logger.warning("Could not extract advisor decision from messages — defaulting to escalate_to_reviewer")
    return "escalate_to_reviewer"


def _extractJsonBlock(text: str) -> str | None:
    """Extract first JSON object from a string (handles fenced and raw JSON)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    raw = re.search(r"\{.*\}", text, re.DOTALL)
    if raw:
        return raw.group(0)
    return None


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def advisorNode(state: ClaimState) -> dict:
    """Make the final claim routing decision and take action.

    Reads complianceFindings and fraudFindings written by the parallel agents,
    builds a context message for the ReAct agent, then invokes the agent to:
      1. (optionally) search additional policies
      2. update claim status in DB
      3. send notification emails

    Args:
        state: ClaimState — expects complianceFindings and fraudFindings set by
               the compliance and fraud nodes running before this node.

    Returns:
        Partial state update:
          - messages: AIMessage with human-readable decision summary
          - advisorDecision: one of "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
          - status: DB-aligned status string ("approved" | "returned" | "escalated")
    """
    settings = getSettings()
    claimId = state.get("claimId", "unknown")
    logger.info("advisorNode started", extra={"claimId": claimId})

    # ------------------------------------------------------------------
    # 1. Read findings from state
    # ------------------------------------------------------------------
    complianceFindings = state.get("complianceFindings") or {}
    fraudFindings = state.get("fraudFindings") or {}
    intakeFindings = state.get("intakeFindings") or {}
    extractedReceipt = state.get("extractedReceipt") or {}
    receiptFields = extractedReceipt.get("fields", {})

    # ------------------------------------------------------------------
    # 2. Extract DB claim ID and claim number from conversation history
    # ------------------------------------------------------------------
    dbClaimId = _extractDbClaimId(state)
    claimNumber = _extractClaimNumber(state)

    if dbClaimId is None:
        logger.warning(
            "Could not find DB claim ID in messages — updateClaimStatus will be skipped if agent cannot resolve it",
            extra={"claimId": claimId},
        )

    # Employee ID needed for email address
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
    # 3. Build context message for the ReAct agent
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
        "Follow the mandatory workflow: decide → updateClaimStatus → sendNotification (claimant) "
        "→ sendNotification (reviewer, if escalating).\n"
        "End with the final JSON summary."
    )

    # ------------------------------------------------------------------
    # 4. Invoke ReAct agent with 402 fallback
    # ------------------------------------------------------------------
    agent = _getAdvisorAgent()
    agentInput = {"messages": [HumanMessage(content=contextMessage)]}

    try:
        result = await agent.ainvoke(agentInput)
    except Exception as e:
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM returned 402 in advisorNode — falling back",
                extra={"error": errorStr},
            )
            fallbackAgent = _getAdvisorAgent(useFallback=True)
            result = await fallbackAgent.ainvoke(agentInput)
        else:
            raise

    # ------------------------------------------------------------------
    # 5. Extract decision from agent output messages
    # ------------------------------------------------------------------
    advisorDecision = _extractAdvisorDecision(result["messages"])
    logger.info(
        "advisorNode completed",
        extra={"claimId": claimId, "advisorDecision": advisorDecision},
    )

    # Map decision to claim lifecycle status
    decisionToStatus = {
        "auto_approve": "approved",
        "return_to_claimant": "returned",
        "escalate_to_reviewer": "escalated",
    }
    newStatus = decisionToStatus.get(advisorDecision, "escalated")

    # Human-readable summary message for the conversation UI
    decisionLabels = {
        "auto_approve": "AUTO-APPROVED",
        "return_to_claimant": "RETURNED TO CLAIMANT",
        "escalate_to_reviewer": "ESCALATED FOR REVIEW",
    }
    label = decisionLabels.get(advisorDecision, advisorDecision.upper())
    summaryMsg = (
        f"**Advisor Decision**: {label}\n\n"
        f"Compliance: **{complianceFindings.get('verdict', 'unknown').upper()}** — "
        f"{complianceFindings.get('summary', '')}\n\n"
        f"Fraud: **{fraudFindings.get('verdict', 'unknown').upper()}** — "
        f"{fraudFindings.get('summary', '')}"
    )

    return {
        "messages": result["messages"] + [AIMessage(content=summaryMsg)],
        "advisorDecision": advisorDecision,
        "status": newStatus,
    }
