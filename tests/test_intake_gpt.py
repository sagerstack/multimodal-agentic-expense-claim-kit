"""Tests for the intake-gpt replacement path."""

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_claims.agents.intake_gpt.graph import (
    applyToolResultsNode,
    buildIntakeGptSubgraph,
    reasonNode,
    turnEntryNode,
)
from agentic_claims.agents.intake_gpt.node import intakeGptNode
from agentic_claims.core.state import ClaimState


@pytest.mark.asyncio
async def test_intakeGptNodeReturnsMessageDeltaAndNestedState():
    """Wrapper should append only new messages and propagate intakeGpt state."""
    mockSubgraph = AsyncMock()
    mockSubgraph.ainvoke = AsyncMock(
        return_value={
            "messages": [
                HumanMessage(content="hello"),
                AIMessage(content="Hi there."),
            ],
            "intakeGpt": {
                "workflow": {
                    "goal": "assist_claimant",
                    "currentStep": "plain_chat",
                    "readyForSubmission": False,
                    "status": "active",
                },
                "slots": {},
                "pendingInterrupt": None,
                "lastUserTurn": {"message": "hello", "hasImage": False},
                "lastResolution": None,
                "toolTrace": {},
                "protocolGuardCount": 0,
            },
        }
    )

    state: ClaimState = {
        "claimId": "claim-gpt-001",
        "status": "draft",
        "messages": [HumanMessage(content="hello")],
    }

    with patch(
        "agentic_claims.agents.intake_gpt.node._getIntakeGptSubgraph",
        return_value=mockSubgraph,
    ):
        result = await intakeGptNode(state, RunnableConfig())

    assert result["messages"] == [AIMessage(content="Hi there.")]
    assert result["intakeGpt"]["workflow"]["currentStep"] == "plain_chat"
    mockSubgraph.ainvoke.assert_called_once()


def test_buildAgentLlmCanReceiveReasoningConfig():
    """Feature slice depends on reasoning summaries being enabled on intake-gpt."""
    from agentic_claims.agents.shared.llmFactory import buildAgentLlm

    settings = MagicMock()
    settings.openrouter_fallback_model_llm = "fallback-model"
    settings.openrouter_model_llm = "primary-model"
    settings.openrouter_api_key = "test-key"
    settings.openrouter_max_retries = 1
    settings.openrouter_llm_max_tokens = 512

    with patch("agentic_claims.agents.shared.llmFactory.ChatOpenRouter") as mockCtor:
        mockLlm = MagicMock()
        mockCtor.return_value = mockLlm
        buildAgentLlm(
            settings,
            reasoning={"enabled": True, "summary": "concise"},
        )

    assert mockCtor.called
    assert mockCtor.call_args.kwargs["reasoning"] == {
        "enabled": True,
        "summary": "concise",
    }


@pytest.mark.asyncio
async def test_buildIntakeGptSubgraphHandlesPlainHelloTurn():
    """Regression guard: reason node must return a dict, not a bare coroutine."""

    class FakeBoundLlm:
        async def ainvoke(self, messages):
            return AIMessage(content="Hi there.")

    class FakeLlm:
        def bind_tools(self, tools):
            return FakeBoundLlm()

    subgraph = buildIntakeGptSubgraph(FakeLlm())
    result = await subgraph.ainvoke(
        {
            "claimId": "claim-gpt-002",
            "threadId": "thread-gpt-002",
            "status": "draft",
            "messages": [HumanMessage(content="hello")],
        }
    )

    assert result["messages"][-1].content == "Hi there."
    assert result["intakeGpt"]["workflow"]["currentStep"] == "plain_chat"


@pytest.mark.asyncio
async def test_reasonNodePersistsFieldConfirmationInterrupt():
    """Receipt slice should persist a structured pending interrupt before pause."""

    class FakeBoundLlm:
        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "requestHumanInput",
                        "args": {
                            "kind": "field_confirmation",
                            "question": "Does this look correct?",
                            "blockingStep": "field_confirmation",
                        },
                        "id": "call_field_confirmation",
                    }
                ],
            )

    class FakeLlm:
        def __init__(self):
            self.boundToolNames = []

        def bind_tools(self, tools):
            self.boundToolNames = [tool.name for tool in tools]
            return FakeBoundLlm()

    llm = FakeLlm()
    state = {
        "claimId": "claim-gpt-004",
        "threadId": "thread-gpt-004",
        "status": "draft",
        "messages": [HumanMessage(content="I've uploaded a receipt image for claim claim-gpt-004. Please process it using extractReceiptFields.")],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "receipt_extracted",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {
                        "merchant": "Kopitiam",
                        "date": "2026-04-13",
                        "totalAmount": 12.5,
                        "currency": "SGD",
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.92,
                        "totalAmount": 0.98,
                        "currency": 0.99,
                    },
                },
                "category": "meals",
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "", "hasImage": True},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=llm)

    assert "requestHumanInput" in llm.boundToolNames
    pendingInterrupt = result["intakeGpt"]["pendingInterrupt"]
    assert pendingInterrupt is not None
    assert pendingInterrupt["kind"] == "field_confirmation"
    assert pendingInterrupt["blockingStep"] == "field_confirmation"
    assert "| Field | Value | Confidence |" in pendingInterrupt["contextMessage"]
    assert "Kopitiam" in pendingInterrupt["contextMessage"]
    assert result["intakeGpt"]["workflow"]["status"] == "blocked"


