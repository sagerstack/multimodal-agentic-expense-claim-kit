"""Intake agent node - first step in claim processing."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def intakeNode(state: ClaimState) -> dict:
    """Process initial claim submission.

    Stub implementation for Phase 1 - validates the orchestration flow.
    Future phases will add receipt parsing, data extraction, validation.

    Args:
        state: Current claim state

    Returns:
        Partial state update with message and status transition to 'submitted'
    """
    aiMessage = AIMessage(content="Hello world from Intake Agent")
    return {"messages": [aiMessage], "status": "submitted"}
