"""Custom LangGraph subgraph for the intake-gpt replacement path."""

from __future__ import annotations

import json
import logging
import re
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
from agentic_claims.agents.intake.tools.submitClaim import submitClaim
from agentic_claims.agents.intake.auditLogger import bufferStep, logIntakeStep
from agentic_claims.agents.intake.extractionContext import extractedReceiptVar
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
    submitClaim,
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
_NEGATIVE_TOKENS = {"no", "nope", "cancel", "not yet", "later", "wait"}
_CURRENCY_SYMBOL_MAP = {
    "₫": "VND",
    "đ": "VND",
    "dong": "VND",
    "dong.": "VND",
    "vietnamese dong": "VND",
    "sgd": "SGD",
    "s$": "SGD",
    "usd": "USD",
    "$": "USD",
}
_VALID_CATEGORIES = {"meals", "transport", "accommodation", "office_supplies", "general"}


class IntakeGptGraphState(TypedDict):
    """Inner graph state for intake-gpt."""

    messages: Annotated[list[AnyMessage], add_messages]
    claimId: str
    threadId: str | None
    status: str
    intakeGpt: NotRequired[IntakeGptState]
    extractedReceipt: NotRequired[dict | None]
    violations: NotRequired[list[dict] | None]
    currencyConversion: NotRequired[dict | None]
    claimSubmitted: NotRequired[bool | None]
    claimNumber: NotRequired[str | None]
    intakeFindings: NotRequired[dict | None]
    dbClaimId: NotRequired[int | None]


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


