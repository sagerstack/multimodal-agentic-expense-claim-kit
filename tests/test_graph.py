"""Integration tests for LangGraph StateGraph orchestration."""

import pytest
from langchain_core.messages import HumanMessage

from agentic_claims.core.graph import buildGraph
from agentic_claims.core.state import ClaimState


@pytest.mark.asyncio
async def test_graphFlowsThrough4Nodes():
    """Verify graph executes all 4 nodes and produces expected output."""
    # Build graph without checkpointer for unit testing
    graph = buildGraph().compile()

    # Create initial state
    initialState: ClaimState = {
        "claimId": "test-001",
        "status": "draft",
        "messages": [HumanMessage(content="Test claim")],
    }

    # Invoke graph
    result = await graph.ainvoke(initialState)

    # Verify final status set by Advisor
    assert result["status"] == "approved", "Advisor should set status to 'approved'"

    # Verify all agent messages present (1 human + 4 agent messages)
    assert len(result["messages"]) >= 5, "Should have at least 5 messages"

    # Extract message contents
    messageContents = [msg.content for msg in result["messages"]]
    allContent = " ".join(messageContents)

    # Verify each agent produced output
    assert "Intake Agent" in allContent, "Intake agent message missing"
    assert "Compliance Agent" in allContent, "Compliance agent message missing"
    assert "Fraud Agent" in allContent, "Fraud agent message missing"
    assert "Advisor Agent" in allContent, "Advisor agent message missing"


@pytest.mark.asyncio
async def test_complianceAndFraudRunInParallel():
    """Verify compliance and fraud nodes execute in the same superstep."""
    # Build graph without checkpointer
    graph = buildGraph().compile()

    # Create initial state
    initialState: ClaimState = {
        "claimId": "test-002",
        "status": "draft",
        "messages": [HumanMessage(content="Test parallel execution")],
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
    assert (
        abs(complianceIdx - fraudIdx) <= 1
    ), "Compliance and Fraud should run in parallel (same superstep)"


@pytest.mark.asyncio
async def test_claimStatePassedBetweenNodes():
    """Verify ClaimState preserves claimId and status transitions correctly."""
    # Build graph without checkpointer
    graph = buildGraph().compile()

    # Create initial state with specific claimId
    initialState: ClaimState = {
        "claimId": "test-003",
        "status": "draft",
        "messages": [HumanMessage(content="Test state preservation")],
    }

    # Invoke graph
    result = await graph.ainvoke(initialState)

    # Verify claimId preserved throughout execution
    assert result["claimId"] == "test-003", "ClaimId should be preserved"

    # Verify status transitions: draft -> submitted (by Intake) -> approved (by Advisor)
    assert result["status"] == "approved", "Final status should be 'approved'"

    # Note: We can't directly verify intermediate "submitted" status without
    # streaming or checkpointer, but we verify the final state is correct
