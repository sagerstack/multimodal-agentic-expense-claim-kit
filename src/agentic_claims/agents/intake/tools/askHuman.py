"""Human-in-the-loop clarification tool using LangGraph interrupt."""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def askHuman(question: str, data: dict) -> dict:
    """Ask the human for clarification or confirmation.

    This tool pauses agent execution and waits for human input.
    Use when extracted data has low confidence or needs verification.

    Args:
        question: The clarification question to ask the human
        data: Context data to display to the human for decision-making

    Returns:
        Human response dict with action and data fields
    """
    # Pause execution and wait for human response
    response = interrupt({"question": question, "data": data})

    return response
