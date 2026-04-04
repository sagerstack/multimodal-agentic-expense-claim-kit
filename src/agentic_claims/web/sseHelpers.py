"""Ported streaming helpers from app.py + runGraph SSE generator.

All helper functions (_stripToolCallJson, _stripThinkingTags, _formatElapsed,
_summarizeToolOutput, TOOL_LABELS) are ported verbatim from the Chainlit app.py.
runGraph translates LangGraph astream_events into SSE events.
"""

import json
import logging
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.sse import ServerSentEvent
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from agentic_claims.core.config import getSettings
from agentic_claims.web.sseEvents import SseEvent

logger = logging.getLogger(__name__)

TOOL_LABELS = {
    "getClaimSchema": "Loading claim schema...",
    "extractReceiptFields": "Extracting receipt fields...",
    "searchPolicies": "Checking policies...",
    "convertCurrency": "Converting currency...",
    "submitClaim": "Submitting claim...",
}


def _stripToolCallJson(text: str) -> str:
    """Strip raw tool call JSON that reasoning models include in text content.

    QwQ-32B and similar models output tool call specifications as text
    alongside proper function calling. This removes trailing JSON blocks
    matching {"name": "...", "arguments": {...}} patterns.
    """
    idx = text.find('{"name":')
    if idx == -1:
        idx = text.find('{"name" :')
    if idx > 0:
        return text[:idx].strip()
    return text


def _stripThinkingTags(text: str) -> str:
    """Strip XML-style thinking/reasoning/tools wrappers from model output.

    Models like QwQ-32B sometimes emit <Thinking>...</Thinking>,
    <think>...</think>, or <tools>...</tools> tags in their text content.
    The UI handles reasoning display via the thinking panel, and tool calls
    are handled by LangGraph, so these leak through as unwanted visible text.
    """
    cleaned = re.sub(
        r"<(?:Thinking|thinking|think|Think|reasoning|Reasoning|tools|Tools)>.*?</(?:Thinking|thinking|think|Think|reasoning|Reasoning|tools|Tools)>",
        "",
        text,
        flags=re.DOTALL,
    )
    return cleaned.strip()


def _formatElapsed(elapsed: float) -> str:
    """Format elapsed seconds into a human-readable duration string."""
    if elapsed >= 60:
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        return f"{minutes}m {seconds}s"
    seconds = int(elapsed)
    if seconds < 1:
        return "<1s"
    return f"{seconds}s"


def _summarizeToolOutput(toolName: str, toolOutput) -> str:
    """Create a human-readable summary of a tool's output for the Thinking panel."""
    try:
        if isinstance(toolOutput, str):
            data = json.loads(toolOutput)
        elif hasattr(toolOutput, "content"):
            data = (
                json.loads(toolOutput.content)
                if isinstance(toolOutput.content, str)
                else toolOutput.content
            )
        else:
            data = toolOutput

        if not isinstance(data, dict):
            return f"Completed {toolName}"

        if "error" in data:
            return f"Error: {data['error']}"

        if toolName == "getClaimSchema":
            claims = data.get("claims", [])
            receipts = data.get("receipts", [])
            return f"Schema loaded: {len(claims)} claim fields, {len(receipts)} receipt fields"

        if toolName == "extractReceiptFields":
            fields = data.get("fields", {})
            merchant = fields.get("merchant", "unknown")
            total = fields.get("totalAmount", "unknown")
            currency = fields.get("currency", "")
            return f"Extracted receipt: {merchant}, {currency} {total}"

        if toolName == "searchPolicies":
            results = data.get("results", data.get("policies", []))
            if isinstance(results, list):
                return f"Found {len(results)} relevant policy clause(s)"
            return "Policy search completed"

        if toolName == "convertCurrency":
            fromAmount = data.get("fromAmount", data.get("originalAmount", "?"))
            fromCurrency = data.get("fromCurrency", data.get("originalCurrency", "?"))
            amountSgd = data.get("amountSgd", data.get("convertedAmount", "?"))
            rate = data.get("rate", data.get("exchangeRate", "?"))
            return f"Converted {fromCurrency} {fromAmount} → SGD {amountSgd} (rate: {rate})"

        if toolName == "submitClaim":
            if "error" in data:
                return f"Submission error: {data['error']}"
            claimId = data.get("claim", {}).get("id", "")
            return f"Claim submitted successfully (ID: {claimId})"

        return f"Completed {toolName}"

    except Exception:
        return f"Completed {toolName}"