def _formatRate(value: object) -> str:
    if not _valuePresent(value):
        return "—"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{numeric:.8f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _normalizeCurrencyCode(value: object) -> str:
    if not _valuePresent(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.lower() in _CURRENCY_SYMBOL_MAP:
        return _CURRENCY_SYMBOL_MAP[text.lower()]
    upper = text.upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return text


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
        if conversion.get("manualOverride"):
            contextMessage += (
                f"\n\nTotal: {originalCurrency} {originalAmount} → SGD {convertedAmount} "
                f"(manual rate: {_formatRate(rate)})"
            )
        else:
            contextMessage += (
                f"\n\nTotal: {originalCurrency} {originalAmount} → SGD {convertedAmount} "
                f"(rate: {_formatRate(rate)})"
            )
    return contextMessage


def _manualFxCurrencyLabel(intakeState: IntakeGptState) -> str:
    slots = intakeState.get("slots") or {}
    conversion = slots.get("currencyConversion") or {}
    if isinstance(conversion, dict) and conversion.get("currency"):
        return str(conversion.get("currency"))
    extracted = slots.get("extractedReceipt") or {}
    if isinstance(extracted, dict):
        fields = extracted.get("fields") or {}
        if isinstance(fields, dict):
            return str(fields.get("currency") or "")
    return "the receipt currency"


def _normalizeCategory(value: object) -> str | None:
    if not _valuePresent(value):
        return None
    normalized = str(value).strip().lower().replace(" ", "_")
    if normalized in _VALID_CATEGORIES:
        return normalized
    return None


def _persistRequestHumanInputMetadata(intakeState: IntakeGptState, response: AIMessage) -> None:
    slots = intakeState.setdefault("slots", {})
    for toolCall in getattr(response, "tool_calls", []) or []:
        if toolCall.get("name") != "requestHumanInput":
            continue
        args = dict(toolCall.get("args") or {})
        category = _normalizeCategory(args.get("category"))
        if category:
            slots["category"] = category


def _buildDraftClaimBundle(slots: dict) -> tuple[dict, dict, dict] | None:
    extracted = slots.get("extractedReceipt") or {}
    if not isinstance(extracted, dict):
        return None
    fields = extracted.get("fields") or {}
    if not isinstance(fields, dict):
        return None

    totalAmount = fields.get("totalAmount")
    if not _valuePresent(totalAmount):
        return None
    try:
        totalAmountFloat = float(totalAmount)
    except (TypeError, ValueError):
        return None

    currency = _normalizeCurrencyCode(fields.get("currency") or "SGD") or "SGD"
    conversion = slots.get("currencyConversion") or {}
    if isinstance(conversion, dict) and conversion.get("supported"):
        amountSgd = conversion.get("convertedAmount")
        originalAmount = conversion.get("originalAmount", totalAmountFloat)
        originalCurrency = _normalizeCurrencyCode(conversion.get("fromCurrency") or currency)
        conversionFinding = {
            "originalAmount": originalAmount,
            "originalCurrency": originalCurrency,
            "convertedAmount": amountSgd,
            "rate": conversion.get("rate"),
            "date": conversion.get("date"),
        }
        if conversion.get("manualOverride"):
            conversionFinding["manualOverride"] = True
    else:
        amountSgd = totalAmountFloat if currency == "SGD" else None
        originalAmount = totalAmountFloat
        originalCurrency = currency
        conversionFinding = None

    category = _normalizeCategory(slots.get("category"))
    claimData = {
        "amountSgd": amountSgd,
        "currency": "SGD" if amountSgd is not None else currency,
        "category": category,
        "originalAmount": originalAmount,
        "originalCurrency": originalCurrency,
    }
    if isinstance(conversion, dict) and conversion.get("supported"):
        claimData["convertedAmount"] = amountSgd
        claimData["exchangeRate"] = conversion.get("rate")
        if conversion.get("date"):
            claimData["conversionDate"] = conversion.get("date")

    receiptData = {
        "merchant": fields.get("merchant"),
        "date": fields.get("date"),
        "totalAmount": totalAmountFloat,
        "currency": currency,
        "lineItems": fields.get("lineItems") or [],
        "taxAmount": fields.get("tax"),
        "paymentMethod": fields.get("paymentMethod"),
        "imagePath": extracted.get("imagePath"),
    }
    intakeFindings = {
        "confidenceScores": _extractConfidenceScores(extracted),
        "extractedFields": dict(fields),
        "employeeId": None,
        "policyViolation": None,
        "justification": slots.get("justification"),
        "remarks": None,
        "conversion": conversionFinding,
    }
    return claimData, receiptData, intakeFindings


def _buildPolicySearchQuery(slots: dict) -> str | None:
    claimData = slots.get("claimData") or {}
    if not isinstance(claimData, dict):
        return None
    amountSgd = claimData.get("amountSgd")
    category = claimData.get("category")
    if not _valuePresent(amountSgd):
        return None
    if not _valuePresent(category):
        return None
    return f"{category} expense policy for SGD {amountSgd}"


def _parseManualFxRate(text: str, expectedCurrency: str) -> dict | None:
    lowered = text.strip()
    if not lowered:
        return None

    pattern = re.compile(
        r"(?P<lhs_amount>\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(?P<lhs_currency>[A-Za-z₫đ$]{1,12}(?:\s+[A-Za-z]{1,12}){0,2})?"
        r"\s*=\s*"
        r"(?P<rhs_amount>\d+(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(?P<rhs_currency>[A-Za-z₫đ$]{1,12}(?:\s+[A-Za-z]{1,12}){0,2})?",
        re.IGNORECASE,
    )
    match = pattern.search(lowered)
    if not match:
        return None

    lhsAmount = float(match.group("lhs_amount").replace(",", ""))
    rhsAmount = float(match.group("rhs_amount").replace(",", ""))
    lhsCurrency = _normalizeCurrencyCode(match.group("lhs_currency") or expectedCurrency)
    rhsCurrency = _normalizeCurrencyCode(match.group("rhs_currency") or "SGD")
    expected = _normalizeCurrencyCode(expectedCurrency)

    if lhsAmount <= 0 or rhsAmount <= 0:
        return None
    if rhsCurrency != "SGD":
        return None
    if expected and lhsCurrency and lhsCurrency != expected:
        return None

    rate = rhsAmount / lhsAmount
    return {
        "lhsAmount": lhsAmount,
        "lhsCurrency": lhsCurrency or expected,
        "rhsAmount": rhsAmount,
        "rhsCurrency": rhsCurrency,
        "rate": rate,
    }


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
        "hasClaimData": bool(slots.get("claimData")),
        "hasReceiptData": bool(slots.get("receiptData")),
        "hasIntakeFindings": bool(slots.get("intakeFindings")),
        "hasPolicySearchResults": bool(slots.get("policySearchResults")),
        "category": slots.get("category"),
        "claimData": slots.get("claimData"),
        "receiptData": slots.get("receiptData"),
        "intakeFindings": slots.get("intakeFindings"),
        "supportedSliceNotes": {
            "receiptCorrections": "not yet implemented in intake-gpt preview",
            "manualFx": "supported: ask for a manual SGD rate via requestHumanInput when automatic conversion is unsupported",
            "policyValidation": "supported through policy search and justification/submit confirmation checkpoints",
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
        category = _normalizeCategory(args.get("category"))
        if category:
            intakeState.setdefault("slots", {})
            intakeState["slots"]["category"] = category
            args["category"] = category
        if kind == "field_confirmation":
            args["contextMessage"] = _buildExtractionContextMessage(intakeState)
            args.setdefault(
                "question",
                "Does the above information look correct? Please confirm or let me know what needs changing.",
            )
            args.setdefault("expectedResponseKind", "confirmation")
            args.setdefault("blockingStep", "field_confirmation")
            if intakeState.get("slots", {}).get("category"):
                args.setdefault("category", intakeState["slots"]["category"])
        elif kind == "manual_fx_rate":
            currencyLabel = _manualFxCurrencyLabel(intakeState)
            args["contextMessage"] = _buildExtractionContextMessage(intakeState)
            args["question"] = (
                "I couldn't look up the rate for "
                f"{currencyLabel} automatically. Can you share the exchange rate to SGD? "
                f"For example, '1 {currencyLabel} = X SGD'."
            )
            args.setdefault("expectedResponseKind", "exchange_rate")
            args.setdefault("blockingStep", "manual_fx_required")
        elif kind == "policy_justification":
            args.setdefault("expectedResponseKind", "justification")
            args.setdefault("blockingStep", "policy_justification")
        elif kind == "submit_confirmation":
            args.setdefault("expectedResponseKind", "confirmation")
            args.setdefault("blockingStep", "submit_confirmation")
        if not args.get("question"):
            args["question"] = (
                "Does the above information look correct? Please confirm or let me know what needs changing."
            )
        args.setdefault("expectedResponseKind", "text")
        args.setdefault("blockingStep", kind)
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


def _buildFieldConfirmationAiMessage(intakeState: IntakeGptState) -> AIMessage:
    question = "Does the above information look correct? Please confirm or let me know what needs changing."
    category = _normalizeCategory((intakeState.get("slots") or {}).get("category"))
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "requestHumanInput",
                "args": {
                    "kind": "field_confirmation",
                    "question": question,
                    "contextMessage": _buildExtractionContextMessage(intakeState),
                    "expectedResponseKind": "confirmation",
                    "blockingStep": "field_confirmation",
                    "allowSideQuestions": True,
                    "category": category or "",
                },
                "id": "call_field_confirmation_after_manual_fx",
            }
        ],
    )


