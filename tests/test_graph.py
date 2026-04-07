"""Integration tests for LangGraph StateGraph orchestration."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agentic_claims.core.graph import buildGraph
from agentic_claims.core.state import ClaimState


async def _mockMarkAiReviewedNode(state: ClaimState) -> dict:
    """Mock markAiReviewedNode that skips DB call."""
    return {"status": "ai_reviewed"}


async def _mockComplianceNode(state: ClaimState) -> dict:
    """Mock complianceNode that returns a pass verdict without LLM calls."""
    return {
        "messages": [AIMessage(content="**Compliance Check**: PASS — No violations found.")],
        "complianceFindings": {"verdict": "pass", "violations": [], "summary": "No violations found."},
    }


async def _mockFraudNode(state: ClaimState) -> dict:
    """Mock fraudNode that returns a clear verdict without LLM/DB calls."""
    return {
        "messages": [AIMessage(content="**Fraud Check**: CLEAR — No fraud indicators detected.")],
        "fraudFindings": {"verdict": "clear", "flags": [], "duplicateClaims": [], "summary": "No fraud indicators detected."},
    }


async def _mockAdvisorNode(state: ClaimState) -> dict:
    """Mock advisorNode that returns an approval without LLM calls."""
    return {
        "messages": [AIMessage(content="**Advisor Decision**: APPROVED — Claim approved by advisor agent.")],
        "advisorDecision": "approved",
    }


@pytest.mark.asyncio
async def test_pendingClaimEndsAfterIntake():
    """Verify pending claim (not submitted) ends after intake without routing to compliance/fraud."""
    # Mock intakeNode to avoid API calls
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Intake processing, not submitted yet")],
            "claimSubmitted": False,  # Key: claim NOT submitted
        }

    with patch("agentic_claims.core.graph.intakeNode", mockIntakeNode):
        # Build graph without checkpointer
        graph = buildGraph().compile()

        # Create initial state
        initialState: ClaimState = {
            "claimId": "test-pending",
            "status": "draft",
            "messages": [HumanMessage(content="Test pending claim")],
            "claimSubmitted": False,
        }

        # Invoke graph
        result = await graph.ainvoke(initialState)

        # Verify claimSubmitted is still False
        assert result.get("claimSubmitted", False) is False, "Claim should not be submitted"

        # Verify graph ended after intake (no compliance/fraud/advisor messages)
        messageContents = [msg.content for msg in result["messages"]]
        allContent = " ".join(messageContents)

        assert "Intake processing" in allContent, "Intake message should be present"
        assert "Compliance Check" not in allContent, "Compliance should NOT run"
        assert "Fraud Check" not in allContent, "Fraud should NOT run"
        assert "Advisor Decision" not in allContent, "Advisor should NOT run"


@pytest.mark.asyncio
async def test_submittedClaimRoutesToComplianceAndFraud():
    """Verify submitted claim routes to compliance and fraud nodes."""
    # Mock intakeNode to simulate claim submission
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Claim submitted successfully")],
            "claimSubmitted": True,  # Key: claim IS submitted
        }

    with (
        patch("agentic_claims.core.graph.intakeNode", mockIntakeNode),
        patch("agentic_claims.core.graph.complianceNode", _mockComplianceNode),
        patch("agentic_claims.core.graph.fraudNode", _mockFraudNode),
        patch("agentic_claims.core.graph.advisorNode", _mockAdvisorNode),
        patch("agentic_claims.core.graph.markAiReviewedNode", _mockMarkAiReviewedNode),
    ):
        # Build graph without checkpointer
        graph = buildGraph().compile()

        # Create initial state
        initialState: ClaimState = {
            "claimId": "test-submitted",
            "status": "draft",
            "messages": [HumanMessage(content="Submit this claim")],
            "claimSubmitted": False,  # Will be set to True by intake
        }

        # Invoke graph
        result = await graph.ainvoke(initialState)

        # Verify claimSubmitted is True
        assert result.get("claimSubmitted", False) is True, "Claim should be submitted"

        # Verify all agents ran (intake + compliance + fraud + markAiReviewed + advisor)
        messageContents = [msg.content for msg in result["messages"]]
        allContent = " ".join(messageContents)

        assert "Claim submitted" in allContent, "Intake message should be present"
        assert "Compliance Check" in allContent, "Compliance should run"
        assert "Fraud Check" in allContent, "Fraud should run"
        assert "Advisor Decision" in allContent, "Advisor should run"


@pytest.mark.asyncio
async def test_complianceAndFraudRunInParallel():
    """Verify compliance and fraud nodes execute in the same superstep."""
    # Mock intakeNode to simulate claim submission
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Claim submitted for parallel processing")],
            "claimSubmitted": True,
        }

    with (
        patch("agentic_claims.core.graph.intakeNode", mockIntakeNode),
        patch("agentic_claims.core.graph.complianceNode", _mockComplianceNode),
        patch("agentic_claims.core.graph.fraudNode", _mockFraudNode),
        patch("agentic_claims.core.graph.advisorNode", _mockAdvisorNode),
        patch("agentic_claims.core.graph.markAiReviewedNode", _mockMarkAiReviewedNode),
    ):
        # Build graph without checkpointer
        graph = buildGraph().compile()

        # Create initial state
        initialState: ClaimState = {
            "claimId": "test-parallel",
            "status": "draft",
            "messages": [HumanMessage(content="Test parallel execution")],
            "claimSubmitted": False,
        }

        # Stream graph execution to capture node execution order
        updates = []
        async for update in graph.astream(initialState, stream_mode="updates"):
            # Each update is a dict with node names as keys
            updates.append(list(update.keys()))

        # Flatten to get all node names in execution order
        allNodes = [node for nodeList in updates for node in nodeList]

        # Verify intake runs first
        assert allNodes[0] == "intake", "Intake should run first"

        # Find positions of compliance and fraud
        complianceIdx = allNodes.index("compliance")
        fraudIdx = allNodes.index("fraud")
        advisorIdx = allNodes.index("advisor")

        # Verify compliance and fraud run before advisor
        assert (
            complianceIdx < advisorIdx and fraudIdx < advisorIdx
        ), "Compliance and Fraud must run before Advisor"

        # Verify compliance and fraud are in adjacent positions (same superstep)
        # After the evaluator gate and postSubmission node, they fan out in parallel
        assert (
            abs(complianceIdx - fraudIdx) <= 1
        ), "Compliance and Fraud should run in parallel (same superstep)"

        # Verify markAiReviewed runs between compliance/fraud and advisor
        markReviewedIdx = allNodes.index("markAiReviewed")
        assert (
            complianceIdx < markReviewedIdx < advisorIdx
        ), "markAiReviewed should run between compliance/fraud fan-in and advisor"


@pytest.mark.asyncio
async def test_claimStatePassedBetweenNodes():
    """Verify ClaimState preserves claimId and status transitions correctly."""
    # Mock intakeNode
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Intake complete")],
            "claimSubmitted": True,
        }

    with (
        patch("agentic_claims.core.graph.intakeNode", mockIntakeNode),
        patch("agentic_claims.core.graph.complianceNode", _mockComplianceNode),
        patch("agentic_claims.core.graph.fraudNode", _mockFraudNode),
        patch("agentic_claims.core.graph.advisorNode", _mockAdvisorNode),
        patch("agentic_claims.core.graph.markAiReviewedNode", _mockMarkAiReviewedNode),
    ):
        # Build graph without checkpointer
        graph = buildGraph().compile()

        # Create initial state with specific claimId
        initialState: ClaimState = {
            "claimId": "test-003",
            "status": "draft",
            "messages": [HumanMessage(content="Test state preservation")],
            "claimSubmitted": False,
        }

        # Invoke graph
        result = await graph.ainvoke(initialState)

        # Verify claimId preserved throughout execution
        assert result["claimId"] == "test-003", "ClaimId should be preserved"

        # Verify status transitions: mock advisor returns "approved"
        assert result["status"] in ("ai_approved", "escalated", "ai_rejected", "ai_reviewed"), "Final status should be a valid terminal status"


@pytest.mark.asyncio
async def test_evaluatorGateWithPendingClaim():
    """Verify evaluator gate correctly routes pending claim to END."""
    # Mock intakeNode to NOT submit claim
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Need more information")],
            # Explicitly do NOT set claimSubmitted to True
        }

    with patch("agentic_claims.core.graph.intakeNode", mockIntakeNode):
        # Build graph
        graph = buildGraph().compile()

        # Create initial state
        initialState: ClaimState = {
            "claimId": "test-gate-pending",
            "status": "draft",
            "messages": [HumanMessage(content="Unclear receipt")],
        }

        # Stream to see node execution
        nodesSeen = []
        async for update in graph.astream(initialState, stream_mode="updates"):
            nodesSeen.extend(list(update.keys()))

        # Should only see intake node (and postSubmission should NOT execute)
        assert "intake" in nodesSeen, "Intake should execute"
        assert "compliance" not in nodesSeen, "Compliance should NOT execute"
        assert "fraud" not in nodesSeen, "Fraud should NOT execute"
        assert "advisor" not in nodesSeen, "Advisor should NOT execute"


@pytest.mark.asyncio
async def test_evaluatorGateWithSubmittedClaim():
    """Verify evaluator gate correctly routes submitted claim to compliance+fraud."""
    # Mock intakeNode to submit claim
    async def mockIntakeNode(state: ClaimState) -> dict:
        return {
            "messages": [AIMessage(content="Claim submitted")],
            "claimSubmitted": True,  # Key flag
        }

    with (
        patch("agentic_claims.core.graph.intakeNode", mockIntakeNode),
        patch("agentic_claims.core.graph.markAiReviewedNode", _mockMarkAiReviewedNode),
    ):
        # Build graph
        graph = buildGraph().compile()

        # Create initial state
        initialState: ClaimState = {
            "claimId": "test-gate-submitted",
            "status": "draft",
            "messages": [HumanMessage(content="Complete claim")],
        }

        # Stream to see node execution
        nodesSeen = []
        async for update in graph.astream(initialState, stream_mode="updates"):
            nodesSeen.extend(list(update.keys()))

        # Should see intake, postSubmission, compliance, fraud, markAiReviewed, advisor
        assert "intake" in nodesSeen, "Intake should execute"
        assert "postSubmission" in nodesSeen, "PostSubmission should execute"
        assert "compliance" in nodesSeen, "Compliance should execute"
        assert "fraud" in nodesSeen, "Fraud should execute"
        assert "markAiReviewed" in nodesSeen, "markAiReviewed should execute"
        assert "advisor" in nodesSeen, "Advisor should execute"
