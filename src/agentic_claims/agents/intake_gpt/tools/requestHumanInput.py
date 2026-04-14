"""Structured human-input tool for intake-gpt."""

import logging

from langchain_core.tools import tool
from langgraph.types import interrupt

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


@tool
def requestHumanInput(
    kind: str,
    question: str,
    contextMessage: str = "",
    expectedResponseKind: str = "text",
    blockingStep: str = "",
    allowSideQuestions: bool = True,
    category: str = "",
) -> dict:
    """Pause the workflow and ask the user for structured input.

    The interrupt payload is durable workflow state. The runtime renders
    contextMessage as a normal assistant bubble and question as the active
    interrupt prompt.
    """
    logEvent(
        logger,
        "intake.gpt.interrupt.opened",
        logCategory="agent",
        agent="intake-gpt",
        message="requestHumanInput opened a structured interrupt",
        kind=kind,
        blockingStep=blockingStep,
        expectedResponseKind=expectedResponseKind,
    )
    payload = {
        "kind": kind,
        "question": question,
        "contextMessage": contextMessage,
        "expectedResponseKind": expectedResponseKind,
        "blockingStep": blockingStep,
        "allowSideQuestions": allowSideQuestions,
        "category": category,
    }
    response = interrupt(payload)
    logEvent(
        logger,
        "intake.gpt.interrupt.resumed",
        logCategory="agent",
        agent="intake-gpt",
        message="requestHumanInput resumed with user input",
        kind=kind,
        blockingStep=blockingStep,
    )
    return {"response": response}