def _buildSubmitClaimAiMessage(state: IntakeGptGraphState, intakeState: IntakeGptState) -> AIMessage | None:
    slots = intakeState.get("slots") or {}
    claimData = slots.get("claimData")
    receiptData = slots.get("receiptData")
    intakeFindings = slots.get("intakeFindings")
    if not isinstance(claimData, dict) or not isinstance(receiptData, dict):
        draftBundle = _buildDraftClaimBundle(slots)
        if draftBundle is not None:
            claimData, receiptData, intakeFindings = draftBundle
            slots["claimData"] = claimData
            slots["receiptData"] = receiptData
            slots["intakeFindings"] = intakeFindings
            intakeState["slots"] = slots
    if not isinstance(claimData, dict) or not isinstance(receiptData, dict):
        return None
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "submitClaim",
                "args": {
                    "claimData": claimData,
                    "receiptData": receiptData,
                    "intakeFindings": intakeFindings or {},
                    "threadId": state.get("threadId"),
                    "sessionClaimId": state.get("claimId"),
                },
                "id": "call_submit_claim_runtime",
            }
        ],
    )


def _buildSubmissionAcknowledgement(intakeState: IntakeGptState) -> AIMessage | None:
    submissionResult = (intakeState.get("slots") or {}).get("submissionResult")
    if not isinstance(submissionResult, dict):
        return None
    claim = submissionResult.get("claim") or {}
    if not isinstance(claim, dict):
        return None
    claimNumber = claim.get("claim_number") or claim.get("claimNumber")
    if claimNumber:
        return AIMessage(
            content=(
                f"Your claim has been submitted successfully. Claim number: {claimNumber}. "
                "Please click on New Claim if you would like to submit another receipt. Thank you."
            )
        )
    return AIMessage(
        content=(
            "Your claim has been submitted successfully. "
            "Please click on New Claim if you would like to submit another receipt. Thank you."
        )
    )


