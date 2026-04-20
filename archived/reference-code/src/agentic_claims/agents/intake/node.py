"""Intake agent node - ReAct agent with all domain tools."""

import json
import logging

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_openrouter import ChatOpenRouter
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.intake.prompts.agentSystemPrompt import INTAKE_AGENT_SYSTEM_PROMPT
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
    5 domain tools for the intake workflow.

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

    # Build state update
    stateUpdate = {"messages": result["messages"]}

    # Detect if submitClaim tool was called successfully by scanning result messages
    # ToolMessages from LangGraph ReAct agent contain tool name and response content
    for msg in result["messages"]:
        if (
            hasattr(msg, "name")
            and msg.name == "submitClaim"
            and hasattr(msg, "content")
        ):
            # Parse tool response to check for success (no error key)
            try:
                content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                if isinstance(content, dict) and "error" not in content:
                    stateUpdate["claimSubmitted"] = True
                    break
            except (json.JSONDecodeError, TypeError):
                pass

    return stateUpdate
