"""askHuman tool — pauses the ReAct loop and requests user input via LangGraph interrupt."""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def askHuman(question: str) -> dict:
    """Pause the workflow and ask the user a question.

    Triggers a LangGraph interrupt, suspending the current graph execution
    and surfacing the question to the user. The graph resumes when the user
    responds, and this tool returns the user's response as a dict.

    Use this tool to:
    - Confirm extracted receipt details with the user before proceeding
    - Request justification for a policy violation before submitting

    Args:
        question: The question to present to the user.

    Returns:
        dict with the user's response, e.g. {"response": "Yes, looks correct."}
    """
    response = interrupt({"question": question})
    return response