def _classifyInterruptReply(text: str, *, pendingKind: str, expectedCurrency: str = "") -> tuple[str, str, dict | None]:
    lowered = text.strip().lower()
    if not lowered:
        return "ambiguous", "No reply captured for the pending interrupt.", None
    if lowered in _END_CONVERSATION_TOKENS:
        return "end_conversation", "User chose to end the conversation.", None
    if pendingKind == "manual_fx_rate":
        parsedRate = _parseManualFxRate(text, expectedCurrency)
        if parsedRate is None:
            return (
                "ambiguous",
                "The reply did not contain a usable exchange rate to SGD.",
                None,
            )
        return "answer", "User provided a manual exchange rate to SGD.", parsedRate
    if pendingKind == "submit_confirmation":
        if lowered in _AFFIRMATIVE_TOKENS or any(
            token in lowered for token in _AFFIRMATIVE_TOKENS if " " in token
        ):
            return "answer", "User confirmed that the claim should be submitted.", None
        if lowered in _NEGATIVE_TOKENS or any(
            token in lowered for token in _NEGATIVE_TOKENS if " " in token
        ):
            return "cancel_claim", "User declined claim submission.", None
        return "ambiguous", "The user did not clearly confirm whether to submit the claim.", None
    if lowered in _AFFIRMATIVE_TOKENS or any(
        token in lowered for token in _AFFIRMATIVE_TOKENS if " " in token
    ):
        return "answer", "User confirmed the pending receipt details.", None
    return "answer", "User replied to the pending interrupt.", None


def _applyManualFxConversion(slots: dict, parsedRate: dict) -> dict | None:
    extracted = slots.get("extractedReceipt") or {}
    if not isinstance(extracted, dict):
        return None
    fields = extracted.get("fields") or {}
    if not isinstance(fields, dict):
        return None
    originalAmount = fields.get("totalAmount")
    if not isinstance(originalAmount, (int, float)):
        try:
            originalAmount = float(str(originalAmount))
        except (TypeError, ValueError):
            return None
    originalCurrency = _normalizeCurrencyCode(
        parsedRate.get("lhsCurrency") or fields.get("currency") or ""
    )
    rate = parsedRate.get("rate")
    if not isinstance(rate, (int, float)):
        return None
    convertedAmount = round(float(originalAmount) * float(rate), 2)
    return {
        "supported": True,
        "manualOverride": True,
        "originalAmount": float(originalAmount),
        "fromCurrency": originalCurrency,
        "convertedAmount": convertedAmount,
        "convertedCurrency": "SGD",
        "rate": round(float(rate), 8),
        "provider": "manual_user_input",
        "originalRateInput": (
            f"{parsedRate.get('lhsAmount')} {originalCurrency} = "
            f"{parsedRate.get('rhsAmount')} SGD"
        ),
    }


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
    conversion = intakeState.get("slots", {}).get("currencyConversion") or {}
    if (
        intakeState["workflow"]["currentStep"] in {"submit_confirmation_answered", "policy_justification_answered"}
        and intakeState.get("pendingInterrupt") is None
        and not intakeState.get("slots", {}).get("submissionResult")
    ):
        response = _buildSubmitClaimAiMessage(state, intakeState)
        if response is not None:
            intakeState["workflow"]["currentStep"] = "submitting_claim"
            intakeState["workflow"]["status"] = "active"
            logEvent(
                logger,
                "intake.gpt.runtime_submit_claim",
                logCategory="agent",
                agent="intake-gpt",
                claimId=state.get("claimId"),
                threadId=state.get("threadId"),
                message="runtime advanced intake-gpt flow directly to submitClaim",
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
                "messages": [response],
                "intakeGpt": intakeState,
            }
    if (
        intakeState["workflow"]["currentStep"] == "claim_submitted"
        and intakeState.get("pendingInterrupt") is None
    ):
        response = _buildSubmissionAcknowledgement(intakeState)
        if response is not None:
            intakeState["workflow"]["status"] = "completed"
            intakeState["workflow"]["currentStep"] = "submission_acknowledged"
            logEvent(
                logger,
                "intake.gpt.runtime_submission_acknowledgement",
                logCategory="agent",
                agent="intake-gpt",
                claimId=state.get("claimId"),
                threadId=state.get("threadId"),
                message="runtime emitted submission acknowledgement",
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
                "messages": [response],
                "intakeGpt": intakeState,
            }
    if (
        intakeState["workflow"]["currentStep"] == "currency_converted"
        and isinstance(conversion, dict)
        and conversion.get("supported")
        and conversion.get("manualOverride")
        and intakeState.get("pendingInterrupt") is None
    ):
        response = _buildFieldConfirmationAiMessage(intakeState)
        pendingInterrupt = _pendingInterruptFromToolCalls(response)
        if pendingInterrupt is not None:
            intakeState["pendingInterrupt"] = pendingInterrupt
            intakeState["workflow"]["currentStep"] = pendingInterrupt["blockingStep"] or "awaiting_input"
            intakeState["workflow"]["status"] = "blocked"
        logEvent(
            logger,
            "intake.gpt.runtime_field_confirmation_after_manual_fx",
            logCategory="agent",
            agent="intake-gpt",
            claimId=state.get("claimId"),
            threadId=state.get("threadId"),
            message="runtime advanced manual-fx flow directly to field confirmation",
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
            "messages": [response],
            "intakeGpt": intakeState,
        }
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
    _persistRequestHumanInputMetadata(intakeState, hydratedResponse)
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


