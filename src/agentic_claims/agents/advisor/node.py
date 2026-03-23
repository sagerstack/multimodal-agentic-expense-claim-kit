"""Advisor agent node - makes final claim decisions."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def advisorNode(state: ClaimState) -> dict:
    """Make final decision on claim approval or rejection.

    Stub implementation for Phase 1 - validates fan-in aggregation.
    Future phases will add decision logic based on compliance and fraud findings.

    Args:
        state: Current claim state

    Returns:
        Partial state update with message and final status decision
    """
    aiMessage = AIMessage(content="Hello world from Advisor Agent")
    return {"messages": [aiMessage], "status": "approved"}
