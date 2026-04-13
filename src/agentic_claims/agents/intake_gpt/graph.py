"""Custom LangGraph subgraph for the intake-gpt replacement path."""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import NotRequired, TypedDict

from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.agents.intake.tools.getClaimSchema import getClaimSchema
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake_gpt.prompt import INTAKE_GPT_SYSTEM_PROMPT
from agentic_claims.agents.intake_gpt.state import IntakeGptState
from agentic_claims.agents.intake_gpt.tools.requestHumanInput import requestHumanInput
from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)

_INTAKE_GPT_TOOLS = [
    searchPolicies,
    getClaimSchema,
    extractReceiptFields,
    convertCurrency,
    requestHumanInput,
]
_END_CONVERSATION_TOKENS = {"bye", "exit", "quit", "close", "stop"}
_AFFIRMATIVE_TOKENS = {
    "yes",
    "yeah",
    "yep",
    "correct",
    "looks good",
    "all good",
    "confirmed",
    "confirm",
}


class IntakeGptGraphState(TypedDict):
    """Inner graph state for intake-gpt."""

    messages: Annotated[list[AnyMessage], add_messages]
    claimId: str
    threadId: str | None
    status: str
    intakeGpt: NotRequired[IntakeGptState]


def _defaultIntakeGptState() -> IntakeGptState:
    return {
        "workflow": {
            "goal": "assist_claimant",
            "currentStep": "plain_chat",
            "readyForSubmission": False,
            "status": "active",
        },
        "slots": {},
        "pendingInterrupt": None,
        "lastUserTurn": {"message": "", "hasImage": False},
        "lastResolution": None,
        "toolTrace": {},
        "protocolGuardCount": 0,
    }


