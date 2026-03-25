"""Intake agent node - ReAct agent with all domain tools."""

import json

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agentic_claims.agents.intake.prompts.agentSystemPrompt import INTAKE_AGENT_SYSTEM_PROMPT
from agentic_claims.agents.intake.tools.askHuman import askHuman
from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake.tools.submitClaim import submitClaim
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState


def getIntakeAgent():
    """Create and return the compiled ReAct agent for intake processing.

    The agent uses ChatOpenAI with OpenRouter as the LLM and has access to all
    5 domain tools for the intake workflow.

    Returns:
        Compiled ReAct agent graph
    """
    settings = getSettings()

    # Instantiate ChatOpenAI with OpenRouter configuration
    llm = ChatOpenAI(
        model=settings.openrouter_model_llm,
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        temperature=0.7,
        max_retries=settings.openrouter_max_retries,
    )

    # Collect all 5 intake tools
    tools = [
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


async def intakeNode(state: ClaimState) -> dict:
    """Process claim intake through ReAct agent loop.

    This node wraps the ReAct agent and manages state updates. The agent
    handles the full conversational loop internally (tool calling, reasoning, etc.).

    Args:
        state: Current claim state with messages

    Returns:
        Partial state update with new messages and optional status/fields
    """
    # Get the ReAct agent
    agent = getIntakeAgent()

    # Prepare input for agent (messages only)
    agentInput = {"messages": state["messages"]}

    # Invoke agent - it manages its own tool loop
    result = await agent.ainvoke(agentInput)

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
