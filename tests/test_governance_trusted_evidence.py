"""Regression tests for trusted receipt evidence at the governance boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from agentic_governance.integrations.langgraph_mcp import install
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from agentic_claims.agents.intake_gpt.graph import (
    IntakeGptGraphState,
    _submitClaimWithTrustedEvidence,
)
from agentic_claims.core import graph as graphModule


@pytest.fixture(autouse=True)
def _governancePolicyEnvironment(monkeypatch):
    monkeypatch.setenv("RAG_MCP_URL", "http://rag")
    monkeypatch.setenv("DB_MCP_URL", "http://db")
    monkeypatch.setenv("CURRENCY_MCP_URL", "http://currency")
    monkeypatch.delenv("AGENTIC_GOV_FORCE_IDENTITY", raising=False)
    monkeypatch.delenv("AGENTIC_GOV_REVOKE_GRANTS", raising=False)


def _receipt() -> dict:
    return {
        "fields": {
            "merchant": "Kopitiam",
            "date": "2026-07-22",
            "totalAmount": 19.36,
            "currency": "SGD",
        },
        "confidence": {
            "merchant": 0.95,
            "date": 0.92,
            "totalAmount": 0.98,
            "currency": 0.99,
        },
    }


async def _governedInsert(state: dict, *, arguments: dict | None = None):
    realTool = AsyncMock(return_value={"ok": True})
    governed = install(
        real_mcp_call_tool=realTool,
        employee_id_provider=lambda: "EMP-42",
        extracted_receipt_provider=lambda: graphModule.extractedReceiptVar.get(None),
        session_claim_id_provider=lambda: "session-a9",
        node_identity_provider=lambda: graphModule.nodeIdentityVar.get(None) or "application",
        db_claim_id_provider=lambda: graphModule.dbClaimIdVar.get(None),
    )
    callArguments = arguments or {
        "employeeId": "EMP-42",
        "status": "pending",
        "totalAmount": 19.36,
    }

    async def submitAtBoundary(_state):
        return await governed("http://db", "insertClaim", callArguments)

    result = await graphModule._withNodeIdentity("intake", submitAtBoundary)(state)
    return result, realTool


async def _governedInterruptedSubmit(
    receipt: dict | None,
    *,
    declaredFindings: dict | None = None,
):
    captured = {}
    realTool = AsyncMock(return_value={"claim": {"id": 123, "claim_number": "CLAIM-123"}})
    governed = install(
        real_mcp_call_tool=realTool,
        employee_id_provider=lambda: "EMP-42",
        extracted_receipt_provider=lambda: graphModule.extractedReceiptVar.get(None),
        session_claim_id_provider=lambda: "session-a9-resume",
        node_identity_provider=lambda: graphModule.nodeIdentityVar.get(None) or "application",
        db_claim_id_provider=lambda: graphModule.dbClaimIdVar.get(None),
    )

    def establishExtraction(state):
        return {
            "intakeGpt": {
                "workflow": {
                    "goal": "assist_claimant",
                    "currentStep": "submit_confirmation",
                    "readyForSubmission": False,
                    "status": "blocked",
                },
                "slots": {"extractedReceipt": receipt} if receipt is not None else {},
                "pendingInterrupt": {
                    "kind": "submit_confirmation",
                    "status": "pending",
                },
                "lastUserTurn": {"message": "upload", "hasImage": True},
                "lastResolution": None,
                "toolTrace": {},
                "protocolGuardCount": 0,
            }
        }

    def awaitConfirmation(state):
        interrupt({"kind": "submit_confirmation", "question": "Submit?"})
        return {}

    def buildSubmitCall(state):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submitClaim",
                            "id": "governed-submit-after-resume",
                            "type": "tool_call",
                            "args": {
                                "claimData": {
                                    "claimantId": "EMP-42",
                                    "amountSgd": 19.36,
                                    "status": "pending",
                                },
                                "receiptData": _receipt()["fields"],
                                "intakeFindings": declaredFindings or {},
                            },
                        }
                    ],
                )
            ]
        }

    async def governedBoundary(serverUrl, toolName, arguments):
        result = await governed(serverUrl, toolName, arguments)
        captured["result"] = result
        return result

    innerBuilder = StateGraph(IntakeGptGraphState)
    innerBuilder.add_node("establishExtraction", establishExtraction)
    innerBuilder.add_node("awaitConfirmation", awaitConfirmation)
    innerBuilder.add_node("buildSubmitCall", buildSubmitCall)
    innerBuilder.add_node("submitTool", ToolNode([_submitClaimWithTrustedEvidence]))
    innerBuilder.add_edge(START, "establishExtraction")
    innerBuilder.add_edge("establishExtraction", "awaitConfirmation")
    innerBuilder.add_edge("awaitConfirmation", "buildSubmitCall")
    innerBuilder.add_edge("buildSubmitCall", "submitTool")
    innerBuilder.add_edge("submitTool", END)
    innerGraph = innerBuilder.compile()

    config = {"configurable": {"thread_id": "governed-a9-interrupt-resume"}}
    with (
        patch.object(graphModule, "_installGovernedMcpBoundary"),
        patch.object(
            graphModule,
            "getSettings",
            return_value=SimpleNamespace(intake_agent_mode="gpt"),
        ),
        patch(
            "agentic_claims.agents.intake_gpt.node._getIntakeGptSubgraph",
            return_value=innerGraph,
        ),
        patch(
            "agentic_claims.agents.intake.tools.submitClaim.mcpCallTool",
            side_effect=governedBoundary,
        ),
    ):
        outerGraph = graphModule.buildGraph().compile(checkpointer=InMemorySaver())
        await outerGraph.ainvoke(
            {
                "claimId": "claim-governed-a9-resume",
                "status": "draft",
                "messages": [HumanMessage(content="upload")],
            },
            config=config,
        )
        await outerGraph.ainvoke(Command(resume="yes"), config=config)

    return captured["result"], realTool


@pytest.mark.asyncio
async def test_intakeGptDurableReceiptReachesGovernanceAsCanonicalTrustedEvidence():
    receipt = _receipt()
    captured = {}

    def captureInstall(**kwargs):
        captured["provider"] = kwargs["extracted_receipt_provider"]
        return kwargs["real_mcp_call_tool"]

    class SubmitBoundarySubgraph:
        async def ainvoke(self, innerState, config=None):
            captured["trustedEvidence"] = captured["provider"]()
            return innerState

    intakeState = {
        "workflow": {
            "goal": "assist_claimant",
            "currentStep": "submit_confirmation_answered",
            "readyForSubmission": True,
            "status": "active",
        },
        "slots": {"extractedReceipt": receipt},
        "pendingInterrupt": None,
        "lastUserTurn": {"message": "submit", "hasImage": False},
        "lastResolution": {
            "outcome": "answer",
            "responseText": "submit",
            "summary": "User confirmed submission.",
        },
        "toolTrace": {},
        "protocolGuardCount": 0,
    }

    with (
        patch.object(graphModule, "install", side_effect=captureInstall),
        patch.object(graphModule, "_MCP_CALL_TOOL_IMPORTERS", ()),
        patch.object(
            graphModule,
            "getSettings",
            return_value=SimpleNamespace(intake_agent_mode="gpt"),
        ),
        patch(
            "agentic_claims.agents.intake_gpt.node._getIntakeGptSubgraph",
            return_value=SubmitBoundarySubgraph(),
        ),
    ):
        await graphModule.buildGraph().compile().ainvoke(
            {
                "claimId": "claim-a9-regression",
                "status": "draft",
                "messages": [HumanMessage(content="submit")],
                "intakeGpt": intakeState,
            }
        )

    assert captured["trustedEvidence"] == receipt


@pytest.mark.asyncio
async def test_interruptedIntakeGptResumeBindsInnerDurableReceiptAtSubmitBoundary():
    receipt = _receipt()
    captured = {}

    def captureInstall(**kwargs):
        captured["provider"] = kwargs["extracted_receipt_provider"]
        return kwargs["real_mcp_call_tool"]

    def establishExtraction(state):
        intakeState = {
            "workflow": {
                "goal": "assist_claimant",
                "currentStep": "submit_confirmation",
                "readyForSubmission": False,
                "status": "blocked",
            },
            "slots": {"extractedReceipt": receipt},
            "pendingInterrupt": {
                "kind": "submit_confirmation",
                "status": "pending",
            },
            "lastUserTurn": {"message": "upload", "hasImage": True},
            "lastResolution": None,
            "toolTrace": {},
            "protocolGuardCount": 0,
        }
        return {"intakeGpt": intakeState}

    def awaitConfirmation(state):
        interrupt({"kind": "submit_confirmation", "question": "Submit?"})
        return {}

    def buildSubmitCall(state):
        captured["innerReceipt"] = state["intakeGpt"]["slots"]["extractedReceipt"]
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "submitClaim",
                            "id": "submit-after-resume",
                            "type": "tool_call",
                            "args": {
                                "claimData": {
                                    "claimantId": "EMP-42",
                                    "amountSgd": 19.36,
                                    "status": "pending",
                                },
                                "receiptData": receipt["fields"],
                                "intakeFindings": {},
                            },
                        }
                    ],
                )
            ]
        }

    async def captureGovernedInsert(serverUrl, toolName, arguments):
        captured["trustedEvidence"] = captured["provider"]()
        return {"error": "test-boundary"}

    innerBuilder = StateGraph(IntakeGptGraphState)
    innerBuilder.add_node("establishExtraction", establishExtraction)
    innerBuilder.add_node("awaitConfirmation", awaitConfirmation)
    innerBuilder.add_node("buildSubmitCall", buildSubmitCall)
    innerBuilder.add_node("submitTool", ToolNode([_submitClaimWithTrustedEvidence]))
    innerBuilder.add_edge(START, "establishExtraction")
    innerBuilder.add_edge("establishExtraction", "awaitConfirmation")
    innerBuilder.add_edge("awaitConfirmation", "buildSubmitCall")
    innerBuilder.add_edge("buildSubmitCall", "submitTool")
    innerBuilder.add_edge("submitTool", END)
    innerGraph = innerBuilder.compile()

    config = {"configurable": {"thread_id": "a9-interrupt-resume"}}
    with (
        patch.object(graphModule, "install", side_effect=captureInstall),
        patch.object(graphModule, "_MCP_CALL_TOOL_IMPORTERS", ()),
        patch.object(
            graphModule,
            "getSettings",
            return_value=SimpleNamespace(intake_agent_mode="gpt"),
        ),
        patch(
            "agentic_claims.agents.intake_gpt.node._getIntakeGptSubgraph",
            return_value=innerGraph,
        ),
        patch(
            "agentic_claims.agents.intake.tools.submitClaim.mcpCallTool",
            side_effect=captureGovernedInsert,
        ),
    ):
        outerGraph = graphModule.buildGraph().compile(checkpointer=InMemorySaver())
        await outerGraph.ainvoke(
            {
                "claimId": "claim-a9-resume",
                "status": "draft",
                "messages": [HumanMessage(content="upload")],
            },
            config=config,
        )
        outerAtInterrupt = (await outerGraph.aget_state(config)).values
        captured["outerReceiptAtResume"] = outerAtInterrupt.get("extractedReceipt")
        captured["outerIntakeGptAtResume"] = outerAtInterrupt.get("intakeGpt")

        await outerGraph.ainvoke(Command(resume="yes"), config=config)

    assert captured["outerReceiptAtResume"] is None
    assert captured["outerIntakeGptAtResume"] is None
    assert captured["innerReceipt"] == receipt
    assert captured["trustedEvidence"] == receipt


@pytest.mark.asyncio
async def test_resumedSubmitWithCompleteEvidenceAllowsAndDispatchesRealTool():
    result, realTool = await _governedInterruptedSubmit(_receipt())

    assert result == {"claim": {"id": 123, "claim_number": "CLAIM-123"}}
    realTool.assert_awaited_once()


@pytest.mark.asyncio
async def test_resumedSubmitWithLowConfidenceEscalatesWithoutDispatch():
    receipt = _receipt()
    receipt["confidence"]["currency"] = 0.69

    result, realTool = await _governedInterruptedSubmit(receipt)

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_resumedSubmitWithMissingEvidenceRejectsForgedDeclaredPayload():
    receipt = _receipt()
    del receipt["fields"]["merchant"]
    forgedFindings = {
        "extractedFields": _receipt()["fields"],
        "confidenceScores": _receipt()["confidence"],
    }

    result, realTool = await _governedInterruptedSubmit(
        receipt,
        declaredFindings=forgedFindings,
    )

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_resumedReceiptlessSubmitDoesNotLeakPriorContext():
    priorReceiptToken = graphModule.extractedReceiptVar.set(_receipt())
    try:
        result, realTool = await _governedInterruptedSubmit(
            None,
            declaredFindings={
                "extractedFields": _receipt()["fields"],
                "confidenceScores": _receipt()["confidence"],
            },
        )
    finally:
        graphModule.extractedReceiptVar.reset(priorReceiptToken)

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_completeDurableEvidenceAllowsA9AndDispatchesRealTool():
    receipt = _receipt()
    state = {"intakeGpt": {"slots": {"extractedReceipt": receipt}}}

    result, realTool = await _governedInsert(state)

    assert result == {"ok": True}
    realTool.assert_awaited_once()


@pytest.mark.asyncio
async def test_requiredConfidenceBelowThresholdEscalatesWithoutDispatch():
    receipt = _receipt()
    receipt["confidence"]["currency"] = 0.69

    result, realTool = await _governedInsert({"extractedReceipt": receipt})

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_missingRequiredFieldEscalatesDespiteForgedDeclaredEvidence():
    receipt = _receipt()
    del receipt["fields"]["merchant"]
    forgedArguments = {
        "employeeId": "EMP-42",
        "status": "pending",
        "totalAmount": 19.36,
        "intakeFindings": {
            "extractedFields": _receipt()["fields"],
            "confidenceScores": _receipt()["confidence"],
        },
    }

    result, realTool = await _governedInsert(
        {"extractedReceipt": receipt}, arguments=forgedArguments
    )

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_priorRequestReceiptDoesNotLeakIntoReceiptlessNode():
    priorReceiptToken = graphModule.extractedReceiptVar.set(_receipt())
    try:
        result, realTool = await _governedInsert({})
    finally:
        graphModule.extractedReceiptVar.reset(priorReceiptToken)

    assert result["decision"] == "Escalate"
    assert result["reason"] == "evidence-insufficient"
    realTool.assert_not_awaited()


@pytest.mark.asyncio
async def test_trustedLegacyReceiptShapeIsCanonicalizedAtAdapterBoundary():
    receipt = _receipt()
    trustedLegacyShape = {
        "extractedFields": receipt["fields"],
        "confidenceScores": receipt["confidence"],
        "imagePath": "uploads/claim-a9.jpg",
    }

    result, realTool = await _governedInsert({"extractedReceipt": trustedLegacyShape})

    assert result == {"ok": True}
    realTool.assert_awaited_once()