def _latestHumanText(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _normalizeIntakeState(state: IntakeGptGraphState) -> IntakeGptState:
    current = state.get("intakeGpt") or _defaultIntakeGptState()
    normalized = _defaultIntakeGptState()
    normalized.update(current)
    normalized["workflow"] = {
        **_defaultIntakeGptState()["workflow"],
        **(current.get("workflow") or {}),
    }
    normalized["lastUserTurn"] = {
        **_defaultIntakeGptState()["lastUserTurn"],
        **(current.get("lastUserTurn") or {}),
    }
    normalized["toolTrace"] = dict(current.get("toolTrace") or {})
    normalized["slots"] = dict(current.get("slots") or {})
    return normalized


def _parseJsonLike(content: Any) -> Any:
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def _toolTraceValue(toolMessage: ToolMessage) -> dict:
    return {"name": toolMessage.name, "output": _parseJsonLike(toolMessage.content)}


def _extractConfidenceScores(payload: dict) -> dict:
    confidence = payload.get("confidence") or payload.get("confidenceScores") or {}
    return confidence if isinstance(confidence, dict) else {}


def _confidenceLabel(score: object) -> str:
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return "Unknown"
    if numeric >= 0.85:
        return "High"
    if numeric >= 0.60:
        return "Medium"
    return "Low"


def _valuePresent(value: object) -> bool:
    return value not in (None, "", [], {})


def _formatMoney(currency: object, value: object) -> str:
    if not _valuePresent(value):
        return "—"
    if isinstance(value, (int, float)):
        amount = f"{value:.2f}"
    else:
        amount = str(value)
    prefix = str(currency).strip() if _valuePresent(currency) else ""
    return f"{prefix} {amount}".strip()


def _formatLineItems(value: object) -> str:
    if not value:
        return "—"
    if isinstance(value, list):
        count = len(value)
        suffix = "item" if count == 1 else "items"
        return f"{count} {suffix}"
    return str(value)


def _buildExtractionContextMessage(intakeState: IntakeGptState) -> str:
    extracted = intakeState.get("slots", {}).get("extractedReceipt") or {}
    if not isinstance(extracted, dict):
        return ""

    fields = extracted.get("fields") or {}
    if not isinstance(fields, dict):
        return ""
    confidence = _extractConfidenceScores(extracted)
    currency = fields.get("currency") or "SGD"

    rows: list[tuple[str, str, str]] = []

    def addRow(label: str, fieldKey: str, formatter=None) -> None:
        value = fields.get(fieldKey)
        if not _valuePresent(value):
            return
        rendered = formatter(value) if formatter else str(value)
        rows.append((label, rendered, _confidenceLabel(confidence.get(fieldKey))))

    addRow("Merchant", "merchant")
    addRow("Date", "date")
    addRow("Total", "totalAmount", lambda value: _formatMoney(currency, value))
    addRow("Currency", "currency")
    addRow("Tax", "tax", lambda value: _formatMoney(currency, value))
    addRow("Payment Method", "paymentMethod")
    addRow("Line items", "lineItems", _formatLineItems)

    category = intakeState.get("slots", {}).get("category")
    if _valuePresent(category):
        rows.append(("Category", str(category), "Derived"))

    lines = ["| Field | Value | Confidence |", "|---|---|---|"]
    for label, value, score in rows:
        lines.append(f"| {label} | {value} | {score} |")

    contextMessage = "\n".join(lines)
    conversion = intakeState.get("slots", {}).get("currencyConversion")
    if isinstance(conversion, dict) and conversion.get("supported"):
        originalAmount = conversion.get("originalAmount", fields.get("totalAmount"))
        originalCurrency = conversion.get("fromCurrency", currency)
        convertedAmount = conversion.get("convertedAmount")
        rate = conversion.get("rate")
        contextMessage += (
            f"\n\nTotal: {originalCurrency} {originalAmount} → SGD {convertedAmount} "
            f"(rate: {rate})"
        )
    return contextMessage


def _deriveCategory(extracted: dict) -> str:
    fields = extracted.get("fields") or {}
    merchant = str(fields.get("merchant", "")).lower()
    keywords = (
        ("meals", ("restaurant", "cafe", "coffee", "burger", "grill", "kopi", "food")),
        ("transport", ("taxi", "grab", "bus", "mrt", "train", "flight", "air")),
        ("accommodation", ("hotel", "inn", "hostel")),
        ("office_supplies", ("stationery", "software", "notebook", "printer")),
    )
    for category, tokens in keywords:
        if any(token in merchant for token in tokens):
            return category
    return "general"


def _buildRuntimeContext(state: IntakeGptGraphState, intakeState: IntakeGptState) -> str:
    slots = intakeState.get("slots") or {}
    pending = intakeState.get("pendingInterrupt")
    resolution = intakeState.get("lastResolution")
    payload = {
        "claimId": state.get("claimId"),
        "workflow": intakeState.get("workflow"),
        "lastUserTurn": intakeState.get("lastUserTurn"),
        "pendingInterrupt": pending,
        "lastResolution": resolution,
        "hasSchema": bool(slots.get("schema")),
        "hasExtractedReceipt": bool(slots.get("extractedReceipt")),
        "hasCurrencyConversion": bool(slots.get("currencyConversion")),
        "supportedSliceNotes": {
            "receiptCorrections": "not yet implemented in intake-gpt preview",
            "manualFx": "not yet implemented in intake-gpt preview",
            "policyValidation": "not yet implemented in intake-gpt preview after confirmation",
        },
    }
    return "Runtime state:\n```json\n" + json.dumps(payload, indent=2, default=str) + "\n```"


def _hydrateRequestHumanInputCall(response: AIMessage, intakeState: IntakeGptState) -> AIMessage:
    toolCalls = list(getattr(response, "tool_calls", []) or [])
    if not toolCalls:
        return response

    updated = False
    for toolCall in toolCalls:
        if toolCall.get("name") != "requestHumanInput":
            continue
        args = dict(toolCall.get("args") or {})
        kind = args.get("kind") or "field_confirmation"
        if kind == "field_confirmation":
            args["contextMessage"] = _buildExtractionContextMessage(intakeState)
        if not args.get("question"):
            args["question"] = (
                "Does the above information look correct? Please confirm or let me know what needs changing."
            )
        args.setdefault("expectedResponseKind", "confirmation")
        args.setdefault("blockingStep", "field_confirmation")
        args.setdefault("allowSideQuestions", True)
        toolCall["args"] = args
        updated = True

    if not updated:
        return response

    return AIMessage(
        content=response.content,
        additional_kwargs=dict(getattr(response, "additional_kwargs", {}) or {}),
        response_metadata=dict(getattr(response, "response_metadata", {}) or {}),
        tool_calls=toolCalls,
        id=getattr(response, "id", None),
    )


def _pendingInterruptFromToolCalls(response: AIMessage) -> dict | None:
    for toolCall in getattr(response, "tool_calls", []) or []:
        if toolCall.get("name") != "requestHumanInput":
            continue
        args = dict(toolCall.get("args") or {})
        return {
            "id": str(toolCall.get("id") or "pending-interrupt"),
            "kind": str(args.get("kind") or "field_confirmation"),
            "question": str(args.get("question") or ""),
            "contextMessage": str(args.get("contextMessage") or ""),
            "expectedResponseKind": str(args.get("expectedResponseKind") or "text"),
            "blockingStep": str(args.get("blockingStep") or ""),
            "status": "pending",
            "retryCount": 0,
            "allowSideQuestions": bool(args.get("allowSideQuestions", True)),
        }
    return None


def _classifyInterruptReply(text: str) -> tuple[str, str]:
    lowered = text.strip().lower()
    if not lowered:
        return "ambiguous", "No reply captured for the pending interrupt."
    if lowered in _END_CONVERSATION_TOKENS:
        return "end_conversation", "User chose to end the conversation."
    if lowered in _AFFIRMATIVE_TOKENS or any(
        token in lowered for token in _AFFIRMATIVE_TOKENS if " " in token
    ):
        return "answer", "User confirmed the pending receipt details."
    return "answer", "User replied to the pending interrupt."


def turnEntryNode(state: IntakeGptGraphState) -> dict:
    """Initialize durable intake-gpt state for the turn."""
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="turnEntryNode",
        message="intake-gpt node entered",
    )
    intakeState = _normalizeIntakeState(state)
    latestText = _latestHumanText(state.get("messages", []))
    intakeState["lastUserTurn"] = {
        "message": latestText,
        "hasImage": "uploaded a receipt image" in latestText.lower(),
    }
    if intakeState["lastUserTurn"]["hasImage"]:
        intakeState["slots"] = {}
        intakeState["toolTrace"] = {}
        intakeState["pendingInterrupt"] = None
        intakeState["lastResolution"] = None
        intakeState["workflow"]["currentStep"] = "receipt_received"
        intakeState["workflow"]["status"] = "active"
        intakeState["workflow"]["readyForSubmission"] = False
    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="turnEntryNode",
        workflowStep=intakeState["workflow"]["currentStep"],
        message="intake-gpt node exited",
    )
    return {"intakeGpt": intakeState}


