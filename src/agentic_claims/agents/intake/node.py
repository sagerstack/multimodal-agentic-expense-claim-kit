"""Intake agent node - ReAct agent with all domain tools."""

import json
import logging

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.intake.prompts.agentSystemPrompt import INTAKE_AGENT_SYSTEM_PROMPT
from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake.tools.submitClaim import submitClaim
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


def getIntakeAgent(useFallback: bool = False):
    """Create and return the compiled ReAct agent for intake processing.

    The agent uses ChatOpenAI with OpenRouter as the LLM and has access to
    4 domain tools for the intake workflow.

    Args:
        useFallback: If True, use fallback LLM model instead of primary

    Returns:
        Compiled ReAct agent graph
    """
    settings = getSettings()

    # Select model based on fallback flag
    modelName = settings.openrouter_fallback_model_llm if useFallback else settings.openrouter_model_llm

    # Instantiate ChatOpenAI with OpenRouter configuration
    llm = ChatOpenAI(
        model=modelName,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0.7,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Collect intake tools
    tools = [
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


async def intakeNode(state: ClaimState) -> dict:
    """Process claim intake through ReAct agent loop.

    This node wraps the ReAct agent and manages state updates. The agent
    handles the full conversational loop internally (tool calling, reasoning, etc.).

    Args:
        state: Current claim state with messages

    Returns:
        Partial state update with new messages and optional status/fields
    """
    settings = getSettings()

    # Get the ReAct agent
    agent = getIntakeAgent()

    # Prepare input for agent (messages only)
    agentInput = {"messages": state["messages"]}

    # Invoke agent with 402 fallback retry
    try:
        result = await agent.ainvoke(agentInput)
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
            result = await fallbackAgent.ainvoke(agentInput)
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