@pytest.mark.asyncio
async def test_reasonNodeOverridesModelProseWithReceiptTable():
    """Runtime should force tabular context for field confirmation."""

    class FakeBoundLlm:
        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "requestHumanInput",
                        "args": {
                            "kind": "field_confirmation",
                            "question": "Please confirm if the extracted details are correct.",
                            "blockingStep": "field_confirmation",
                            "contextMessage": (
                                "Here are the extracted details from your receipt:\n\n"
                                "Merchant: DIG.\nDate: 2024-05-28"
                            ),
                        },
                        "id": "call_field_confirmation",
                    }
                ],
            )

    class FakeLlm:
        def bind_tools(self, tools):
            return FakeBoundLlm()

    state = {
        "claimId": "claim-gpt-004b",
        "threadId": "thread-gpt-004b",
        "status": "draft",
        "messages": [
            HumanMessage(
                content=(
                    "I've uploaded a receipt image for claim claim-gpt-004b. "
                    "Please process it using extractReceiptFields."
                )
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "receipt_extracted",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {
                        "merchant": "DIG.",
                        "date": "2024-05-28",
                        "totalAmount": 16.2,
                        "currency": "USD",
                        "lineItems": [
                            {"description": "1 Custom with Protein", "amount": 0.0},
                            {"description": "Charred Chicken", "amount": 13.4},
                        ],
                        "tax": 1.19,
                        "paymentMethod": "VISA CREDIT",
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.92,
                        "totalAmount": 0.98,
                        "currency": 0.99,
                        "lineItems": 0.88,
                        "tax": 0.85,
                        "paymentMethod": 0.9,
                    },
                },
                "currencyConversion": {
                    "supported": True,
                    "originalAmount": 16.2,
                    "fromCurrency": "USD",
                    "convertedAmount": 20.64,
                    "rate": 1.2739,
                },
                "category": "meals",
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "", "hasImage": True},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=FakeLlm())

    pendingInterrupt = result["intakeGpt"]["pendingInterrupt"]
    assert pendingInterrupt is not None
    assert "| Field | Value | Confidence |" in pendingInterrupt["contextMessage"]
    assert "Here are the extracted details from your receipt" not in pendingInterrupt["contextMessage"]
    assert "Total: USD 16.2 → SGD 20.64 (rate: 1.2739)" in pendingInterrupt["contextMessage"]


def test_applyToolResultsNodeMapsExtractedReceiptIntoDurableState():
    """Tool results should populate top-level receipt fields and derived category."""
    extractedReceipt = {
        "fields": {
            "merchant": "Kopitiam",
            "date": "2026-04-13",
            "totalAmount": 12.5,
            "currency": "SGD",
        },
        "confidence": {
            "merchant": 0.95,
            "date": 0.92,
            "totalAmount": 0.98,
            "currency": 0.99,
        },
    }
    state = {
        "claimId": "claim-gpt-005",
        "threadId": "thread-gpt-005",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps(extractedReceipt),
                name="extractReceiptFields",
                tool_call_id="call_extract",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "receipt_received",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {},
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "", "hasImage": True},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = applyToolResultsNode(state)

    assert result["extractedReceipt"] == extractedReceipt
    assert result["intakeGpt"]["slots"]["extractedReceipt"] == extractedReceipt
    assert result["intakeGpt"]["slots"]["category"] == "meals"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "receipt_extracted"