async def interruptResolutionNode(state: IntakeGptGraphState) -> dict:
    """Placeholder interrupt-resolution node for future slices."""
    intakeState = _normalizeIntakeState(state)
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="interruptResolutionNode",
        message="intake-gpt node entered",
    )
    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="interruptResolutionNode",
        message="intake-gpt node exited",
    )
    return {"intakeGpt": intakeState}


async def reasonNode(state: IntakeGptGraphState, *, llm) -> dict:
    """Run the model step with tool binding."""
    nodeStart = time.time()
    intakeState = _normalizeIntakeState(state)
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="reasonNode",
        workflowStep=intakeState["workflow"]["currentStep"],
        message="intake-gpt node entered",
    )
    boundLlm = llm.bind_tools(_INTAKE_GPT_TOOLS)
    runtimeContext = _buildRuntimeContext(state, intakeState)
    logEvent(
        logger,
        "intake.gpt.llm_call_started",
        logCategory="llm",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        messageCount=len(state.get("messages", [])),
        message="intake-gpt reason node invoking llm",
    )
    response = await boundLlm.ainvoke(
        [
            SystemMessage(content=INTAKE_GPT_SYSTEM_PROMPT),
            SystemMessage(content=runtimeContext),
            *state.get("messages", []),
        ]
    )
    hydratedResponse = _hydrateRequestHumanInputCall(response, intakeState)
    pendingInterrupt = _pendingInterruptFromToolCalls(hydratedResponse)
    if pendingInterrupt is not None:
        intakeState["pendingInterrupt"] = pendingInterrupt
        intakeState["workflow"]["currentStep"] = pendingInterrupt["blockingStep"] or "awaiting_input"
        intakeState["workflow"]["status"] = "blocked"
    else:
        intakeState["workflow"]["status"] = "active"
    logEvent(
        logger,
        "intake.gpt.llm_call_completed",
        logCategory="llm",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        elapsedMs=round((time.time() - nodeStart) * 1000),
        toolCallCount=len(getattr(hydratedResponse, "tool_calls", []) or []),
        message="intake-gpt reason node llm completed",
    )
    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="reasonNode",
        workflowStep=intakeState["workflow"]["currentStep"],
        message="intake-gpt node exited",
    )
    return {
        "messages": [hydratedResponse],
        "intakeGpt": intakeState,
    }


