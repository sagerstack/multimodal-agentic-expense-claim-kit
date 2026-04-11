"""Intake agent node - ReAct agent with all domain tools."""

import json
import logging
import time

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_openrouter import ChatOpenRouter
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.intake.auditLogger import bufferStep, flushSteps, logIntakeStep
from agentic_claims.agents.intake.extractionContext import extractedReceiptVar
from agentic_claims.agents.intake.prompts.agentSystemPrompt_v3 import INTAKE_AGENT_SYSTEM_PROMPT
from agentic_claims.agents.intake.tools.askHuman import askHuman
from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.agents.intake.tools.getClaimSchema import getClaimSchema
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake.tools.submitClaim import submitClaim
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


def getIntakeAgent(useFallback: bool = False):
    """Create and return the compiled ReAct agent for intake processing.

    The agent uses ChatOpenRouter as the LLM and has access to
    6 domain tools for the intake workflow.

    Args:
        useFallback: If True, use fallback LLM model instead of primary

    Returns:
        Compiled ReAct agent graph
    """
    settings = getSettings()

    # Select model based on fallback flag
    modelName = settings.openrouter_fallback_model_llm if useFallback else settings.openrouter_model_llm

    # Instantiate ChatOpenRouter for reasoning token capture
    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=settings.openrouter_llm_temperature,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Bypass SSL verification (Zscaler corporate proxy workaround)
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    # Collect intake tools
    tools = [
        getClaimSchema,
        extractReceiptFields,
        searchPolicies,
        convertCurrency,
        submitClaim,
        askHuman,
    ]

    # Create ReAct agent with system prompt
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=INTAKE_AGENT_SYSTEM_PROMPT,
    )

    return agent


async def intakeNode(state: ClaimState, config: RunnableConfig) -> dict:
    """Process claim intake through ReAct agent loop.

    This node wraps the ReAct agent and manages state updates. The agent
    handles the full conversational loop internally (tool calling, reasoning, etc.).

    Config is passed through from the outer graph so that streaming events
    (on_chat_model_stream, on_tool_start, etc.) propagate to the outer
    graph's astream_events consumer in app.py.

    Args:
        state: Current claim state with messages
        config: RunnableConfig from outer graph (carries event callbacks)

    Returns:
        Partial state update with new messages and optional status/fields
    """
    nodeStart = time.time()
    logger.info("intakeNode started", extra={"claimId": state.get("claimId"), "messageCount": len(state.get("messages", []))})

    settings = getSettings()

    # Get the ReAct agent
    agent = getIntakeAgent()

    # Prepare input for agent (messages only)
    agentInput = {"messages": state["messages"]}

    # Invoke agent with 402 fallback retry
    # Pass config through so streaming events propagate to outer graph
    try:
        result = await agent.ainvoke(agentInput, config=config)
    except Exception as e:
        errorStr = str(e)
        # Check for 402 payment/quota errors
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logger.warning(
                "Primary LLM model returned 402, falling back to secondary model",
                extra={
                    "primary_model": settings.openrouter_model_llm,
                    "fallback_model": settings.openrouter_fallback_model_llm,
                    "error": errorStr,
                },
            )
            # Retry with fallback agent
            fallbackAgent = getIntakeAgent(useFallback=True)
            result = await fallbackAgent.ainvoke(agentInput, config=config)
        else:
            raise

    logger.info("intakeNode agent.ainvoke completed", extra={"elapsed": f"{time.time() - nodeStart:.2f}s", "resultMessageCount": len(result.get("messages", []))})

    # Build state update
    stateUpdate = {"messages": result["messages"]}

    # Scan tool messages to extract state updates from agent tool calls
    for msg in result["messages"]:
        if not (hasattr(msg, "name") and hasattr(msg, "content")):
            continue
        try:
            content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            if not isinstance(content, dict) or "error" in content:
                continue

            if msg.name == "submitClaim":
                stateUpdate["claimSubmitted"] = True
                claimRecord = content.get("claim", {})
                claimNumber = claimRecord.get("claim_number")
                if claimNumber:
                    stateUpdate["claimNumber"] = claimNumber
                dbClaimId = claimRecord.get("id")
                if dbClaimId is not None:
                    try:
                        parsedDbClaimId = int(dbClaimId)
                        stateUpdate["dbClaimId"] = parsedDbClaimId
                        # Flush buffered intake audit steps (receipt_uploaded, ai_extraction, policy_check)
                        # using the session claim UUID as the buffer key
                        sessionClaimId = state.get("claimId", "")
                        await flushSteps(sessionClaimId=sessionClaimId, dbClaimId=parsedDbClaimId)
                        # Write claim_submitted audit entry directly
                        await logIntakeStep(
                            claimId=parsedDbClaimId,
                            action="claim_submitted",
                            details={"claimNumber": claimNumber, "status": "pending"},
                        )
                        # Propagate intakeFindings from DB record to state for downstream agents
                        intakeFindingsFromDb = claimRecord.get("intake_findings")
                        if intakeFindingsFromDb and isinstance(intakeFindingsFromDb, dict):
                            stateUpdate["intakeFindings"] = intakeFindingsFromDb
                    except (TypeError, ValueError):
                        pass
            elif msg.name == "extractReceiptFields":
                stateUpdate["extractedReceipt"] = content
                # BUG-028: set ContextVar so submitClaim can inject confidenceScores
                extractedReceiptVar.set(content)
                # Buffer receipt_uploaded and ai_extraction audit steps directly in
                # intakeNode using the session claimId from state — this is the
                # authoritative buffer call (immune to LLM passing wrong claimId)
                sessionClaimId = state.get("claimId", "")
                if sessionClaimId:
                    fields = content.get("fields", {})
                    confidence = content.get("confidence", {})
                    imagePath = content.get("imagePath")
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="receipt_uploaded",
                        details={"imagePath": imagePath},
                    )
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="ai_extraction",
                        details={
                            "confidence": confidence,
                            "merchant": fields.get("merchant"),
                            "amount": fields.get("totalAmount"),
                            "fields": fields,
                        },
                    )
            elif msg.name == "convertCurrency":
                stateUpdate["currencyConversion"] = content
            elif msg.name == "searchPolicies":
                results = content.get("results", content.get("policies", []))
                if isinstance(results, list):
                    stateUpdate["violations"] = results
                else:
                    stateUpdate["violations"] = []
                # Buffer policy_check audit step — the LLM never passes claimId to the
                # tool so we buffer it here using the session claimId from state
                sessionClaimId = state.get("claimId", "")
                if sessionClaimId:
                    policyRefs = [
                        {"section": r.get("section"), "category": r.get("category"), "score": r.get("score")}
                        for r in (results if isinstance(results, list) else [])
                        if isinstance(r, dict)
                    ]
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="policy_check",
                        details={
                            "violations": [],
                            "policyRefs": policyRefs,
                            "compliant": True,
                            "query": "intake policy check",
                        },
                    )
        except (json.JSONDecodeError, TypeError):
            pass

    # Ensure violations is always written to state (empty list if no policy search ran)
    if "violations" not in stateUpdate:
        stateUpdate["violations"] = []

    logger.info("intakeNode completed", extra={"elapsed": f"{time.time() - nodeStart:.2f}s", "stateUpdateKeys": list(stateUpdate.keys())})
    return stateUpdate
