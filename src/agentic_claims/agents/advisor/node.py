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
from agentic_claims.agents.shared.llmFactory import buildGovernedAgentLlm
from agentic_claims.agents.shared.utils import extractJsonBlock
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.core.state import ClaimState
from agentic_claims.web.governanceNoticeContext import append_background_governance
from agentic_governance.core.content_envelope import ContentType

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
    """Create the ReAct advisor agent with its two tools.
    
    GOVERNANCE LIMITATION: create_react_agent uses .bind_tools()/.astream() internally
    which bypasses GovernedChatOpenRouter.ainvoke override. The advisor node must
    govern explicitly at the invocation boundary (pre/post checks around agent.ainvoke).
    
    This limitation applies to any LangGraph prebuilt that wraps the model (create_react_agent,
    create_openai_functions_agent, .with_structured_output, etc.). Direct llm.ainvoke() calls
    (like compliance/fraud) are governed by the wrapper.
    """
    settings = getSettings()
    llm = buildGovernedAgentLlm(settings, agent_identity="advisor", temperature=0.2, useFallback=useFallback)

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

    logEvent(
        logger,
        "advisor.decision_extract_fallback",
        level=logging.WARNING,
        logCategory="agent",
        agent="advisor",
        message="Could not extract advisor decision from messages — defaulting to escalate_to_reviewer",
    )
    return "escalate_to_reviewer"


def _extractAdvisorSummaryFields(messages: list) -> dict:
    """Extract plain-text reasoning/summary fields from the advisor's final JSON output."""
    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else ""
        jsonStr = extractJsonBlock(content)
        if not jsonStr:
            continue
        try:
            parsed = json.loads(jsonStr)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, dict):
            continue
        reasoning = parsed.get("reasoning")
        summary = parsed.get("summary")
        citedClauses = parsed.get("citedClauses")
        return {
            "reasoning": str(reasoning).strip() if reasoning else "",
            "summary": str(summary).strip() if summary else "",
            "citedClauses": citedClauses if isinstance(citedClauses, list) else [],
        }

    fallbackText = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            fallbackText = msg.content.strip()
            break
    return {
        "reasoning": fallbackText,
        "summary": "",
        "citedClauses": [],
    }


def _extractReviewerExplanation(*results) -> str | None:
    """Best-effort extraction of a reviewer-facing B6 explanation from governance results.

    Supports multiple attribute/key spellings to avoid tight coupling to runtime internals.
    Returns the first non-empty string found.

    NOTE: This value may be filtered out later if it matches benign allow-only
    patterns; final persisted explanation is selected by decision-aware precedence.
    """
    candidate_keys = [
        "explanation_reviewer",
        "reviewer_explanation",
        "explanationReviewer",
        "reviewerExplanation",
        "b6_explanation",
        "explanation",  # fallback (if runtime exposes a single explanation)
    ]
    for res in results:
        if res is None:
            continue
        # Attribute access (object-like)
        for k in candidate_keys:
            try:
                val = getattr(res, k)
                if isinstance(val, str) and val.strip():
                    return val.strip()
            except Exception:
                pass
        # Dict-like access
        try:
            if isinstance(res, dict):
                for k in candidate_keys:
                    val = res.get(k)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
        except Exception:
            pass
    return None


