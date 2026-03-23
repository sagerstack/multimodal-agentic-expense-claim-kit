"""Compliance agent node - validates claims against policy rules."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def complianceNode(state: ClaimState) -> dict:
    """Check claim compliance with company policies.

    Stub implementation for Phase 1 - validates parallel execution.
    Future phases will add policy rule engine, validation logic.

    Args:
        state: Current claim state

    Returns:
        Partial state update with message (no status change - parallel node)
    """
    aiMessage = AIMessage(content="Hello world from Compliance Agent")
    return {"messages": [aiMessage]}
