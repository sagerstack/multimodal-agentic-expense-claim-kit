"""State types for the intake-gpt replacement path."""

from typing import Literal, NotRequired, TypedDict


class WorkflowState(TypedDict):
    """Durable workflow state for intake-gpt."""

    goal: str
    currentStep: str
    readyForSubmission: bool
    status: str


class PendingInterrupt(TypedDict):
    """Structured interrupt payload stored in graph state."""

    id: str
    kind: str
    question: str
    contextMessage: str
    expectedResponseKind: str
    blockingStep: str
    status: str
    retryCount: int
    allowSideQuestions: bool


class LastUserTurn(TypedDict):
    """Latest user turn metadata."""

    message: str
    hasImage: bool


class InterruptResolution(TypedDict):
    """Resolved classification for a resumed interrupt turn."""

    outcome: Literal[
        "answer",
        "side_question",
        "cancel_claim",
        "reset_workflow",
        "start_new_claim",
        "end_conversation",
        "ambiguous",
    ]
    responseText: str
    summary: str


class IntakeGptState(TypedDict):
    """Nested state object persisted on ClaimState."""

    workflow: WorkflowState
    slots: dict
    pendingInterrupt: PendingInterrupt | None
    lastUserTurn: LastUserTurn
    lastResolution: InterruptResolution | None
    toolTrace: dict
    protocolGuardCount: int


class IntakeGptSubgraphState(TypedDict):
    """Inner subgraph state for the custom intake-gpt graph."""

    messages: list
    claimId: str
    threadId: str | None
    status: str
    intakeGpt: IntakeGptState
    pendingToolCallCount: NotRequired[int]
