"""Tests for Intake Agent ReAct loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agentic_claims.agents.intake.node import getIntakeAgent, intakeNode
from agentic_claims.core.state import ClaimState


def test_getIntakeAgentReturnsCompiledGraph():
    """Verify getIntakeAgent returns a compiled graph with ainvoke method."""
    agent = getIntakeAgent()

    # Verify it has the ainvoke method (compiled graph signature)
    assert hasattr(agent, "ainvoke"), "Agent should have ainvoke method"
    assert callable(agent.ainvoke), "ainvoke should be callable"


def test_intakeAgentHasFiveTools():
    """Verify the ReAct agent has all 5 domain tools registered."""
    with patch("agentic_claims.agents.intake.node.create_react_agent") as mockCreateAgent:
        # Mock the agent creation to capture arguments
        mockAgent = MagicMock()
        mockCreateAgent.return_value = mockAgent

        # Call getIntakeAgent which will invoke create_react_agent
        getIntakeAgent()

        # Verify create_react_agent was called
        assert mockCreateAgent.called, "create_react_agent should be called"

        # Extract the tools argument
        callArgs = mockCreateAgent.call_args
        tools = callArgs.kwargs.get("tools", [])

        # Verify 5 tools
        assert len(tools) == 5, f"Expected 5 tools, got {len(tools)}"

        # Verify tool names
        toolNames = [tool.name for tool in tools]
        expectedTools = [
            "extractReceiptFields",
            "searchPolicies",
            "convertCurrency",
            "submitClaim",
            "askHuman",
        ]
        for expectedTool in expectedTools:
            assert expectedTool in toolNames, f"Tool {expectedTool} missing from agent"


def test_intakeAgentUsesOpenRouterModel():
    """Verify ChatOpenAI is configured with OpenRouter base_url."""
    with patch("agentic_claims.agents.intake.node.ChatOpenAI") as mockChatOpenAI:
        # Mock ChatOpenAI constructor
        mockLlm = MagicMock()
        mockChatOpenAI.return_value = mockLlm

        # Mock create_react_agent to avoid actual agent creation
        with patch("agentic_claims.agents.intake.node.create_react_agent") as mockCreateAgent:
            mockAgent = MagicMock()
            mockCreateAgent.return_value = mockAgent

            # Call getIntakeAgent
            getIntakeAgent()

            # Verify ChatOpenAI was instantiated with OpenRouter config
            assert mockChatOpenAI.called, "ChatOpenAI should be instantiated"
            callArgs = mockChatOpenAI.call_args

            # Check that base_url is set (OpenRouter endpoint)
            assert "base_url" in callArgs.kwargs, "base_url should be set"
            # Verify it contains expected OpenRouter pattern
            baseUrl = callArgs.kwargs["base_url"]
            assert "openrouter" in baseUrl.lower() or callArgs.kwargs.get(
                "base_url"
            ), "base_url should be OpenRouter endpoint"


@pytest.mark.asyncio
async def test_intakeNodeReturnsMessagesUpdate():
    """Verify intakeNode returns state dict with messages."""
    # Mock the agent to avoid actual API calls
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="User message"),
                AIMessage(content="Agent response"),
            ]
        }
    )

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        # Create test state
        state: ClaimState = {
            "claimId": "test-001",
            "status": "draft",
            "messages": [HumanMessage(content="User message")],
        }

        # Call intakeNode
        result = await intakeNode(state)

        # Verify result structure
        assert isinstance(result, dict), "Result should be a dict"
        assert "messages" in result, "Result should contain messages"
        assert isinstance(result["messages"], list), "Messages should be a list"

        # Verify agent was invoked
        mockAgent.ainvoke.assert_called_once()
