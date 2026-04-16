"""Structured human-input tool for intake-gpt."""

import logging

from langchain_core.tools import tool
from langgraph.types import interrupt

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)

_BUTTON_INTERRUPT_KINDS = {"field_confirmation", "submit_confirmation"}


def _deriveUiKind(kind: str) -> str:
    return "buttons" if kind in _BUTTON_INTERRUPT_KINDS else "text"


def _deriveButtonOptions(kind: str) -> list[dict]:
    if kind not in _BUTTON_INTERRUPT_KINDS:
        return []
    return [
        {"label": "Yes", "value": "yes"},
        {"label": "No", "value": "no"},
    ]


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
    uiKind = _deriveUiKind(kind)
    logEvent(
        logger,
        "intake.gpt.interrupt.opened",
        logCategory="agent",
        agent="intake-gpt",
        message="requestHumanInput opened a structured interrupt",
        kind=kind,
        blockingStep=blockingStep,
        expectedResponseKind=expectedResponseKind,
        uiKind=uiKind,
    )
    payload = {
        "kind": kind,
        "question": question,
        "contextMessage": contextMessage,
        "expectedResponseKind": expectedResponseKind,
        "blockingStep": blockingStep,
        "allowSideQuestions": allowSideQuestions,
        "category": category,
        "uiKind": uiKind,
        "options": _deriveButtonOptions(kind),
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