def applyToolResultsNode(state: IntakeGptGraphState) -> dict:
    """Update durable state after tools run."""
    intakeState = _normalizeIntakeState(state)
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="applyToolResultsNode",
        message="intake-gpt node entered",
    )
    slots = dict(intakeState.get("slots") or {})
    toolTrace = dict(intakeState.get("toolTrace") or {})
    updates: dict[str, Any] = {"intakeGpt": intakeState}
    toolMessages = [
        message
        for message in state.get("messages", [])
        if isinstance(message, ToolMessage) and message.name
    ]
    if toolMessages:
        latestTool = toolMessages[-1]
        parsed = _parseJsonLike(latestTool.content)
        toolTrace[str(latestTool.name)] = {"name": latestTool.name, "output": parsed}
        intakeState["toolTrace"] = toolTrace

        if latestTool.name == "getClaimSchema" and isinstance(parsed, dict):
            slots["schema"] = parsed
            intakeState["workflow"]["currentStep"] = "schema_loaded"
        elif latestTool.name == "extractReceiptFields" and isinstance(parsed, dict):
            slots["extractedReceipt"] = parsed
            slots["category"] = _deriveCategory(parsed)
            updates["extractedReceipt"] = parsed
            intakeState["workflow"]["currentStep"] = "receipt_extracted"
        elif latestTool.name == "convertCurrency" and isinstance(parsed, dict):
            slots["currencyConversion"] = parsed
            updates["currencyConversion"] = parsed
            intakeState["workflow"]["currentStep"] = (
                "currency_converted" if parsed.get("supported", True) else "manual_fx_required"
            )
        elif latestTool.name == "requestHumanInput":
            responseText = ""
            if isinstance(parsed, dict):
                responseText = str(parsed.get("response") or "")
            outcome, summary = _classifyInterruptReply(responseText)
            pending = intakeState.get("pendingInterrupt") or {}
            intakeState["lastResolution"] = {
                "outcome": outcome,
                "responseText": responseText,
                "summary": summary,
            }
            slots["lastHumanInput"] = responseText
            if pending.get("kind") == "field_confirmation":
                slots["fieldConfirmationResponse"] = responseText
            intakeState["pendingInterrupt"] = None
            intakeState["workflow"]["status"] = "completed" if outcome == "end_conversation" else "active"
            intakeState["workflow"]["currentStep"] = (
                "conversation_closed" if outcome == "end_conversation" else "field_confirmation_answered"
            )
        elif latestTool.name == "searchPolicies":
            intakeState["workflow"]["currentStep"] = "policy_answered"

        intakeState["slots"] = slots
        logEvent(
            logger,
            "intake.gpt.tool_result_applied",
            logCategory="agent",
            agent="intake-gpt",
            claimId=state.get("claimId"),
            threadId=state.get("threadId"),
            toolName=str(latestTool.name),
            message="intake-gpt applied tool result to durable state",
        )

    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="applyToolResultsNode",
        workflowStep=intakeState["workflow"]["currentStep"],
        message="intake-gpt node exited",
    )
    updates["intakeGpt"] = intakeState
    return updates