def _isBenignAllowExplanation(text: str | None) -> bool:
    """Return True if text is a generic allow-only governance message (low-value for reviewers).

    Examples filtered:
    - "Control B2: Allow." / "control b2: allow"
    - "Allow" / "Allowed"
    The check is conservative to avoid hiding meaningful content.
    """
    if not text:
        return False
    t = text.strip().lower()
    if not t:
        return False
    if t in ("allow", "allowed", "allow.", "allowed."):
        return True
    # "control xyz: allow" style
    if t.startswith("control ") and ":" in t and "allow" in t:
        # ensure there's no contradictory cue suggesting escalation/deny
        bad_cues = ("deny", "escalat", "violation", "duplicate", "fail")
        if not any(cue in t for cue in bad_cues):
            return True
    return False


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
    logEvent(
        logger,
        "advisor.error",
        level=logging.ERROR,
        logCategory="agent",
        agent="advisor",
        claimId=claimId,
        error=errorStr,
        message="advisorNode failed — applying error fallback (escalate_to_reviewer)",
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
            logEvent(
                logger,
                "advisor.audit_log_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                error=str(auditErr),
                message="Error fallback: failed to write advisor audit log",
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
            logEvent(
                logger,
                "advisor.status_update_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                error=str(updateErr),
                message="Error fallback: failed to update claim status",
            )

    return {
        "messages": [AIMessage(content="**Advisor Decision**: ESCALATED FOR REVIEW\n\nAdvisor encountered an error and escalated the claim for manual review.", additional_kwargs={"agent": "advisor"})],
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
    logEvent(
        logger,
        "advisor.started",
        logCategory="agent",
        agent="advisor",
        claimId=claimId,
        message="Advisor agent started",
    )

    # ------------------------------------------------------------------
    # 1. Read findings and identifiers from state
    # ------------------------------------------------------------------
    complianceFindings = state.get("complianceFindings") or {}
    fraudFindings = state.get("fraudFindings") or {}
    intakeFindings = state.get("intakeFindings") or {}
    extractedReceipt = state.get("extractedReceipt") or {}
    receiptFields = extractedReceipt.get("fields", {})
    
    # B3 grounding: build trusted_state from extracted receipt + claim data
    # Try ContextVar first, fall back to state (ContextVar may not propagate across async tasks)
    from agentic_claims.agents.intake.extractionContext import extractedReceiptVar
    
    trusted_receipt = extractedReceiptVar.get(None)
    claim_data = state.get("claimData", {})
    
    # BUG FIX: Source trusted values from state if ContextVar not set (async boundary)
    if trusted_receipt and isinstance(trusted_receipt, dict):
        fields = trusted_receipt.get("fields", {})
        trusted_amount = claim_data.get("amountSgd") or fields.get("totalAmount")
        trusted_date = fields.get("date")
        trusted_vendor = fields.get("merchant")
        trusted_currency = fields.get("currency", "SGD")
    else:
        # Fallback to state (extractedReceipt stored in state by intake)
        extracted_from_state = state.get("extractedReceipt", {}).get("fields", {})
        trusted_amount = claim_data.get("amountSgd") or extracted_from_state.get("totalAmount")
        trusted_date = extracted_from_state.get("date")
        trusted_vendor = extracted_from_state.get("merchant")
        trusted_currency = extracted_from_state.get("currency", "SGD")
    
    # BUG FIX: Read compliance/fraud verdicts UNCONDITIONALLY from state (NOT gated)
    # These are always in state, don't depend on extractedReceiptVar
    compliance_verdict = complianceFindings.get("verdict")
    fraud_verdict = fraudFindings.get("verdict")
    
    trusted_state_b3 = {
        "amount": trusted_amount,
        "date": trusted_date,
        "vendor": trusted_vendor,
        "currency": trusted_currency,
        "compliance_verdict": compliance_verdict,
        "fraud_verdict": fraud_verdict,
    }
    
    # B3 grounding: RAG clauses from compliance findings (already verified)
    rag_clauses_b3 = complianceFindings.get("citedClauses", [])

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
        logEvent(
            logger,
            "advisor.missing_db_claim_id",
            level=logging.WARNING,
            logCategory="agent",
            agent="advisor",
            claimId=claimId,
            message="dbClaimId not found in state — DB update may be skipped by agent",
        )

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

    logEvent(
        logger,
        "advisor.context_built",
        logCategory="agent",
        agent="advisor",
        claimId=claimId,
        dbClaimId=dbClaimId,
        claimNumber=claimNumber,
        employeeId=employeeId,
        complianceVerdict=complianceFindings.get("verdict"),
        fraudVerdict=fraudFindings.get("verdict"),
        message="Advisor context built",
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

    # B6 reviewer explanation captured from runtime (not authoritative; filtered later)
    reviewer_explanation: str | None = None

    logEvent(
        logger,
        "advisor.llm_request",
        logCategory="agent",
        agent="advisor",
        claimId=claimId,
        model=modelName,
        payload={"userPrompt": contextMessage[:2000]},
        message="Advisor LLM request",
    )
    llmStartTime = time.time()

    # Pre-check: B1/B2 on advisor input (create_react_agent bypasses wrapper)
    # Lazy import: core.graph imports this module at graph-build time, so a top-level
    # import here creates a circular import. Imported at call time (after graph build),
    # contentHookRuntime_background is set to the real runtime instance.
    from agentic_claims.core.graph import contentHookRuntime_background
    if contentHookRuntime_background and hasattr(contentHookRuntime_background, "pre_model_check"):
        try:
            pre_result = await contentHookRuntime_background.pre_model_check(
                content=contextMessage,
                content_type=ContentType.INTER_AGENT,
                correlation_id=claimId,
                agent_identity="advisor",
                context={"agent": "advisor", "background": True},
            )
            
            # Capture actionable fired_controls for findings embed
            if pre_result.fired_controls:
                for control in pre_result.fired_controls:
                    result_val = control.get("result", "")
                    if result_val in ("redacted", "escalated", "blocked", "flagged", "grounding-failed", "concerns-found"):
                        append_background_governance({
                            "control": control.get("controlId"),
                            "name": control.get("name"),
                            "result": result_val,
                            "entityTypes": control.get("entityTypes"),
                            "signalValue": control.get("signalValue"),
                        })
            
            # Capture reviewer-facing explanation (if provided by runtime)
            try:
                pre_expl = _extractReviewerExplanation(pre_result)
                if pre_expl:
                    reviewer_explanation = pre_expl
            except Exception:
                pass

            # If governance blocked, return early
            if not pre_result.should_proceed:
                logEvent(
                    logger,
                    "advisor.governance_blocked",
                    level=logging.WARNING,
                    logCategory="governance",
                    agent="advisor",
                    claimId=claimId,
                    message="Advisor input blocked by governance",
                )
                # Return escalation decision when governance blocks
                return await _advisorErrorFallback(
                    claimId=claimId,
                    dbClaimId=dbClaimId,
                    settings=settings,
                    errorStr="Governance blocked advisor input",
                    complianceFindings=complianceFindings,
                    fraudFindings=fraudFindings,
                )
        except Exception as gov_exc:
            logEvent(
                logger,
                "advisor.governance_error",
                level=logging.WARNING,
                logCategory="governance",
                agent="advisor",
                claimId=claimId,
                error=str(gov_exc),
                message="Pre-check governance failed — continuing",
            )

    try:
        result = await agent.ainvoke(agentInput)
        llmElapsed = round(time.time() - llmStartTime, 2)

        # Log all agent output messages for debugging
        agentMessages = result.get("messages", [])
        lastContent = agentMessages[-1].content if agentMessages else ""
        logEvent(
            logger,
            "advisor.llm_response",
            logCategory="agent",
            agent="advisor",
            claimId=claimId,
            model=modelName,
            elapsedSeconds=llmElapsed,
            messageCount=len(agentMessages),
            payload={"lastMessageContent": lastContent[:2000] if isinstance(lastContent, str) else str(lastContent)[:2000]},
            message="Advisor LLM response",
        )
        
        # Post-check: B2 PII + B3 grounding + B4 judge on advisor output (create_react_agent bypasses wrapper)
        post_result_b3 = None
        if contentHookRuntime_background and hasattr(contentHookRuntime_background, "post_model_check") and lastContent:
            try:
                # BUG FIX: Normalize advisor output for GroundingValidator
                # Extract summary fields to get citedClauses (before final extraction below)
                temp_summary = _extractAdvisorSummaryFields(agentMessages)
                
                # Build normalized dict with GroundingValidator-compatible keys
                normalized_advisor_output = {
                    "amount": trusted_state_b3.get("amount"),  # Advisor references the claim amount
                    "date": trusted_state_b3.get("date"),      # Advisor references the receipt date
                    "vendor": trusted_state_b3.get("vendor"),  # Advisor references the merchant
                    "cited_clauses": temp_summary.get("citedClauses", []),  # ← Key fix: cited_clauses not citedClauses
                }
                
                post_result_b3 = await contentHookRuntime_background.post_model_check(
                    content=json.dumps(normalized_advisor_output),  # Pass normalized JSON
                    content_type=ContentType.MODEL_OUTPUT,
                    correlation_id=claimId,
                    agent_identity="advisor",
                    context={"agent": "advisor", "background": True},
                    trusted_state=trusted_state_b3,  # B3 grounding validation
                    rag_clauses=rag_clauses_b3,
                    required_evidence_fields=None,
                )
                
                # Capture actionable fired_controls for findings embed
                if post_result_b3.fired_controls:
                    for control in post_result_b3.fired_controls:
                        result_val = control.get("result", "")
                        if result_val in ("redacted", "escalated", "blocked", "flagged", "grounding-failed", "concerns-found"):
                            append_background_governance({
                                "control": control.get("controlId"),
                                "name": control.get("name"),
                                "result": result_val,
                                "entityTypes": control.get("entityTypes"),
                                "signalValue": control.get("signalValue"),
                            })
                
                # Capture reviewer-facing explanation (from runtime; will be filtered later)
                try:
                    post_expl = _extractReviewerExplanation(post_result_b3)
                    if post_expl:
                        reviewer_explanation = post_expl
                except Exception:
                    pass

                # B4 judge (observe-only): critique advisor output and record structured signal
                try:
                    critique = await contentHookRuntime_background.judge(
                        content=str(lastContent) if isinstance(lastContent, str) else json.dumps(normalized_advisor_output),
                        correlation_id=claimId,
                        agent_identity="advisor",
                        context={"agent": "advisor", "background": True},
                    ) if hasattr(contentHookRuntime_background, "judge") else None
                    if critique and getattr(critique, "confidence", None) is not None:
                        result_val = "concerns-found" if getattr(critique, "concerns", ()) else "no-concerns"
                        append_background_governance({
                            "control": "B4",
                            "name": "llm-judge",
                            "result": result_val,
                            "entityTypes": None,
                            "signalValue": critique.confidence,
                        })
                except Exception:
                    pass
            except Exception as gov_exc:
                logEvent(
                    logger,
                    "advisor.governance_error",
                    level=logging.WARNING,
                    logCategory="governance",
                    agent="advisor",
                    claimId=claimId,
                    error=str(gov_exc),
                    message="Post-check governance failed — continuing",
                )

    except Exception as e:
        llmElapsed = round(time.time() - llmStartTime, 2)
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logEvent(
                logger,
                "advisor.llm_402_fallback",
                level=logging.WARNING,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                elapsedSeconds=llmElapsed,
                error=errorStr,
                message="Primary LLM returned 402 in advisorNode — falling back",
            )
            try:
                fallbackAgent = _getAdvisorAgent(useFallback=True)
                result = await fallbackAgent.ainvoke(agentInput)
                
                # Post-check on fallback result (pre-check already ran before main try)
                if contentHookRuntime_background and hasattr(contentHookRuntime_background, "post_model_check"):
                    try:
                        fallback_messages = result.get("messages", [])
                        fallback_content = fallback_messages[-1].content if fallback_messages else ""
                        if fallback_content:
                            # BUG FIX: Normalize fallback advisor output for GroundingValidator
                            fallback_summary = _extractAdvisorSummaryFields(fallback_messages)
                            
                            normalized_fallback_output = {
                                "amount": trusted_state_b3.get("amount"),
                                "date": trusted_state_b3.get("date"),
                                "vendor": trusted_state_b3.get("vendor"),
                                "cited_clauses": fallback_summary.get("citedClauses", []),
                            }
                            
                            post_result_b3 = await contentHookRuntime_background.post_model_check(
                                content=json.dumps(normalized_fallback_output),  # Pass normalized JSON
                                content_type=ContentType.MODEL_OUTPUT,
                                correlation_id=claimId,
                                agent_identity="advisor",
                                context={"agent": "advisor", "background": True, "fallback": True},
                                trusted_state=trusted_state_b3,  # B3 grounding validation
                                rag_clauses=rag_clauses_b3,
                                required_evidence_fields=None,
                            )
                            
                            # Capture actionable fired_controls
                            if post_result_b3.fired_controls:
                                for control in post_result_b3.fired_controls:
                                    result_val = control.get("result", "")
                                    if result_val in ("redacted", "escalated", "blocked", "flagged", "grounding-failed", "concerns-found"):
                                        append_background_governance({
                                            "control": control.get("controlId"),
                                            "name": control.get("name"),
                                            "result": result_val,
                                            "entityTypes": control.get("entityTypes"),
                                            "signalValue": control.get("signalValue"),
                                        })
                    except Exception as gov_exc:
                        logEvent(
                            logger,
                            "advisor.governance_error",
                            level=logging.WARNING,
                            logCategory="governance",
                            agent="advisor",
                            claimId=claimId,
                            error=str(gov_exc),
                            message="Fallback post-check governance failed — continuing",
                        )
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
    # 4. Extract decision from agent output + B3 grounding check
    # ------------------------------------------------------------------
    advisorDecision = _extractAdvisorDecision(result["messages"])
    
    # B3 inline advisor-specific consistency check: auto_approve requires compliance=pass AND fraud=clean/low_risk
    grounding_failed = False
    grounding_reasons = []
    
    # Check if B3 GroundingValidator already flagged issues (from post_model_check)
    if post_result_b3 and post_result_b3.fired_controls:
        for control in post_result_b3.fired_controls:
            if control.get("controlId") == "B3" and control.get("result") in ("grounding-failed", "escalated", "blocked"):
                grounding_failed = True
                grounding_reasons.append(control.get("name", "Grounding validation failed"))
    
    # Inline decision-consistency check (advisor-specific)
    if advisorDecision == "auto_approve":
        compliance_verdict = trusted_state_b3.get("compliance_verdict")
        fraud_verdict = trusted_state_b3.get("fraud_verdict")
        
        if compliance_verdict != "pass":
            grounding_failed = True
            grounding_reasons.append(f"auto_approve requires compliance=pass, got {compliance_verdict}")
        
        if fraud_verdict not in ("clean", "legit", "low_risk"):
            grounding_failed = True
            grounding_reasons.append(f"auto_approve requires fraud=clean/legit/low_risk, got {fraud_verdict}")
    
    # If grounding failed, DOWNGRADE decision to escalate_to_reviewer (before updateClaimStatus)
    original_decision = advisorDecision
    if grounding_failed:
        advisorDecision = "escalate_to_reviewer"
        grounding_override_reason = f"[Governance B3] {'; '.join(grounding_reasons)}"
        logEvent(
            logger,
            "advisor.b3_grounding_failed",
            level=logging.WARNING,
            logCategory="governance",
            agent="advisor",
            claimId=claimId,
            originalDecision=original_decision,
            downgradedDecision=advisorDecision,
            reasons=grounding_reasons,
            message="B3 grounding failed — downgraded decision to escalate_to_reviewer",
        )
    
    newStatus = DECISION_TO_STATUS.get(advisorDecision, "escalated")
    approvedBy = "agent" if advisorDecision == "auto_approve" else ""

    logEvent(
        logger,
        "advisor.completed",
        logCategory="agent",
        agent="advisor",
        claimId=claimId,
        advisorDecision=advisorDecision,
        newStatus=newStatus,
        message="Advisor agent completed",
    )

    # ------------------------------------------------------------------
    # 5. Write advisor_decision audit log and persist findings to claims table
    # ------------------------------------------------------------------
    agentMessages = result.get("messages", [])
    advisorSummaryFields = _extractAdvisorSummaryFields(agentMessages)

    # Select meaningful reviewer-facing explanation per precedence:
    # (a) governance downgrade/escalation reason (e.g., B3 grounding) if present
    # (b) else advisor reasoning/summary (explains actual decision)
    # Never persist benign allow-only governance text.
    selected_explanation = None
    if grounding_failed:
        selected_explanation = grounding_override_reason
    else:
        selected_explanation = advisorSummaryFields.get("reasoning") or advisorSummaryFields.get("summary") or None

    if _isBenignAllowExplanation(selected_explanation):
        selected_explanation = None

    advisorFindingsPayload = {
        "decision": advisorDecision,
        "reasoning": (
            grounding_override_reason + ". Original: " + advisorSummaryFields.get("reasoning", "")
            if grounding_failed
            else advisorSummaryFields.get("reasoning", "")
        ),
        "summary": advisorSummaryFields.get("summary", ""),
        "citedClauses": advisorSummaryFields.get("citedClauses", []),
        "complianceSummary": complianceFindings.get("summary", ""),
        "fraudSummary": fraudFindings.get("summary", ""),
        "complianceVerdict": complianceFindings.get("verdict"),
        "fraudVerdict": fraudFindings.get("verdict"),
    }
    
    # Persist reviewerExplanation inside advisorFindings (only if meaningful)
    if selected_explanation:
        advisorFindingsPayload["reviewerExplanation"] = selected_explanation
    
    # Drain and embed governance findings (B1/B2/B3 from governed LLM + inline checks)
    from agentic_claims.web.governanceNoticeContext import drain_background_governance
    governance_controls = drain_background_governance()
    
    # Add B3 grounding failure from inline consistency check if it failed
    if grounding_failed and not any(c.get("control") == "B3" for c in governance_controls):
        governance_controls.append({
            "control": "B3",
            "result": "escalated",
            "name": "Output grounding",
            "entityTypes": None,
            "details": {
                "original_decision": original_decision,
                "downgraded_to": advisorDecision,
                "reasons": grounding_reasons,
            },
        })
    
    if governance_controls:
        # Embed structured governance data in findings (PII-safe: IDs/results/types only)
        advisorFindingsPayload["governance"] = [
            {
                "control": c.get("control"),
                "result": c.get("result"),
                "reason": c.get("name"),
                "entityTypes": c.get("entityTypes"),
                "details": c.get("details"),
            }
            for c in governance_controls
        ]

    if dbClaimId is not None:
        try:
            # Reasoning for audit must be meaningful: prefer governance downgrade reason (if any), else advisor reasoning/summary
            reasoning_for_audit = selected_explanation or advisorSummaryFields.get("reasoning") or advisorSummaryFields.get("summary") or ""
            if _isBenignAllowExplanation(reasoning_for_audit):
                reasoning_for_audit = ""
            auditValue = json.dumps({
                "decision": advisorDecision,
                "complianceVerdict": complianceFindings.get("verdict"),
                "fraudVerdict": fraudFindings.get("verdict"),
                **({"reasoning": reasoning_for_audit} if reasoning_for_audit else {}),
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
            logEvent(
                logger,
                "advisor.audit_log_written",
                level=logging.DEBUG,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                dbClaimId=dbClaimId,
                message="Advisor audit log written",
            )
        except Exception as e:
            logEvent(
                logger,
                "advisor.audit_log_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                error=str(e),
                message="Failed to write advisor audit log — continuing",
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
            logEvent(
                logger,
                "advisor.status_update",
                level=logging.DEBUG,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                newStatus=newStatus,
                approvedBy=approvedBy,
                message="Advisor updateClaimStatus written",
            )
        except Exception as e:
            logEvent(
                logger,
                "advisor.status_update_error",
                level=logging.WARNING,
                logCategory="agent",
                agent="advisor",
                claimId=claimId,
                error=str(e),
                message="Failed to write advisor updateClaimStatus — continuing",
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
        "messages": [AIMessage(content=summaryMsg, additional_kwargs={"agent": "advisor"})],
        "advisorDecision": advisorDecision,
        "status": newStatus,
    }