async def applyToolResultsNode(state: IntakeGptGraphState) -> dict:
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
            extractedReceiptVar.set(parsed)
            extractedCategory = ((parsed.get("fields") or {}).get("category") if isinstance(parsed, dict) else None)
            if _valuePresent(extractedCategory):
                slots["category"] = str(extractedCategory)
            updates["extractedReceipt"] = parsed
            intakeState["workflow"]["currentStep"] = "receipt_extracted"
            sessionClaimId = state.get("claimId", "")
            if sessionClaimId:
                fields = parsed.get("fields", {})
                confidence = parsed.get("confidence", {})
                imagePath = parsed.get("imagePath")
                bufferStep(
                    sessionClaimId=sessionClaimId,
                    action="receipt_uploaded",
                    details={"imagePath": imagePath},
                )
                bufferStep(
                    sessionClaimId=sessionClaimId,
                    action="ai_extraction",
                    details={
                        "confidence": confidence,
                        "merchant": fields.get("merchant"),
                        "amount": fields.get("totalAmount"),
                        "fields": fields,
                    },
                )
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
            pending = intakeState.get("pendingInterrupt") or {}
            expectedCurrency = ""
            if pending.get("kind") == "manual_fx_rate":
                expectedCurrency = _manualFxCurrencyLabel(intakeState)
            outcome, summary, parsedAnswer = _classifyInterruptReply(
                responseText,
                pendingKind=str(pending.get("kind") or ""),
                expectedCurrency=expectedCurrency,
            )
            intakeState["lastResolution"] = {
                "outcome": outcome,
                "responseText": responseText,
                "summary": summary,
            }
            slots["lastHumanInput"] = responseText
            if pending.get("kind") == "field_confirmation":
                slots["fieldConfirmationResponse"] = responseText
                draftBundle = _buildDraftClaimBundle(slots)
                if draftBundle is not None:
                    claimData, receiptData, intakeFindings = draftBundle
                    slots["claimData"] = claimData
                    slots["receiptData"] = receiptData
                    slots["intakeFindings"] = intakeFindings
                    updates["intakeFindings"] = intakeFindings
                intakeState["pendingInterrupt"] = None
                intakeState["workflow"]["status"] = (
                    "completed" if outcome == "end_conversation" else "active"
                )
                intakeState["workflow"]["currentStep"] = (
                    "conversation_closed"
                    if outcome == "end_conversation"
                    else "field_confirmation_answered"
                )
            elif pending.get("kind") == "manual_fx_rate":
                if outcome == "answer" and parsedAnswer:
                    manualConversion = _applyManualFxConversion(slots, parsedAnswer)
                    if manualConversion is not None:
                        slots["currencyConversion"] = manualConversion
                        updates["currencyConversion"] = manualConversion
                        slots["manualFxResponse"] = responseText
                        intakeState["pendingInterrupt"] = None
                        intakeState["workflow"]["status"] = "active"
                        intakeState["workflow"]["currentStep"] = "currency_converted"
                    else:
                        outcome = "ambiguous"
                        summary = "The exchange rate could not be applied to the extracted total."
                        intakeState["lastResolution"] = {
                            "outcome": outcome,
                            "responseText": responseText,
                            "summary": summary,
                        }
                if outcome == "end_conversation":
                    intakeState["pendingInterrupt"] = None
                    intakeState["workflow"]["status"] = "completed"
                    intakeState["workflow"]["currentStep"] = "conversation_closed"
                elif outcome == "ambiguous":
                    retryCount = int(pending.get("retryCount") or 0) + 1
                    intakeState["pendingInterrupt"] = {
                        **pending,
                        "retryCount": retryCount,
                        "status": "pending",
                    }
                    intakeState["workflow"]["status"] = "blocked"
                    intakeState["workflow"]["currentStep"] = "manual_fx_required"
            else:
                if pending.get("kind") == "policy_justification":
                    slots["justification"] = responseText
                    intakeFindings = dict(slots.get("intakeFindings") or {})
                    if intakeFindings:
                        intakeFindings["justification"] = responseText
                        slots["intakeFindings"] = intakeFindings
                        updates["intakeFindings"] = intakeFindings
                elif pending.get("kind") == "submit_confirmation":
                    slots["submitConfirmationResponse"] = responseText
                if outcome == "ambiguous":
                    retryCount = int(pending.get("retryCount") or 0) + 1
                    intakeState["pendingInterrupt"] = {
                        **pending,
                        "retryCount": retryCount,
                        "status": "pending",
                    }
                    intakeState["workflow"]["status"] = "blocked"
                    intakeState["workflow"]["currentStep"] = str(
                        pending.get("blockingStep") or pending.get("kind") or "awaiting_input"
                    )
                else:
                    intakeState["pendingInterrupt"] = None
                    intakeState["workflow"]["status"] = "completed" if outcome == "end_conversation" else "active"
                    intakeState["workflow"]["readyForSubmission"] = outcome == "answer"
                    intakeState["workflow"]["currentStep"] = (
                        "conversation_closed"
                        if outcome == "end_conversation"
                        else (
                            "submission_declined"
                            if outcome == "cancel_claim"
                            else (
                                "policy_justification_answered"
                                if pending.get("kind") == "policy_justification"
                                else (
                                    "submit_confirmation_answered"
                                    if pending.get("kind") == "submit_confirmation"
                                    else "field_confirmation_answered"
                                )
                            )
                        )
                    )
        elif latestTool.name == "searchPolicies":
            slots["policySearchResults"] = parsed
            query = _buildPolicySearchQuery(slots)
            if query:
                slots["policySearchQuery"] = query
            intakeState["workflow"]["currentStep"] = "policy_answered"
            results = []
            if isinstance(parsed, dict):
                candidateResults = parsed.get("results", parsed.get("policies", []))
                if isinstance(candidateResults, list):
                    results = candidateResults
            sessionClaimId = state.get("claimId", "")
            if sessionClaimId:
                policyRefs = [
                    {
                        "section": result.get("section"),
                        "category": result.get("category"),
                        "score": result.get("score"),
                    }
                    for result in results
                    if isinstance(result, dict)
                ]
                bufferStep(
                    sessionClaimId=sessionClaimId,
                    action="policy_check",
                    details={
                        "violations": [],
                        "policyRefs": policyRefs,
                        "compliant": True,
                        "query": slots.get("policySearchQuery") or query or "intake policy check",
                    },
                )
        elif latestTool.name == "submitClaim" and isinstance(parsed, dict):
            slots["submissionResult"] = parsed
            claimRecord = parsed.get("claim") or {}
            if isinstance(claimRecord, dict) and "error" not in parsed:
                updates["claimSubmitted"] = True
                claimNumber = claimRecord.get("claim_number") or claimRecord.get("claimNumber")
                if claimNumber:
                    updates["claimNumber"] = str(claimNumber)
                dbClaimId = claimRecord.get("id")
                if dbClaimId is not None:
                    try:
                        updates["dbClaimId"] = int(dbClaimId)
                        claimNumber = claimRecord.get("claim_number") or claimRecord.get("claimNumber")
                        await logIntakeStep(
                            claimId=int(dbClaimId),
                            action="claim_submitted",
                            details={"claimNumber": claimNumber, "status": claimRecord.get("status", "pending")},
                        )
                    except (TypeError, ValueError):
                        pass
                intakeFindingsFromDb = claimRecord.get("intake_findings")
                if isinstance(intakeFindingsFromDb, dict):
                    slots["intakeFindings"] = intakeFindingsFromDb
                    updates["intakeFindings"] = intakeFindingsFromDb
                intakeState["workflow"]["currentStep"] = "claim_submitted"
                intakeState["workflow"]["readyForSubmission"] = False
                intakeState["workflow"]["status"] = "active"
            else:
                intakeState["workflow"]["currentStep"] = "submission_failed"

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