async def sideQuestionResponderNode(state: IntakeGptGraphState) -> dict:
    """Placeholder node kept for the planned topology."""
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="sideQuestionResponderNode",
        message="intake-gpt node entered",
    )
    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="sideQuestionResponderNode",
        message="intake-gpt node exited",
    )
    return {"intakeGpt": _normalizeIntakeState(state)}


def finalizeTurnNode(state: IntakeGptGraphState) -> dict:
    """Finalize the turn without mutating legacy routing flags."""
    intakeState = _normalizeIntakeState(state)
    logEvent(
        logger,
        "intake.graph.node_entered",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="finalizeTurnNode",
        message="intake-gpt node entered",
    )
    logEvent(
        logger,
        "intake.graph.node_exited",
        logCategory="agent",
        agent="intake-gpt",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        nodeName="finalizeTurnNode",
        workflowStep=intakeState["workflow"]["currentStep"],
        message="intake-gpt node exited",
    )
    return {"intakeGpt": intakeState}


def _routeAfterTurnEntry(state: IntakeGptGraphState) -> str:
    pending = (_normalizeIntakeState(state).get("pendingInterrupt")) is not None
    return "interruptResolutionNode" if pending else "reasonNode"


def _routeAfterReason(state: IntakeGptGraphState) -> str:
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "toolNode"
    return "finalizeTurnNode"


def buildIntakeGptSubgraph(llm):
    """Build the custom intake-gpt subgraph."""
    builder = StateGraph(IntakeGptGraphState)

    async def _reasonNodeWithLlm(state: IntakeGptGraphState) -> dict:
        return await reasonNode(state, llm=llm)

    builder.add_node("turnEntryNode", turnEntryNode)
    builder.add_node("interruptResolutionNode", interruptResolutionNode)
    builder.add_node("reasonNode", _reasonNodeWithLlm)
    builder.add_node("toolNode", ToolNode(_INTAKE_GPT_TOOLS))
    builder.add_node("applyToolResultsNode", applyToolResultsNode)
    builder.add_node("sideQuestionResponderNode", sideQuestionResponderNode)
    builder.add_node("finalizeTurnNode", finalizeTurnNode)

    builder.add_edge(START, "turnEntryNode")
    builder.add_conditional_edges(
        "turnEntryNode",
        _routeAfterTurnEntry,
        {
            "interruptResolutionNode": "interruptResolutionNode",
            "reasonNode": "reasonNode",
        },
    )
    builder.add_edge("interruptResolutionNode", "reasonNode")
    builder.add_conditional_edges(
        "reasonNode",
        _routeAfterReason,
        {
            "toolNode": "toolNode",
            "finalizeTurnNode": "finalizeTurnNode",
        },
    )
    builder.add_edge("toolNode", "applyToolResultsNode")
    builder.add_edge("applyToolResultsNode", "reasonNode")
    builder.add_edge("sideQuestionResponderNode", "finalizeTurnNode")
    builder.add_edge("finalizeTurnNode", END)

    return builder.compile()
