"""Tests for the intake-gpt replacement path."""

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_claims.agents.intake_gpt.graph import (
    _buildRuntimeContext,
    _classifyInterruptReply,
    applyToolResultsNode,
    buildIntakeGptSubgraph,
    interruptResolutionNode,
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
            "claimSubmitted": True,
            "claimNumber": "CLAIM-999",
            "dbClaimId": 999,
            "intakeFindings": {"justification": None},
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
    assert result["claimSubmitted"] is True
    assert result["claimNumber"] == "CLAIM-999"
    assert result["dbClaimId"] == 999
    assert result["intakeFindings"] == {"justification": None}
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


@pytest.mark.asyncio
async def test_reasonNodePersistsModelDerivedCategoryIntoFieldConfirmation():
    """Category supplied by the model should be persisted and shown in the confirmation table."""

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
                            "category": "meals",
                        },
                        "id": "call_field_confirmation",
                    }
                ],
            )

    class FakeLlm:
        def bind_tools(self, tools):
            return FakeBoundLlm()

    state = {
        "claimId": "claim-gpt-004c",
        "threadId": "thread-gpt-004c",
        "status": "draft",
        "messages": [
            HumanMessage(
                content=(
                    "I've uploaded a receipt image for claim claim-gpt-004c. "
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
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.92,
                        "totalAmount": 0.98,
                        "currency": 0.99,
                    },
                },
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "", "hasImage": True},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=FakeLlm())

    assert result["intakeGpt"]["slots"]["category"] == "meals"
    pendingInterrupt = result["intakeGpt"]["pendingInterrupt"]
    assert pendingInterrupt is not None
    assert "| Category | meals | Derived |" in pendingInterrupt["contextMessage"]


@pytest.mark.asyncio
async def test_reasonNodePersistsManualFxInterruptWhenConversionUnsupported():
    """Unsupported auto-conversion should route to a manual-FX interrupt, not prose."""

    class FakeBoundLlm:
        async def ainvoke(self, messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "requestHumanInput",
                        "args": {
                            "kind": "manual_fx_rate",
                            "question": "Can you share the exchange rate to SGD?",
                        },
                        "id": "call_manual_fx",
                    }
                ],
            )

    class FakeLlm:
        def bind_tools(self, tools):
            return FakeBoundLlm()

    state = {
        "claimId": "claim-gpt-manual-fx-001",
        "threadId": "thread-gpt-manual-fx-001",
        "status": "draft",
        "messages": [HumanMessage(content="Please continue processing this Vietnamese receipt.")],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "manual_fx_required",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {
                        "merchant": "Pho 24",
                        "date": "2026-04-13",
                        "totalAmount": 550000,
                        "currency": "₫",
                    },
                    "confidence": {
                        "merchant": 0.91,
                        "date": 0.89,
                        "totalAmount": 0.94,
                        "currency": 0.97,
                    },
                },
                "currencyConversion": {
                    "supported": False,
                    "currency": "₫",
                    "error": "unsupported",
                    "provider": "frankfurter",
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
    assert pendingInterrupt["kind"] == "manual_fx_rate"
    assert pendingInterrupt["blockingStep"] == "manual_fx_required"
    assert pendingInterrupt["expectedResponseKind"] == "exchange_rate"
    assert "| Field | Value | Confidence |" in pendingInterrupt["contextMessage"]
    assert "₫" in pendingInterrupt["question"]


@pytest.mark.asyncio
async def test_reasonNodeSkipsLlmAndGoesToFieldConfirmationAfterManualFx():
    """Once a manual FX rate is applied, the next step should be field confirmation directly."""

    class FakeLlm:
        def bind_tools(self, tools):
            raise AssertionError("LLM should not be invoked after a valid manual FX conversion")

    state = {
        "claimId": "claim-gpt-manual-fx-guard-001",
        "threadId": "thread-gpt-manual-fx-guard-001",
        "status": "draft",
        "messages": [HumanMessage(content="1 VND = 0.0000424 SGD")],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "currency_converted",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {
                        "merchant": "Cari Trường",
                        "date": "2018-08-16",
                        "totalAmount": 510000.0,
                        "currency": "₫",
                        "lineItems": [
                            {"description": "Bia tươi", "amount": 150000.0},
                        ],
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.98,
                        "totalAmount": 0.99,
                        "currency": 0.99,
                        "lineItems": 0.95,
                    },
                },
                "currencyConversion": {
                    "supported": True,
                    "manualOverride": True,
                    "originalAmount": 510000.0,
                    "fromCurrency": "VND",
                    "convertedAmount": 21.62,
                    "convertedCurrency": "SGD",
                    "rate": 0.0000424,
                    "provider": "manual_user_input",
                },
                "category": "meals",
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "1 VND = 0.0000424 SGD", "hasImage": False},
            "lastResolution": {
                "outcome": "answer",
                "responseText": "1 VND = 0.0000424 SGD",
                "summary": "User provided a manual exchange rate to SGD.",
            },
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=FakeLlm())

    pendingInterrupt = result["intakeGpt"]["pendingInterrupt"]
    assert pendingInterrupt is not None
    assert pendingInterrupt["kind"] == "field_confirmation"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "field_confirmation"
    assert "manual rate: 0.0000424" in pendingInterrupt["contextMessage"]