TOOL_TO_STEP = {
    "extractReceiptFields": 1,
    "searchPolicies": 2,
    "submitClaim": 3,
}

PATHWAY_WAITING_TEXT = {
    0: "",
    1: "Awaiting receipt upload...",
    2: "Awaiting extraction data...",
    3: "Awaiting policy check...",
}


def _nowTimestamp() -> str:
    sgt = ZoneInfo("Asia/Singapore")
    return datetime.now(sgt).strftime("%I:%M:%S %p")


def _buildPathwaySteps(
    completedTools: set,
    activeTools: set,
    hasImage: bool,
    toolTimestamps: dict,
    extractionDetails: dict | None = None,
) -> list:
    """Build the 4 Decision Pathway steps from current tool state."""
    steps = [
        {"name": "Receipt Uploaded", "icon": "cloud_upload", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": ""},
        {"name": "AI Extraction", "icon": "troubleshoot", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": PATHWAY_WAITING_TEXT[1]},
        {"name": "Policy Check", "icon": "rule", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": PATHWAY_WAITING_TEXT[2]},
        {"name": "Final Decision", "icon": "verified", "status": "pending", "timestamp": None, "details": None, "description": None, "waitingText": PATHWAY_WAITING_TEXT[3]},
    ]

    # Step 0: Receipt Uploaded
    if hasImage:
        steps[0]["status"] = "completed"
        steps[0]["timestamp"] = toolTimestamps.get("receiptUploaded", _nowTimestamp())

    # Steps 1-3: tool-driven
    for toolName, stepIdx in TOOL_TO_STEP.items():
        if toolName in completedTools:
            steps[stepIdx]["status"] = "completed"
            steps[stepIdx]["timestamp"] = toolTimestamps.get(toolName)
            if toolName == "extractReceiptFields" and extractionDetails:
                steps[stepIdx]["details"] = extractionDetails
            if toolName == "submitClaim":
                steps[stepIdx]["description"] = "Claim submitted successfully"
        elif toolName in activeTools:
            steps[stepIdx]["status"] = "in_progress"
            steps[stepIdx]["timestamp"] = toolTimestamps.get(toolName)

    return steps


def _extractExtractionDetails(toolOutput) -> dict | None:
    """Parse extractReceiptFields output into pathway display details."""
    try:
        if isinstance(toolOutput, str):
            data = json.loads(toolOutput)
        elif hasattr(toolOutput, "content"):
            data = json.loads(toolOutput.content) if isinstance(toolOutput.content, str) else toolOutput.content
        else:
            data = toolOutput

        if not isinstance(data, dict):
            return None

        fields = data.get("fields", {})
        confidence = data.get("confidence", data.get("confidenceScores", {}))

        if isinstance(confidence, dict) and confidence:
            scores = [float(v) for v in confidence.values() if isinstance(v, (int, float))]
            avgConfidence = round((sum(scores) / len(scores)) * 100 if scores and all(s <= 1 for s in scores) else sum(scores) / len(scores) if scores else 0, 1)
        elif isinstance(confidence, (int, float)):
            avgConfidence = round(confidence * 100 if confidence <= 1 else confidence, 1)
        else:
            avgConfidence = 0

        currency = fields.get("currency", "")
        totalAmount = fields.get("totalAmount", "")
        amountStr = f"{currency} {totalAmount}" if currency else str(totalAmount)

        return {
            "confidence": avgConfidence,
            "merchant": fields.get("merchant", "Unknown"),
            "amount": amountStr,
            "date": fields.get("date", "Unknown"),
        }
    except Exception:
        return None


async def _getFallbackMessage(graph, config: dict) -> str:
    """Extract last AI message from graph state as fallback when token buffer is empty."""
    try:
        finalState = await graph.aget_state(config=config)
        messages = finalState.values.get("messages", [])
        for msg in reversed(messages):
            if (
                hasattr(msg, "type")
                and msg.type == "ai"
                and hasattr(msg, "content")
                and msg.content
            ):
                return _stripThinkingTags(_stripToolCallJson(str(msg.content)))
    except Exception as e:
        logger.error(f"Error in fallback message extraction: {e}", exc_info=True)
    return ""


def _calcProgressPct(thinkingEntries: list, graphState: dict | None) -> int:
    """Calculate progress from tool milestones.
    extractReceiptFields completed -> 33%
    searchPolicies completed -> 50%
    User confirmed (ready for submission) -> 66%
    submitClaim completed -> 100%
    """
    completedTools = set()
    for e in thinkingEntries:
        if e.get("type") == "tool" and e.get("name"):
            completedTools.add(e["name"])

    if graphState:
        if graphState.get("extractedReceipt"):
            completedTools.add("extractReceiptFields")
        if graphState.get("currencyConversion"):
            completedTools.add("convertCurrency")
        if graphState.get("claimSubmitted"):
            completedTools.add("submitClaim")

    if "submitClaim" in completedTools:
        return 100
    if "askHuman" in completedTools or "convertCurrency" in completedTools:
        return 66
    if "searchPolicies" in completedTools:
        return 50
    if "extractReceiptFields" in completedTools:
        return 33
    return 0


def _extractSummaryData(thinkingEntries: list, graphState: dict | None = None, claimId: str = "") -> dict | None:
    """Extract summary panel data from tool outputs and graph state.

    Uses thinkingEntries (current turn's tool outputs) first, then falls
    back to graphState for data from prior turns (e.g. extractedReceipt
    from turn 1 when turn 2 only does submission).
    """
    totalAmount = ""
    merchant = ""
    category = ""
    currency = ""
    warningCount = 0
    submitted = False
    convertedAmount = ""
    extractedClaimNumber = ""

    submitCallInEntries = any(
        e.get("name") == "submitClaim" and e.get("type") == "tool"
        for e in thinkingEntries
    )

    hasReceiptData = False

    for entry in thinkingEntries:
        if entry["type"] != "tool":
            continue

        toolName = entry.get("name", "")
        toolOutput = entry.get("output", "")

        try:
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput

            if not isinstance(data, dict):
                continue

            if toolName == "extractReceiptFields":
                fields = data.get("fields", {})
                merchant = fields.get("merchant", "")
                totalAmount = fields.get("totalAmount", "")
                currency = fields.get("currency", "SGD")
                category = fields.get("category", "")
                hasReceiptData = True

            elif toolName == "searchPolicies":
                results = data.get("results", data.get("policies", []))
                if isinstance(results, list):
                    warningCount = len(results)

            elif toolName == "convertCurrency":
                convertedAmount = str(data.get("convertedAmount", data.get("amountSgd", "")))

            elif toolName == "submitClaim":
                if "error" not in data:
                    submitted = True
                    claimData = data.get("claim", {})
                    extractedClaimNumber = claimData.get("claim_number", "")

        except Exception:
            continue

    # Fall back to graph state for receipt data from prior turns
    if not hasReceiptData and graphState:
        extractedReceipt = graphState.get("extractedReceipt")
        if isinstance(extractedReceipt, dict):
            fields = extractedReceipt.get("fields", extractedReceipt)
            merchant = fields.get("merchant", "")
            totalAmount = fields.get("totalAmount", "")
            currency = fields.get("currency", "SGD")
            category = fields.get("category", "")
            hasReceiptData = bool(merchant or totalAmount)

        conversionData = graphState.get("currencyConversion")
        if isinstance(conversionData, dict) and not convertedAmount:
            convertedAmount = str(conversionData.get("convertedAmount", conversionData.get("amountSgd", "")))

    # Check graphState claimSubmitted regardless of hasReceiptData
    # (prior turn may have submitted while current turn has new receipt data)
    if graphState and graphState.get("claimSubmitted"):
        submitted = True

    if not extractedClaimNumber and graphState:
        extractedClaimNumber = graphState.get("claimNumber", "") or ""

    # BUG-013: If graphState says submitted but no submitClaim tool call
    # exists in THIS turn's thinkingEntries, trust the graphState (prior turn
    # did submit). But if submitted was set from thinkingEntries parsing and
    # there's no actual submitClaim entry, suppress it (hallucination).
    if submitted and not submitCallInEntries and not graphState.get("claimSubmitted"):
        logger.warning("BUG-013: _extractSummaryData suppressing submitted=True — no submitClaim in thinkingEntries and graphState not submitted")
        submitted = False
        extractedClaimNumber = ""

    if not hasReceiptData:
        return None

    displayAmount = f"SGD {convertedAmount}" if convertedAmount else f"{currency} {totalAmount}"

    progressPct = _calcProgressPct(thinkingEntries, graphState)

    return {
        "totalAmount": displayAmount,
        "itemCount": 1,
        "topCategory": category or "--",
        "warningCount": warningCount,
        "progressPct": progressPct,
        "claimNumber": extractedClaimNumber or "",
        "submitted": submitted,
        "claimId": claimId,
        "batchItems": [
            {
                "merchant": merchant or "Unknown",
                "amount": displayAmount,
                "category": category or "uncategorized",
            }
        ],
    }


def _extractConfidenceScores(thinkingEntries: list) -> dict | None:
    """Extract per-field confidence scores from extractReceiptFields output."""
    for entry in thinkingEntries:
        if entry.get("type") != "tool" or entry.get("name") != "extractReceiptFields":
            continue
        try:
            toolOutput = entry.get("output", "")
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput
            if isinstance(data, dict):
                confidence = data.get("confidence", data.get("confidenceScores"))
                if isinstance(confidence, dict):
                    return {
                        k: int(float(v) * 100) if isinstance(v, float) and v <= 1 else int(v)
                        for k, v in confidence.items()
                    }
        except Exception:
            continue
    return None


def _extractViolations(thinkingEntries: list) -> list | None:
    """Extract policy violation citations from searchPolicies output."""
    violations = []
    for entry in thinkingEntries:
        if entry.get("type") != "tool" or entry.get("name") != "searchPolicies":
            continue
        try:
            toolOutput = entry.get("output", "")
            if isinstance(toolOutput, str):
                data = json.loads(toolOutput)
            elif hasattr(toolOutput, "content"):
                data = (
                    json.loads(toolOutput.content)
                    if isinstance(toolOutput.content, str)
                    else toolOutput.content
                )
            else:
                data = toolOutput
            if isinstance(data, dict):
                results = data.get("violations", data.get("results", []))
                if isinstance(results, list):
                    for r in results:
                        if isinstance(r, dict):
                            text = r.get("text", r.get("clause", r.get("violation", "")))
                            if text:
                                violations.append(str(text))
                        elif isinstance(r, str):
                            violations.append(r)
        except Exception:
            continue
    return violations if violations else None


def _buildGraphInput(graphInput: dict) -> dict:
    """Build LangGraph input from the queue payload."""
    claimId = graphInput["claimId"]
    message = graphInput.get("message", "")
    hasImage = graphInput.get("hasImage", False)

    if hasImage:
        userText = message.strip()
        if userText:
            humanMsg = HumanMessage(
                content=f'User says: "{userText}"\n\n'
                f"I've also uploaded a receipt image for claim {claimId}. "
                "Please process it using extractReceiptFields."
            )
        else:
            humanMsg = HumanMessage(
                content=f"I've uploaded a receipt image for claim {claimId}. "
                "Please process it using extractReceiptFields. "
                "No expense description was provided."
            )
    else:
        humanMsg = HumanMessage(content=message)

    return {
        "claimId": claimId,
        "status": "draft",
        "messages": [humanMsg],
    }


async def runGraph(graph, graphInput: dict, request: Request, templates: Jinja2Templates):
    """Translate LangGraph astream_events into SSE events.

    Yields ServerSentEvent instances classifying each astream_events event
    into the SseEvent taxonomy. Checks request.is_disconnected() at each
    iteration to break on client disconnect.
    """
    settings = getSettings()
    logger.info(
        "runGraph started: threadId=%s, isResume=%s",
        graphInput.get("threadId"),
        graphInput.get("isResume"),
    )
    thinkingEntries = []
    tokenBuffer = ""
    reasoningBuffer = ""
    finalResponse = ""
    pendingToolCalls = 0
    hadAnyToolCall = False
    toolStartTimes = {}
    turnStart = time.time()

    # Decision Pathway state
    pathwayActiveTools: set = set()
    pathwayCompletedTools: set = set()
    pathwayToolTimestamps: dict = {}
    pathwayExtractionDetails: dict | None = None
    hasImage = graphInput.get("hasImage", False)

    # Submission table state (in-memory claims accumulated during the turn)
    tableClaims: list[dict] = []


    if hasImage:
        pathwayToolTimestamps["receiptUploaded"] = _nowTimestamp()

    threadId = graphInput["threadId"]
    config = {"configurable": {"thread_id": threadId}}

    # Reconstruct pathway state from graph state (preserves progress across turns)
    try:
        t0 = time.time()
        priorState = await graph.aget_state(config=config)
        logger.info("aget_state took %.2fs", time.time() - t0)
        if priorState and priorState.values:
            sv = priorState.values
            if sv.get("extractedReceipt"):
                pathwayCompletedTools.add("extractReceiptFields")
                hasImage = True  # receipt was uploaded in a prior turn
                pathwayExtractionDetails = _extractExtractionDetails(sv["extractedReceipt"])
                if "extractReceiptFields" not in pathwayToolTimestamps:
                    pathwayToolTimestamps["extractReceiptFields"] = _nowTimestamp()
                if "receiptUploaded" not in pathwayToolTimestamps:
                    pathwayToolTimestamps["receiptUploaded"] = _nowTimestamp()
            if sv.get("violations") is not None:
                pathwayCompletedTools.add("searchPolicies")
                if "searchPolicies" not in pathwayToolTimestamps:
                    pathwayToolTimestamps["searchPolicies"] = _nowTimestamp()
            if sv.get("claimSubmitted"):
                pathwayCompletedTools.add("submitClaim")
                if "submitClaim" not in pathwayToolTimestamps:
                    pathwayToolTimestamps["submitClaim"] = _nowTimestamp()
                if "searchPolicies" not in pathwayCompletedTools:
                    pathwayCompletedTools.add("searchPolicies")
                if "searchPolicies" not in pathwayToolTimestamps:
                    pathwayToolTimestamps["searchPolicies"] = _nowTimestamp()
    except Exception as e:
        logger.debug(f"Could not reconstruct pathway from graph state: {e}")

    yield ServerSentEvent(raw_data="<!-- thinking -->", event=SseEvent.THINKING_START)

    # Initial pathway state
    try:
        initialSteps = _buildPathwaySteps(pathwayCompletedTools, pathwayActiveTools, hasImage, pathwayToolTimestamps)
        pathwayHtml = templates.get_template("partials/decision_pathway.html").render(steps=initialSteps)
        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
    except Exception as e:
        logger.error(f"Error rendering initial pathway: {e}", exc_info=True)

    if graphInput.get("isResume"):
        invokeInput = Command(resume=graphInput["resumeData"])
    else:
        invokeInput = _buildGraphInput(graphInput)

    try:
        async for event in graph.astream_events(invokeInput, config=config, version="v2"):
            if await request.is_disconnected():
                break

            eventKind = event.get("event")
            logger.info("astream_events event: %s - %s", eventKind, event.get("name", ""))

            if eventKind == "on_chat_model_stream":
                if pendingToolCalls > 0:
                    continue

                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    tokenBuffer += chunk.content
                    if settings.enable_response_streaming and (not hadAnyToolCall or pendingToolCalls == 0):
                        yield ServerSentEvent(raw_data=chunk.content, event=SseEvent.TOKEN)

                if chunk:
                    reasoning = None
                    if hasattr(chunk, "additional_kwargs"):
                        reasoning = chunk.additional_kwargs.get(
                            "reasoning_content"
                        ) or chunk.additional_kwargs.get("reasoning")
                    if not reasoning and hasattr(chunk, "response_metadata"):
                        reasoning = chunk.response_metadata.get(
                            "reasoning_content"
                        ) or chunk.response_metadata.get("reasoning")
                    if reasoning:
                        reasoningBuffer += str(reasoning)

            elif eventKind == "on_chat_model_end":
                if pendingToolCalls > 0:
                    tokenBuffer = ""
                    reasoningBuffer = ""
                    continue

                output = event.get("data", {}).get("output")
                hasToolCalls = output and hasattr(output, "tool_calls") and output.tool_calls

                if hasToolCalls:
                    cleanedBuffer = _stripToolCallJson(tokenBuffer.strip())
                    if cleanedBuffer:
                        thinkingEntries.append(
                            {
                                "type": "reasoning",
                                "content": cleanedBuffer,
                            }
                        )
                    if reasoningBuffer.strip():
                        thinkingEntries.append(
                            {
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            }
                        )
                    # Show brief reasoning summary in thinking panel
                    reasoningText = reasoningBuffer.strip() or cleanedBuffer or ""
                    if reasoningText:
                        preview = reasoningText[:120].replace("\n", " ").strip()
                        if len(reasoningText) > 120:
                            preview += "..."
                        yield ServerSentEvent(
                            raw_data="Reasoning...",
                            event=SseEvent.STEP_NAME,
                        )
                        yield ServerSentEvent(
                            raw_data=f'<div class="text-xs text-outline/50 italic mt-1">{preview}</div>',
                            event=SseEvent.STEP_CONTENT,
                        )
                    tokenBuffer = ""
                    reasoningBuffer = ""
                else:
                    if reasoningBuffer.strip():
                        thinkingEntries.append(
                            {
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            }
                        )
                        # Show brief reasoning summary in thinking panel
                        preview = reasoningBuffer.strip()[:120].replace("\n", " ").strip()
                        if len(reasoningBuffer.strip()) > 120:
                            preview += "..."
                        yield ServerSentEvent(
                            raw_data="Reasoning...",
                            event=SseEvent.STEP_NAME,
                        )
                        yield ServerSentEvent(
                            raw_data=f'<div class="text-xs text-outline/50 italic mt-1">{preview}</div>',
                            event=SseEvent.STEP_CONTENT,
                        )
                    yield ServerSentEvent(raw_data="Preparing response...", event=SseEvent.STEP_NAME)
                    finalResponse = _stripToolCallJson(tokenBuffer)
                    tokenBuffer = ""
                    reasoningBuffer = ""

            elif eventKind == "on_tool_start":
                toolName = event.get("name", "unknown")
                toolStartTimes[toolName] = time.time()
                pendingToolCalls += 1
                hadAnyToolCall = True
                label = TOOL_LABELS.get(toolName, f"Running {toolName}...")
                yield ServerSentEvent(raw_data=label, event=SseEvent.STEP_NAME)

                # Pathway: mark tool as in_progress
                if toolName in TOOL_TO_STEP:
                    pathwayActiveTools.add(toolName)
                    pathwayToolTimestamps[toolName] = _nowTimestamp()
                    try:
                        steps = _buildPathwaySteps(pathwayCompletedTools, pathwayActiveTools, hasImage, pathwayToolTimestamps, pathwayExtractionDetails)
                        pathwayHtml = templates.get_template("partials/decision_pathway.html").render(steps=steps)
                        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
                    except Exception as e:
                        logger.error(f"Error rendering pathway on tool start: {e}", exc_info=True)

            elif eventKind == "on_tool_end":
                toolName = event.get("name", "unknown")
                toolOutput = event.get("data", {}).get("output", "")
                startTime = toolStartTimes.pop(toolName, None)
                elapsed = time.time() - startTime if startTime else 0
                summary = _summarizeToolOutput(toolName, toolOutput)
                thinkingEntries.append(
                    {
                        "type": "tool",
                        "name": toolName,
                        "elapsed": elapsed,
                        "output": toolOutput,
                    }
                )
                pendingToolCalls = max(0, pendingToolCalls - 1)
                yield ServerSentEvent(
                    raw_data=f'<div class="text-xs text-outline mt-1">{summary}</div>',
                    event=SseEvent.STEP_CONTENT,
                )

                # Pathway: mark tool as completed
                if toolName in TOOL_TO_STEP:
                    pathwayActiveTools.discard(toolName)
                    pathwayCompletedTools.add(toolName)
                    pathwayToolTimestamps[toolName] = _nowTimestamp()
                    if toolName == "submitClaim" and "searchPolicies" not in pathwayCompletedTools:
                        pathwayCompletedTools.add("searchPolicies")
                        pathwayToolTimestamps["searchPolicies"] = _nowTimestamp()
                    if toolName == "extractReceiptFields":
                        pathwayExtractionDetails = _extractExtractionDetails(toolOutput)
                    try:
                        steps = _buildPathwaySteps(pathwayCompletedTools, pathwayActiveTools, hasImage, pathwayToolTimestamps, pathwayExtractionDetails)
                        pathwayHtml = templates.get_template("partials/decision_pathway.html").render(steps=steps)
                        yield ServerSentEvent(raw_data=pathwayHtml, event=SseEvent.PATHWAY_UPDATE)
                    except Exception as e:
                        logger.error(f"Error rendering pathway on tool end: {e}", exc_info=True)

                # Table: add/update row after extraction or submission
                if toolName == "extractReceiptFields":
                    details = _extractExtractionDetails(toolOutput)
                    if details:
                        tableClaims.append({
                            "merchant": details.get("merchant", "Processing..."),
                            "receipt_date": details.get("date", "--"),
                            "total_amount": details.get("amount", "--").replace("SGD ", "").replace("USD ", ""),
                            "currency": "SGD",
                            "status": "processing",
                            "created_at": datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M"),
                        })
                elif toolName == "submitClaim":
                    if tableClaims:
                        tableClaims[-1]["status"] = "submitted"

                if toolName in ("extractReceiptFields", "submitClaim"):
                    try:
                        renderClaims = tableClaims
                        if toolName == "submitClaim":
                            from agentic_claims.web.routers.chat import fetchClaimsForTable
                            dbClaims = await fetchClaimsForTable()
                            if dbClaims:
                                renderClaims = dbClaims
                        sessionTotal = sum(float(c.get("total_amount", 0) or 0) for c in renderClaims if c.get("total_amount") and str(c.get("total_amount")) != "--")
                        tableHtml = templates.get_template("partials/submission_table.html").render(
                            claims=renderClaims,
                            sessionTotal=f"SGD {sessionTotal:.2f}",
                            itemCount=len(renderClaims),
                        )
                        yield ServerSentEvent(raw_data=tableHtml, event=SseEvent.TABLE_UPDATE)
                    except Exception as e:
                        logger.error(f"Error rendering table on tool end: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Error during graph streaming: {e}", exc_info=True)
        yield ServerSentEvent(raw_data=str(e), event=SseEvent.ERROR)
        return

    # Thinking done summary
    totalElapsed = time.time() - turnStart
    toolCount = sum(1 for e in thinkingEntries if e["type"] == "tool")
    toolLabel = "tool" if toolCount == 1 else "tools"
    summary = f"Thought for {_formatElapsed(totalElapsed)} . {toolCount} {toolLabel}"
    yield ServerSentEvent(raw_data=summary, event=SseEvent.THINKING_DONE)
    logger.info("Thinking done: %s", summary)

    # Fetch graph state once — reused for summary panel, interrupt check, and fallback message
    finalState = None
    graphStateValues = None
    try:
        finalState = await graph.aget_state(config=config)
        graphStateValues = finalState.values if finalState else None
    except Exception as e:
        logger.error(f"Error fetching graph state: {e}", exc_info=True)

    # Summary panel update (uses graph state for cross-turn receipt data)
    claimId = graphInput.get("claimId", "")
    summaryData = _extractSummaryData(thinkingEntries, graphState=graphStateValues, claimId=claimId)
    if summaryData:
        try:
            summaryTemplate = templates.get_template("partials/summary_panel.html")
            summaryHtml = summaryTemplate.render(**summaryData)
            yield ServerSentEvent(raw_data=summaryHtml, event=SseEvent.SUMMARY_UPDATE)
        except Exception as e:
            logger.error(f"Error rendering summary panel: {e}", exc_info=True)

    # Check for interrupt via graph state
    try:
        if finalState and finalState.next:
            for task in finalState.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    payload = task.interrupts[0].value
                    question = (
                        payload.get("question", str(payload))
                        if isinstance(payload, dict)
                        else str(payload)
                    )
                    request.session["awaiting_clarification"] = True
                    yield ServerSentEvent(raw_data=question, event=SseEvent.INTERRUPT)
                    return
    except Exception as e:
        logger.error(f"Error checking interrupt state: {e}", exc_info=True)

    # Extract final response text
    finalText = ""
    if finalResponse and finalResponse.strip():
        finalText = _stripThinkingTags(finalResponse).strip()
    if not finalText and tokenBuffer.strip():
        finalText = _stripThinkingTags(_stripToolCallJson(tokenBuffer)).strip()
    if not finalText:
        # Use already-fetched state if available, otherwise fetch
        if graphStateValues:
            messages = graphStateValues.get("messages", [])
            for msg in reversed(messages):
                if (
                    hasattr(msg, "type")
                    and msg.type == "ai"
                    and hasattr(msg, "content")
                    and msg.content
                ):
                    finalText = _stripThinkingTags(_stripToolCallJson(str(msg.content)))
                    break
        if not finalText:
            finalText = await _getFallbackMessage(graph, config)

    # BUG-013: Detect hallucinated claim submission (second layer — message)
    if finalText:
        submittedInText = "submitted" in finalText.lower() or "CLAIM-" in finalText
        submitCallMade = any(
            e.get("name") == "submitClaim"
            for e in thinkingEntries
            if e.get("type") == "tool"
        )
        if submittedInText and not submitCallMade:
            logger.warning("BUG-013: Hallucinated submission detected — AI claimed submission without submitClaim tool call")
            try:
                template = templates.get_template("partials/message_bubble.html")
                errorHtml = template.render(
                    content="I encountered an issue submitting your claim. The submission did not complete. Please try again by typing 'submit' or 'yes'.",
                    isAi=True,
                    confidenceScores=None,
                    violations=None,
                    timestamp=datetime.now(ZoneInfo("Asia/Singapore")).strftime("%-I:%M %p"),
                )
            except Exception:
                errorHtml = '<div class="ai-message">I encountered an issue submitting your claim. Please try again by typing "submit".</div>'
            yield ServerSentEvent(raw_data=errorHtml, event=SseEvent.MESSAGE)
            return

    if finalText:
        confidenceScores = _extractConfidenceScores(thinkingEntries)
        violations = _extractViolations(thinkingEntries)
        try:
            template = templates.get_template("partials/message_bubble.html")
            messageHtml = template.render(
                content=finalText,
                isAi=True,
                confidenceScores=confidenceScores,
                violations=violations,
                timestamp=datetime.now().strftime("%-I:%M %p"),
            )
        except Exception:
            messageHtml = f'<div class="ai-message">{finalText}</div>'
        yield ServerSentEvent(raw_data=messageHtml, event=SseEvent.MESSAGE)
        logger.info("Message yielded: %d chars", len(finalText))
