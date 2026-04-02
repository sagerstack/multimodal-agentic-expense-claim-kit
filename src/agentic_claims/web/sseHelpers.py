"""Ported streaming helpers from app.py + runGraph SSE generator.

All helper functions (_stripToolCallJson, _stripThinkingTags, _formatElapsed,
_summarizeToolOutput, TOOL_LABELS) are ported verbatim from the Chainlit app.py.
runGraph translates LangGraph astream_events into SSE events.
"""

import json
import logging
import re
import time

from fastapi.sse import ServerSentEvent
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from starlette.requests import Request
from starlette.templating import Jinja2Templates

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
    """Strip XML-style thinking/reasoning wrappers from model output.

    Models like QwQ-32B sometimes emit <Thinking>...</Thinking> or
    <think>...</think> tags in their text content. The UI handles
    reasoning display via the thinking panel, so these leak through
    as unwanted visible text.
    """
    cleaned = re.sub(
        r"<(?:Thinking|thinking|think|Think|reasoning|Reasoning)>.*?</(?:Thinking|thinking|think|Think|reasoning|Reasoning)>",
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
            amountSgd = data.get("amountSgd", data.get("convertedAmount", "?"))
            rate = data.get("rate", data.get("exchangeRate", "?"))
            return f"Converted to SGD {amountSgd} (rate: {rate})"

        if toolName == "submitClaim":
            if "error" in data:
                return f"Submission error: {data['error']}"
            claimId = data.get("claim", {}).get("id", "")
            return f"Claim submitted successfully (ID: {claimId})"

        return f"Completed {toolName}"

    except Exception:
        return f"Completed {toolName}"


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


def _extractSummaryData(thinkingEntries: list) -> dict | None:
    """Extract summary panel data from tool outputs in thinking entries."""
    totalAmount = ""
    merchant = ""
    category = ""
    currency = ""
    warningCount = 0
    submitted = False
    convertedAmount = ""

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

        except Exception:
            continue

    if not hasReceiptData:
        return None

    displayAmount = f"SGD {convertedAmount}" if convertedAmount else f"{currency} {totalAmount}"

    progressPct = 25
    if hasReceiptData:
        progressPct = 50
    if submitted:
        progressPct = 100

    return {
        "totalAmount": displayAmount,
        "itemCount": 1,
        "topCategory": category or "--",
        "warningCount": warningCount,
        "progressPct": progressPct,
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
    thinkingEntries = []
    tokenBuffer = ""
    reasoningBuffer = ""
    pendingToolCalls = 0
    toolStartTimes = {}
    turnStart = time.time()

    yield ServerSentEvent(data="", event=SseEvent.THINKING_START)

    threadId = graphInput["threadId"]
    config = {"configurable": {"thread_id": threadId}}

    if graphInput.get("isResume"):
        invokeInput = Command(resume=graphInput["resumeData"])
    else:
        invokeInput = _buildGraphInput(graphInput)

    try:
        async for event in graph.astream_events(invokeInput, config=config, version="v2"):
            if await request.is_disconnected():
                break

            eventKind = event.get("event")

            if eventKind == "on_chat_model_stream":
                if pendingToolCalls > 0:
                    continue

                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    tokenBuffer += chunk.content
                    yield ServerSentEvent(data=chunk.content, event=SseEvent.TOKEN)

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
                    tokenBuffer = ""
                    reasoningBuffer = ""

            elif eventKind == "on_tool_start":
                toolName = event.get("name", "unknown")
                toolStartTimes[toolName] = time.time()
                pendingToolCalls += 1
                label = TOOL_LABELS.get(toolName, f"Running {toolName}...")
                yield ServerSentEvent(data=label, event=SseEvent.STEP_NAME)

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
                yield ServerSentEvent(data=summary, event=SseEvent.STEP_CONTENT)
                if pendingToolCalls == 0:
                    yield ServerSentEvent(data="Analyzing...", event=SseEvent.STEP_NAME)

    except Exception as e:
        logger.error(f"Error during graph streaming: {e}", exc_info=True)
        yield ServerSentEvent(data=str(e), event=SseEvent.ERROR)
        return

    # Thinking done summary
    totalElapsed = time.time() - turnStart
    toolCount = sum(1 for e in thinkingEntries if e["type"] == "tool")
    toolLabel = "tool" if toolCount == 1 else "tools"
    summary = f"Thought for {_formatElapsed(totalElapsed)} . {toolCount} {toolLabel}"
    yield ServerSentEvent(data=summary, event=SseEvent.THINKING_DONE)

    # Summary panel update
    summaryData = _extractSummaryData(thinkingEntries)
    if summaryData:
        try:
            summaryTemplate = templates.get_template("partials/summary_panel.html")
            summaryHtml = summaryTemplate.render(**summaryData)
            yield ServerSentEvent(data=summaryHtml, event=SseEvent.SUMMARY_UPDATE)
        except Exception as e:
            logger.error(f"Error rendering summary panel: {e}", exc_info=True)

    # Check for interrupt via graph state
    try:
        finalState = await graph.aget_state(config=config)
        if finalState.next:
            for task in finalState.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    payload = task.interrupts[0].value
                    question = (
                        payload.get("question", str(payload))
                        if isinstance(payload, dict)
                        else str(payload)
                    )
                    request.session["awaiting_clarification"] = True
                    yield ServerSentEvent(data=question, event=SseEvent.INTERRUPT)
                    return
    except Exception as e:
        logger.error(f"Error checking interrupt state: {e}", exc_info=True)

    # Extract final response text
    finalText = ""
    cleanedToken = (
        _stripThinkingTags(_stripToolCallJson(tokenBuffer)) if tokenBuffer.strip() else ""
    )

    if cleanedToken.strip():
        finalText = cleanedToken.strip()
    else:
        finalText = await _getFallbackMessage(graph, config)

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
            )
        except Exception:
            messageHtml = f'<div class="ai-message">{finalText}</div>'
        yield ServerSentEvent(data=messageHtml, event=SseEvent.MESSAGE)