@pytest.mark.asyncio
async def test_reasonNodeSkipsLlmAndCallsSubmitClaimAfterSubmitConfirmation():
    """After a confirmed submit checkpoint, runtime should move directly to submitClaim."""

    class FakeLlm:
        def bind_tools(self, tools):
            raise AssertionError("LLM should not be invoked after submit_confirmation_answered")

    state = {
        "claimId": "claim-gpt-submit-001",
        "threadId": "thread-gpt-submit-001",
        "status": "draft",
        "messages": [HumanMessage(content="yes")],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "submit_confirmation_answered",
                "readyForSubmission": True,
                "status": "active",
            },
            "slots": {
                "claimData": {"amountSgd": 20.64, "category": "meals"},
                "receiptData": {
                    "merchant": "DIG.",
                    "date": "2024-05-28",
                    "totalAmount": 16.2,
                    "currency": "USD",
                },
                "intakeFindings": {"policyViolation": None, "justification": None},
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "yes", "hasImage": False},
            "lastResolution": {
                "outcome": "answer",
                "responseText": "yes",
                "summary": "User confirmed that the claim should be submitted.",
            },
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=FakeLlm())

    message = result["messages"][-1]
    assert isinstance(message, AIMessage)
    assert message.tool_calls
    assert message.tool_calls[0]["name"] == "submitClaim"
    assert message.tool_calls[0]["args"]["sessionClaimId"] == "claim-gpt-submit-001"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "submitting_claim"


@pytest.mark.asyncio
async def test_reasonNodeSkipsLlmAndCallsSubmitClaimAfterPolicyJustificationWithoutPrebuiltDraft():
    """A stored justification should be enough to rebuild the draft claim bundle and submit."""

    class FakeLlm:
        def bind_tools(self, tools):
            raise AssertionError("LLM should not be invoked after policy_justification_answered")

    state = {
        "claimId": "claim-gpt-submit-justification-001",
        "threadId": "thread-gpt-submit-justification-001",
        "status": "draft",
        "messages": [HumanMessage(content="it was a client dinner")],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "policy_justification_answered",
                "readyForSubmission": True,
                "status": "active",
            },
            "slots": {
                "category": "meals",
                "justification": "it was a client dinner",
                "extractedReceipt": {
                    "fields": {
                        "merchant": "DIG.",
                        "date": "2024-05-28",
                        "totalAmount": 16.2,
                        "currency": "USD",
                        "lineItems": [{"description": "Charred Chicken", "amount": 13.4}],
                        "tax": 1.19,
                        "paymentMethod": "VISA CREDIT",
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.92,
                        "totalAmount": 0.98,
                        "currency": 0.99,
                    },
                    "imagePath": "uploads/claim-gpt-submit-justification-001.jpg",
                },
                "currencyConversion": {
                    "supported": True,
                    "originalAmount": 16.2,
                    "fromCurrency": "USD",
                    "convertedAmount": 20.68,
                    "convertedCurrency": "SGD",
                    "rate": 1.2764,
                },
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "it was a client dinner", "hasImage": False},
            "lastResolution": {
                "outcome": "answer",
                "responseText": "it was a client dinner",
                "summary": "User provided a justification for the policy exception.",
            },
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await reasonNode(state, llm=FakeLlm())

    message = result["messages"][-1]
    assert isinstance(message, AIMessage)
    assert message.tool_calls
    assert message.tool_calls[0]["name"] == "submitClaim"
    assert message.tool_calls[0]["args"]["sessionClaimId"] == "claim-gpt-submit-justification-001"
    assert message.tool_calls[0]["args"]["intakeFindings"]["justification"] == "it was a client dinner"
    assert result["intakeGpt"]["slots"]["claimData"]["category"] == "meals"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "submitting_claim"


