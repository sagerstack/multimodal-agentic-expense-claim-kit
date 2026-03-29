"""Tests for Intake Agent ReAct loop."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

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
            "getClaimSchema",
            "extractReceiptFields",
            "searchPolicies",
            "convertCurrency",
            "submitClaim",
        ]
        for expectedTool in expectedTools:
            assert expectedTool in toolNames, f"Tool {expectedTool} missing from agent"


def test_intakeAgentUsesOpenRouterModel():
    """Verify ChatOpenRouter is configured with OpenRouter API key."""
    with patch("agentic_claims.agents.intake.node.ChatOpenRouter") as mockChatOpenRouter:
        # Mock ChatOpenRouter constructor
        mockLlm = MagicMock()
        mockChatOpenRouter.return_value = mockLlm

        # Mock create_react_agent to avoid actual agent creation
        with patch("agentic_claims.agents.intake.node.create_react_agent") as mockCreateAgent:
            mockAgent = MagicMock()
            mockCreateAgent.return_value = mockAgent

            # Call getIntakeAgent
            getIntakeAgent()

            # Verify ChatOpenRouter was instantiated with OpenRouter config
            assert mockChatOpenRouter.called, "ChatOpenRouter should be instantiated"
            callArgs = mockChatOpenRouter.call_args

            # Check that openrouter_api_key is set
            assert "openrouter_api_key" in callArgs.kwargs, "openrouter_api_key should be set"
            # Verify base_url is NOT passed (ChatOpenRouter defaults to OpenRouter)
            assert "base_url" not in callArgs.kwargs, "base_url should not be passed to ChatOpenRouter"


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
        result = await intakeNode(state, RunnableConfig())

        # Verify result structure
        assert isinstance(result, dict), "Result should be a dict"
        assert "messages" in result, "Result should contain messages"
        assert isinstance(result["messages"], list), "Messages should be a list"

        # Verify agent was invoked
        mockAgent.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_intakeNodeSetsClaimSubmittedOnSuccessfulSubmitClaim():
    """Verify intakeNode sets claimSubmitted=True when submitClaim tool succeeds."""
    submitResult = json.dumps({"claim": {"id": 1}, "receipt": {"id": 2}})
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="Submit my claim"),
                AIMessage(content="Submitting..."),
                ToolMessage(
                    content=submitResult,
                    name="submitClaim",
                    tool_call_id="call_123",
                ),
                AIMessage(content="Your claim has been submitted."),
            ]
        }
    )

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        state: ClaimState = {
            "claimId": "test-002",
            "status": "draft",
            "messages": [HumanMessage(content="Submit my claim")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert result.get("claimSubmitted") is True, "claimSubmitted should be True after successful submitClaim"


@pytest.mark.asyncio
async def test_intakeNodeDoesNotSetClaimSubmittedOnError():
    """Verify intakeNode does NOT set claimSubmitted when submitClaim returns error."""
    errorResult = json.dumps({"error": "Connection failed"})
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="Submit my claim"),
                ToolMessage(
                    content=errorResult,
                    name="submitClaim",
                    tool_call_id="call_456",
                ),
                AIMessage(content="Submission failed."),
            ]
        }
    )

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        state: ClaimState = {
            "claimId": "test-003",
            "status": "draft",
            "messages": [HumanMessage(content="Submit my claim")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert "claimSubmitted" not in result, "claimSubmitted should NOT be set when submitClaim returns error"


@pytest.mark.asyncio
async def test_intakeNodeClaimSubmittedNotSetWithoutSubmitClaim():
    """Verify claimSubmitted is not set when no submitClaim tool call in messages."""
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="What is the meal limit?"),
                AIMessage(content="The meal limit is $50 per day."),
            ]
        }
    )

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        state: ClaimState = {
            "claimId": "test-004",
            "status": "draft",
            "messages": [HumanMessage(content="What is the meal limit?")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert "claimSubmitted" not in result, "claimSubmitted should NOT be set without submitClaim call"
