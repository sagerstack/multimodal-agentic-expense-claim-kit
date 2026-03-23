"""Fraud detection agent node - identifies suspicious claims."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def fraudNode(state: ClaimState) -> dict:
    """Detect potential fraud in expense claims.

    Stub implementation for Phase 1 - validates parallel execution.
    Future phases will add fraud detection logic, pattern analysis.

    Args:
        state: Current claim state

    Returns:
        Partial state update with message (no status change - parallel node)
    """
    aiMessage = AIMessage(content="Hello world from Fraud Agent")
    return {"messages": [aiMessage]}