@pytest.mark.asyncio
async def test_applyToolResultsNodeDeclinesSubmitConfirmationWithoutSubmitting():
    """A negative submit_confirmation reply should not advance to submitClaim."""
    state = {
        "claimId": "claim-gpt-submit-002",
        "threadId": "thread-gpt-submit-002",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps({"response": "no"}),
                name="requestHumanInput",
                tool_call_id="call_submit_confirmation",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "submit_confirmation",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {},
            "pendingInterrupt": {
                "id": "call_submit_confirmation",
                "kind": "submit_confirmation",
                "question": "Submit the claim?",
                "contextMessage": "summary",
                "expectedResponseKind": "confirmation",
                "blockingStep": "submit_confirmation",
                "status": "pending",
                "retryCount": 0,
                "allowSideQuestions": True,
            },
            "lastUserTurn": {"message": "no", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await applyToolResultsNode(state)

    assert result["intakeGpt"]["pendingInterrupt"] is None
    assert result["intakeGpt"]["lastResolution"]["outcome"] == "cancel_claim"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "submission_declined"
    assert result["intakeGpt"]["workflow"]["readyForSubmission"] is False


@pytest.mark.asyncio
async def test_applyToolResultsNodeMapsSubmitClaimResult():
    """submitClaim output should populate top-level submission fields."""
    submitResult = {
        "claim": {
            "id": 123,
            "claim_number": "CLAIM-00123",
            "intake_findings": {"policyViolation": None, "justification": None},
        },
        "receipt": {"id": 456},
    }
    state = {
        "claimId": "claim-gpt-submit-003",
        "threadId": "thread-gpt-submit-003",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps(submitResult),
                name="submitClaim",
                tool_call_id="call_submit",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "submitting_claim",
                "readyForSubmission": True,
                "status": "active",
            },
            "slots": {
                "claimData": {"amountSgd": 20.64, "category": "meals"},
                "receiptData": {"merchant": "DIG."},
                "intakeFindings": {"policyViolation": None, "justification": None},
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "yes", "hasImage": False},
            "lastResolution": {
                "outcome": "answer",
                "responseText": "yes",
                "summary": "User confirmed that the claim should be submitted.",
            },
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await applyToolResultsNode(state)

    assert result["claimSubmitted"] is True
    assert result["claimNumber"] == "CLAIM-00123"
    assert result["dbClaimId"] == 123
    assert result["intakeFindings"] == {"policyViolation": None, "justification": None}
    assert result["intakeGpt"]["slots"]["submissionResult"] == submitResult
    assert result["intakeGpt"]["workflow"]["currentStep"] == "claim_submitted"


@pytest.mark.asyncio
async def test_applyToolResultsNodeBuffersAuditStepsForExtraction():
    """intake-gpt should buffer the same extraction audit steps as legacy intake."""
    extractedReceipt = {
        "fields": {
            "merchant": "DIG.",
            "date": "2024-05-28",
            "totalAmount": 16.2,
            "currency": "USD",
        },
        "confidence": {"merchant": 0.95},
        "imagePath": "uploads/claim-gpt-audit.jpg",
    }
    state = {
        "claimId": "claim-gpt-audit",
        "threadId": "thread-gpt-audit",
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
                "currentStep": "schema_loaded",
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

    with patch("agentic_claims.agents.intake_gpt.graph.bufferStep") as mockBufferStep:
        result = await applyToolResultsNode(state)

    assert result["extractedReceipt"] == extractedReceipt
    assert mockBufferStep.call_count == 2
    actions = [call.kwargs["action"] for call in mockBufferStep.call_args_list]
    assert actions == ["receipt_uploaded", "ai_extraction"]


@pytest.mark.asyncio
async def test_applyToolResultsNodeWritesClaimSubmittedAuditStep():
    """intake-gpt should log the submitted-claim audit step after DB claim creation."""
    submitResult = {
        "claim": {
            "id": 100,
            "claim_number": "CLAIM-025",
            "status": "pending",
            "intake_findings": {"justification": None},
        }
    }
    state = {
        "claimId": "claim-gpt-submit-audit",
        "threadId": "thread-gpt-submit-audit",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps(submitResult),
                name="submitClaim",
                tool_call_id="call_submit",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "submitting_claim",
                "readyForSubmission": False,
                "status": "active",
            },
            "slots": {"intakeFindings": {"justification": None}},
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "submit", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    with patch("agentic_claims.agents.intake_gpt.graph.logIntakeStep", new_callable=AsyncMock) as mockLogIntakeStep:
        result = await applyToolResultsNode(state)

    assert result["claimSubmitted"] is True
    mockLogIntakeStep.assert_awaited_once_with(
        claimId=100,
        action="claim_submitted",
        details={"claimNumber": "CLAIM-025", "status": "pending"},
    )


@pytest.mark.asyncio
async def test_applyToolResultsNodeMapsExtractedReceiptIntoDurableState():
    """Tool results should populate top-level receipt fields without forcing category."""
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

    result = await applyToolResultsNode(state)

    assert result["extractedReceipt"] == extractedReceipt
    assert result["intakeGpt"]["slots"]["extractedReceipt"] == extractedReceipt
    assert "category" not in result["intakeGpt"]["slots"]
    assert result["intakeGpt"]["workflow"]["currentStep"] == "receipt_extracted"


@pytest.mark.asyncio
async def test_applyToolResultsNodeClearsPendingInterruptOnResume():
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

    result = await applyToolResultsNode(state)

    assert result["intakeGpt"]["pendingInterrupt"] is None
    assert result["intakeGpt"]["lastResolution"]["outcome"] == "answer"
    assert result["intakeGpt"]["slots"]["fieldConfirmationResponse"] == "yes"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "field_confirmation_answered"


@pytest.mark.asyncio
async def test_applyToolResultsNodeBuildsDraftClaimBundleAfterFieldConfirmation():
    """Confirmation should materialize claimData, receiptData, and intakeFindings."""
    state = {
        "claimId": "claim-gpt-006b",
        "threadId": "thread-gpt-006b",
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
            "slots": {
                "category": "meals",
                "extractedReceipt": {
                    "fields": {
                        "merchant": "DIG.",
                        "date": "2024-05-28",
                        "totalAmount": 16.2,
                        "currency": "USD",
                        "lineItems": [{"description": "Charred Chicken", "amount": 13.4}],
                        "tax": 1.19,
                        "paymentMethod": "VISA CREDIT",
                    },
                    "confidence": {
                        "merchant": 0.95,
                        "date": 0.92,
                        "totalAmount": 0.98,
                        "currency": 0.99,
                    },
                    "imagePath": "uploads/claim-gpt-006b.jpg",
                },
                "currencyConversion": {
                    "supported": True,
                    "originalAmount": 16.2,
                    "fromCurrency": "USD",
                    "convertedAmount": 20.64,
                    "convertedCurrency": "SGD",
                    "rate": 1.2739,
                    "date": "2026-04-14",
                },
            },
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

    result = await applyToolResultsNode(state)

    claimData = result["intakeGpt"]["slots"]["claimData"]
    receiptData = result["intakeGpt"]["slots"]["receiptData"]
    intakeFindings = result["intakeFindings"]
    assert claimData["amountSgd"] == 20.64
    assert claimData["category"] == "meals"
    assert receiptData["merchant"] == "DIG."
    assert receiptData["currency"] == "USD"
    assert intakeFindings["confidenceScores"]["merchant"] == 0.95
    assert intakeFindings["extractedFields"]["merchant"] == "DIG."
    assert intakeFindings["conversion"]["originalCurrency"] == "USD"
    assert intakeFindings["policyViolation"] is None
    assert result["intakeGpt"]["workflow"]["currentStep"] == "field_confirmation_answered"


@pytest.mark.asyncio
async def test_applyToolResultsNodeAppliesManualFxRateOnResume():
    """Manual FX reply should be parsed into a durable SGD conversion."""
    state = {
        "claimId": "claim-gpt-manual-fx-002",
        "threadId": "thread-gpt-manual-fx-002",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps({"response": "1 VND = 0.000053 SGD"}),
                name="requestHumanInput",
                tool_call_id="call_manual_fx",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "manual_fx_required",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {
                        "merchant": "Pho 24",
                        "date": "2026-04-13",
                        "totalAmount": 550000,
                        "currency": "VND",
                    },
                    "confidence": {
                        "merchant": 0.91,
                        "date": 0.89,
                        "totalAmount": 0.94,
                        "currency": 0.97,
                    },
                },
                "currencyConversion": {
                    "supported": False,
                    "currency": "VND",
                    "error": "unsupported",
                    "provider": "frankfurter",
                },
                "category": "meals",
            },
            "pendingInterrupt": {
                "id": "call_manual_fx",
                "kind": "manual_fx_rate",
                "question": "Can you share the exchange rate to SGD?",
                "contextMessage": "summary",
                "expectedResponseKind": "exchange_rate",
                "blockingStep": "manual_fx_required",
                "status": "pending",
                "retryCount": 0,
                "allowSideQuestions": True,
            },
            "lastUserTurn": {"message": "1 VND = 0.000053 SGD", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await applyToolResultsNode(state)

    conversion = result["currencyConversion"]
    assert conversion["supported"] is True
    assert conversion["manualOverride"] is True
    assert conversion["fromCurrency"] == "VND"
    assert conversion["convertedAmount"] == 29.15
    assert conversion["rate"] == 0.000053
    assert result["intakeGpt"]["pendingInterrupt"] is None
    assert result["intakeGpt"]["lastResolution"]["outcome"] == "answer"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "currency_converted"


@pytest.mark.asyncio
async def test_applyToolResultsNodeKeepsManualFxInterruptPendingOnInvalidRate():
    """An unusable manual FX reply should re-block the workflow instead of advancing."""
    state = {
        "claimId": "claim-gpt-manual-fx-003",
        "threadId": "thread-gpt-manual-fx-003",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps({"response": "yes"}),
                name="requestHumanInput",
                tool_call_id="call_manual_fx",
            )
        ],
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "manual_fx_required",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {
                "extractedReceipt": {
                    "fields": {"totalAmount": 550000, "currency": "VND"},
                    "confidence": {"totalAmount": 0.94, "currency": 0.97},
                },
                "currencyConversion": {
                    "supported": False,
                    "currency": "VND",
                    "error": "unsupported",
                    "provider": "frankfurter",
                },
            },
            "pendingInterrupt": {
                "id": "call_manual_fx",
                "kind": "manual_fx_rate",
                "question": "Can you share the exchange rate to SGD?",
                "contextMessage": "summary",
                "expectedResponseKind": "exchange_rate",
                "blockingStep": "manual_fx_required",
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

    result = await applyToolResultsNode(state)

    assert result["intakeGpt"]["lastResolution"]["outcome"] == "ambiguous"
    assert result["intakeGpt"]["pendingInterrupt"] is not None
    assert result["intakeGpt"]["pendingInterrupt"]["kind"] == "manual_fx_rate"
    assert result["intakeGpt"]["pendingInterrupt"]["retryCount"] == 1
    assert result["intakeGpt"]["workflow"]["currentStep"] == "manual_fx_required"
    assert result["intakeGpt"]["workflow"]["status"] == "blocked"


@pytest.mark.asyncio
async def test_applyToolResultsNodeStoresPolicySearchResults():
    """Policy search tool output should be stored for the next reasoning step."""
    policyResults = [
        {
            "text": "Meal claims are capped at SGD 30 per meal.",
            "file": "meals.md",
            "category": "meals",
            "section": "2.1",
            "score": 0.95,
        }
    ]
    state = {
        "claimId": "claim-gpt-policy-001",
        "threadId": "thread-gpt-policy-001",
        "status": "draft",
        "messages": [
            ToolMessage(
                content=json.dumps(policyResults),
                name="searchPolicies",
                tool_call_id="call_policy_search",
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
                "claimData": {"amountSgd": 20.64, "category": "meals"},
            },
            "pendingInterrupt": None,
            "lastUserTurn": {"message": "", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }

    result = await applyToolResultsNode(state)

    assert result["intakeGpt"]["slots"]["policySearchResults"] == policyResults
    assert result["intakeGpt"]["slots"]["policySearchQuery"] == "meals expense policy for SGD 20.64"
    assert result["intakeGpt"]["workflow"]["currentStep"] == "policy_answered"


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


# ---------------------------------------------------------------------------
# Phase 14 Plan 01 — RED phase: interrupt state machine contract tests
# ---------------------------------------------------------------------------


def test_classifyInterruptReplyRejectsNegativeTokenForFieldConfirmation():
    for reply in ("no", "nope", "cancel"):
        outcome, _summary, _parsed = _classifyInterruptReply(
            reply, pendingKind="field_confirmation"
        )
        assert outcome != "answer", (
            f"Negative token {reply!r} must NOT classify as 'answer' for field_confirmation"
        )


def test_classifyInterruptReplyRejectsNegativeTokenForPolicyJustification():
    for reply in ("no", "nope", "skip", "never mind"):
        outcome, _summary, _parsed = _classifyInterruptReply(
            reply, pendingKind="policy_justification"
        )
        assert outcome in {"cancel_claim", "side_question"}, (
            f"Negative token {reply!r} must be cancel_claim or side_question, got {outcome}"
        )


def test_classifyInterruptReplyDetectsSideQuestionForPolicyJustification():
    # Ends with '?'
    outcome1, _, _ = _classifyInterruptReply(
        "what is the meal allowance cap?", pendingKind="policy_justification"
    )
    assert outcome1 == "side_question"

    # Starts with interrogative word
    for reply in (
        "what approval level is required",
        "why does this policy cap exist",
        "how do I escalate this",
        "when should I submit receipts",
        "can this be overridden",
        "is there an exception path",
    ):
        outcome, _, _ = _classifyInterruptReply(reply, pendingKind="policy_justification")
        assert outcome == "side_question", f"{reply!r} → {outcome}"


def test_classifyInterruptReplyPreservesJustificationTextVerbatim():
    text = "Client dinner on-site, approved by my manager offline."
    outcome, _summary, _parsed = _classifyInterruptReply(
        text, pendingKind="policy_justification"
    )
    assert outcome == "answer", (
        f"Free-form justification text must classify as 'answer', got {outcome}"
    )


@pytest.mark.asyncio
async def test_interruptResolutionNodePreservesPendingInterruptOnSideQuestion():
    pendingInterrupt = {
        "id": "int-1",
        "kind": "field_confirmation",
        "question": "Do these extracted details look correct?",
        "contextMessage": "Merchant: Koufu...",
        "expectedResponseKind": "text",
        "blockingStep": "field_confirmation",
        "status": "pending",
        "retryCount": 0,
        "allowSideQuestions": True,
    }
    state = {
        "messages": [HumanMessage(content="what is the meal cap in SGD?")],
        "claimId": "c1",
        "threadId": "t1",
        "status": "active",
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "field_confirmation",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {},
            "pendingInterrupt": pendingInterrupt,
            "lastUserTurn": {"message": "what is the meal cap in SGD?", "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }
    result = await interruptResolutionNode(state)
    intake = result["intakeGpt"]
    assert intake["pendingInterrupt"] is not None, (
        "pendingInterrupt must remain set on side_question"
    )
    assert intake["lastResolution"] is not None, "lastResolution must be written"
    assert intake["lastResolution"]["outcome"] == "side_question"
    assert intake["lastResolution"]["responseText"] == "what is the meal cap in SGD?"


@pytest.mark.asyncio
async def test_applyToolResultsNodeStoresVerbatimJustificationText():
    justificationText = "Client dinner with external auditors, no cheaper option available."
    toolMsg = ToolMessage(
        content=f'{{"response": "{justificationText}"}}',
        name="requestHumanInput",
        tool_call_id="tc-1",
    )
    pendingInterrupt = {
        "id": "int-2",
        "kind": "policy_justification",
        "question": "Please provide a justification.",
        "contextMessage": "Policy violation...",
        "expectedResponseKind": "text",
        "blockingStep": "policy_justification",
        "status": "pending",
        "retryCount": 0,
        "allowSideQuestions": True,
    }
    state = {
        "messages": [toolMsg],
        "claimId": "c1",
        "threadId": "t1",
        "status": "active",
        "intakeGpt": {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "policy_justification",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {"intakeFindings": {"justification": ""}},
            "pendingInterrupt": pendingInterrupt,
            "lastUserTurn": {"message": justificationText, "hasImage": False},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        },
    }
    result = await applyToolResultsNode(state)
    intake = result["intakeGpt"]
    assert intake["slots"]["justification"] == justificationText, (
        f"Expected verbatim text; got {intake['slots']['justification']!r}"
    )
    findings = intake["slots"].get("intakeFindings") or {}
    assert findings.get("justification") == justificationText, (
        f"intakeFindings.justification must be verbatim; got {findings.get('justification')!r}"
    )


def test_pendingInterruptFromToolCallsHandlesPolicyJustification():
    """_pendingInterruptFromToolCalls must accept policy_justification kind."""
    from agentic_claims.agents.intake_gpt.graph import _pendingInterruptFromToolCalls

    msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "tc-1",
            "name": "requestHumanInput",
            "args": {
                "kind": "policy_justification",
                "question": "Why did this exceed?",
                "contextMessage": "Claim exceeds cap",
                "expectedResponseKind": "text",
                "blockingStep": "policy_justification",
                "allowSideQuestions": True,
                "category": "meals",
            },
        }],
    )
    pending = _pendingInterruptFromToolCalls(msg)
    assert pending is not None, "_pendingInterruptFromToolCalls must accept policy_justification kind"
    assert pending.get("kind") == "policy_justification"


def test_pendingInterruptFromToolCallsHandlesSubmitConfirmation():
    """_pendingInterruptFromToolCalls must accept submit_confirmation kind."""
    from agentic_claims.agents.intake_gpt.graph import _pendingInterruptFromToolCalls

    msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "tc-2",
            "name": "requestHumanInput",
            "args": {
                "kind": "submit_confirmation",
                "question": "Shall I submit?",
                "contextMessage": "Claim summary",
                "expectedResponseKind": "text",
                "blockingStep": "submit_confirmation",
                "allowSideQuestions": True,
                "category": "meals",
            },
        }],
    )
    pending = _pendingInterruptFromToolCalls(msg)
    assert pending is not None, "_pendingInterruptFromToolCalls must accept submit_confirmation kind"
    assert pending.get("kind") == "submit_confirmation"


def test_buildRuntimeContextExposesPendingInterruptAndSideQuestionOutcome():
    intakeState = {
        "workflow": {
            "goal": "assist_claimant",
            "currentStep": "field_confirmation",
            "readyForSubmission": False,
            "status": "blocked",
        },
        "slots": {},
        "pendingInterrupt": {
            "id": "int-3",
            "kind": "field_confirmation",
            "question": "Do these extracted details look correct?",
            "contextMessage": "",
            "expectedResponseKind": "text",
            "blockingStep": "field_confirmation",
            "status": "pending",
            "retryCount": 0,
            "allowSideQuestions": True,
        },
        "lastUserTurn": {"message": "what is the meal cap?", "hasImage": False},
        "lastResolution": {
            "outcome": "side_question",
            "responseText": "what is the meal cap?",
            "summary": "User asked a side question",
        },
        "toolTrace": {},
        "protocolGuardCount": 0,
    }
    graphState = {"messages": [], "claimId": "c1", "threadId": "t1", "status": "active"}
    context = _buildRuntimeContext(graphState, intakeState)
    assert "field_confirmation" in context, (
        "runtime context must mention the pending interrupt kind"
    )
    assert "side_question" in context or "side question" in context.lower(), (
        "runtime context must surface the side_question resolution outcome"
    )
    assert "Do these extracted details look correct?" in context, (
        "runtime context must include the pending interrupt question verbatim for re-presentation"
    )