def test_applyToolResultsNodeClearsPendingInterruptOnResume():
    """Resumed requestHumanInput result should clear the pending interrupt."""
    state = {
        "claimId": "claim-gpt-006",
        "threadId": "thread-gpt-006",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps({"response": "yes"}),
                name="requestHumanInput",
                tool_call_id="call_field_confirmation",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "field_confirmation",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {},
            "pendingInterrupt": {
                "id": "call_field_confirmation",
                "kind": "field_confirmation",
                "question": "Does this look correct?",
                "contextMessage": "",
                "expectedResponseKind": "confirmation",
                "blockingStep": "field_confirmation",
                "status": "pending",
                "retryCount": 0,
                "allowSideQuestions": True,
            },
            "lastUserTurn": {"message": "yes", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = applyToolResultsNode(state)

    assert result["intakeGpt"]["pendingInterrupt"] is None
    assert result["intakeGpt"]["lastResolution"]["outcome"] == "answer"
    assert result["intakeGpt"]["slots"]["fieldConfirmationResponse"] == "yes"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "field_confirmation_answered"


def test_turnEntryNodeResetsReceiptStateOnFreshUpload():
    """A fresh uploaded image should supersede prior confirmed-receipt state."""
    state = {
        "claimId": "claim-gpt-007",
        "threadId": "thread-gpt-007",
        "status": "draft",
        "messages": [
            HumanMessage(
                content=(
                    "I've uploaded a receipt image for claim claim-gpt-007. "
                    "Please process it using extractReceiptFields."
                )
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "field_confirmation_answered",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {
                "extractedReceipt": {"fields": {"merchant": "Old Receipt"}},
                "currencyConversion": {"supported": True, "convertedAmount": 12.34},
                "fieldConfirmationResponse": "looks correct",
            },
            "pendingInterrupt": {
                "id": "old_interrupt",
                "kind": "field_confirmation",
                "question": "Old question",
                "contextMessage": "Old summary",
                "expectedResponseKind": "confirmation",
                "blockingStep": "field_confirmation",
                "status": "pending",
                "retryCount": 0,
                "allowSideQuestions": True,
            },
            "lastUserTurn": {"message": "looks correct", "hasImage": False},
            "lastResolution": {
                "outcome": "answer",
                "responseText": "looks correct",
                "summary": "User confirmed the pending receipt details.",
            },
            "toolTrace": {"extractReceiptFields": {"name": "extractReceiptFields", "output": {}}},
            "protocolGuardCount": 0,
        },
    }

    result = turnEntryNode(state)

    intakeState = result["intakeGpt"]
    assert intakeState["workflow"]["currentStep"] == "receipt_received"
    assert intakeState["workflow"]["status"] == "active"
    assert intakeState["slots"] == {}
    assert intakeState["toolTrace"] == {}
    assert intakeState["pendingInterrupt"] is None
    assert intakeState["lastResolution"] is None
    assert intakeState["lastUserTurn"]["hasImage"] is True


@contextmanager
def _captureIntakeGptLogEvents():
    captured = []

    def _capture(_logger, eventName, *, level=None, message=None, payload=None, **fields):
        captured.append((eventName, fields))

    patchTargets = [
        "agentic_claims.agents.intake_gpt.node.logEvent",
        "agentic_claims.agents.intake_gpt.graph.logEvent",
        "agentic_claims.agents.intake_gpt.tools.requestHumanInput.logEvent",
    ]
    patches = [patch(target, side_effect=_capture) for target in patchTargets]
    for p in patches:
        p.start()
    try:
        yield captured
    finally:
        for p in patches:
            p.stop()


@pytest.mark.asyncio
async def test_intakeGptLogsWrapperLifecycle():
    """New path should emit the same kind of wrapper lifecycle events as legacy intake."""
    mockSubgraph = AsyncMock()
    mockSubgraph.ainvoke = AsyncMock(
        return_value={
            "messages": [HumanMessage(content="hello"), AIMessage(content="Hi.")],
            "intakeGpt": {
                "workflow": {
                    "goal": "assist_claimant",
                    "currentStep": "plain_chat",
                    "readyForSubmission": False,
                    "status": "active",
                },
                "slots": {},
                "pendingInterrupt": None,
                "lastUserTurn": {"message": "hello", "hasImage": False},
                "lastResolution": None,
                "toolTrace": {},
                "protocolGuardCount": 0,
            },
        }
    )
    state: ClaimState = {
        "claimId": "claim-gpt-003",
        "threadId": "thread-gpt-003",
        "turnIndex": 2,
        "status": "draft",
        "messages": [HumanMessage(content="hello")],
    }

    with (
        patch(
            "agentic_claims.agents.intake_gpt.node._getIntakeGptSubgraph",
            return_value=mockSubgraph,
        ),
        _captureIntakeGptLogEvents() as events,
    ):
        await intakeGptNode(state, RunnableConfig())

    names = [name for name, _ in events]
    assert "intake.agent_invoked" in names
    assert "intake.completed" in names
    assert "intake.turn.end" in names
