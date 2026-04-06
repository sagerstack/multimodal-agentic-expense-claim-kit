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


@pytest.mark.asyncio
async def test_intakeNodeFlushesAuditBufferAfterSubmission():
    """intakeNode calls flushSteps after submitClaim succeeds so intake audit steps are persisted."""
    submitResult = json.dumps({
        "claim": {"id": 7, "claim_number": "CLAIM-007"},
        "receipt": {"id": 3},
    })
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                ToolMessage(
                    content=submitResult,
                    name="submitClaim",
                    tool_call_id="call_flush_test",
                ),
                AIMessage(content="Claim submitted."),
            ]
        }
    )

    mockFlushSteps = AsyncMock()

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            state: ClaimState = {
                "claimId": "session-uuid-001",
                "status": "draft",
                "messages": [HumanMessage(content="Submit")],
            }
            result = await intakeNode(state, RunnableConfig())

    mockFlushSteps.assert_called_once_with(
        sessionClaimId="session-uuid-001",
        dbClaimId=7,
    )
    assert result.get("claimSubmitted") is True


@pytest.mark.asyncio
async def test_intakeNodeWritesClaimSubmittedAuditEntry():
    """intakeNode writes a claim_submitted audit log entry after successful submission."""
    submitResult = json.dumps({
        "claim": {"id": 9, "claim_number": "CLAIM-009"},
        "receipt": {"id": 5},
    })
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                ToolMessage(
                    content=submitResult,
                    name="submitClaim",
                    tool_call_id="call_audit_test",
                ),
                AIMessage(content="Claim submitted."),
            ]
        }
    )

    mockFlushSteps = AsyncMock()
    mockLogIntakeStep = AsyncMock()

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            with patch("agentic_claims.agents.intake.node.logIntakeStep", mockLogIntakeStep):
                state: ClaimState = {
                    "claimId": "session-uuid-002",
                    "status": "draft",
                    "messages": [HumanMessage(content="Submit")],
                }
                result = await intakeNode(state, RunnableConfig())

    mockLogIntakeStep.assert_called_once()
    callKwargs = mockLogIntakeStep.call_args.kwargs
    assert callKwargs["claimId"] == 9
    assert callKwargs["action"] == "claim_submitted"


@pytest.mark.asyncio
async def test_intakeNodeWritesIntakeFindingsToState():
    """intakeNode writes intakeFindings to state from submitClaim result."""
    submitResult = json.dumps({
        "claim": {
            "id": 11,
            "claim_number": "CLAIM-011",
            "intake_findings": {"employeeId": "EMP-123", "violations": []},
        },
        "receipt": {"id": 6},
    })
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                ToolMessage(
                    content=submitResult,
                    name="submitClaim",
                    tool_call_id="call_findings_test",
                ),
                AIMessage(content="Claim submitted."),
            ]
        }
    )

    mockFlushSteps = AsyncMock()

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            state: ClaimState = {
                "claimId": "session-uuid-003",
                "status": "draft",
                "messages": [HumanMessage(content="Submit")],
            }
            result = await intakeNode(state, RunnableConfig())

    assert "intakeFindings" in result
    assert result["intakeFindings"].get("employeeId") == "EMP-123"


@pytest.mark.asyncio
async def test_intakeNodeBuffersPolicyCheckFromSearchPoliciesResult():
    """intakeNode buffers a policy_check audit step when searchPolicies ToolMessage is present."""
    policyResult = json.dumps({
        "results": [
            {"section": "Meals", "category": "meals", "score": 0.9}
        ]
    })
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                ToolMessage(
                    content=policyResult,
                    name="searchPolicies",
                    tool_call_id="call_policy_test",
                ),
                AIMessage(content="Policy checked."),
            ]
        }
    )

    mockBufferStep = MagicMock()

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        with patch("agentic_claims.agents.intake.node.bufferStep", mockBufferStep):
            state: ClaimState = {
                "claimId": "session-uuid-policy",
                "status": "draft",
                "messages": [HumanMessage(content="Check policy")],
            }
            await intakeNode(state, RunnableConfig())

    mockBufferStep.assert_called_once_with(
        sessionClaimId="session-uuid-policy",
        action="policy_check",
        details={
            "violations": [],
            "policyRefs": [{"section": "Meals", "category": "meals", "score": 0.9}],
            "compliant": True,
            "query": "intake policy check",
        },
    )


@pytest.mark.asyncio
async def test_intakeNodeBuffersReceiptUploadedAndAiExtractionFromExtractReceiptFields():
    """intakeNode buffers receipt_uploaded and ai_extraction when extractReceiptFields ToolMessage is present."""
    extractResult = json.dumps({
        "fields": {"merchant": "TestMart", "totalAmount": 50.0},
        "confidence": {"merchant": 0.95},
        "imagePath": "uploads/test-session.jpg",
    })
    mockAgent = AsyncMock()
    mockAgent.ainvoke = AsyncMock(
        return_value={
            "messages": [
                ToolMessage(
                    content=extractResult,
                    name="extractReceiptFields",
                    tool_call_id="call_extract_test",
                ),
                AIMessage(content="Extracted receipt."),
            ]
        }
    )

    bufferedCalls = []
    mockBufferStep = MagicMock(side_effect=lambda **kwargs: bufferedCalls.append(kwargs))

    with patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent):
        with patch("agentic_claims.agents.intake.node.bufferStep", mockBufferStep):
            state: ClaimState = {
                "claimId": "session-uuid-extract",
                "status": "draft",
                "messages": [HumanMessage(content="Process receipt")],
            }
            result = await intakeNode(state, RunnableConfig())

    actions = [c["action"] for c in bufferedCalls]
    assert "receipt_uploaded" in actions
    assert "ai_extraction" in actions

    receiptStep = next(c for c in bufferedCalls if c["action"] == "receipt_uploaded")
    assert receiptStep["sessionClaimId"] == "session-uuid-extract"
    assert receiptStep["details"]["imagePath"] == "uploads/test-session.jpg"

    aiStep = next(c for c in bufferedCalls if c["action"] == "ai_extraction")
    assert aiStep["details"]["merchant"] == "TestMart"
