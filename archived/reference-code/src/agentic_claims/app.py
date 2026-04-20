"""Chainlit app entry point for Agentic Expense Claims.

Architecture: Progressive streaming with cl.Step thinking panel.
- cl.Step appears immediately with "Processing..." status
- Step name updates in real-time as tools execute
- Type A reasoning (agent text before tool calls) captured
- Type B reasoning (QwQ reasoning_content tokens) captured when available
- Final step shows elapsed time, tool count, and markdown summary
- Final response sent as a separate cl.Message below the step
"""

import base64
import json
import logging
import re
import time
import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage
from agentic_claims.core.logging import setupLogging

logger = logging.getLogger(__name__)

REPLAY_DELAY_MS = 8

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


def _buildThinkingMarkdown(thinkingEntries: list) -> str:
    """Build a markdown summary of thinking entries for the cl.Step output."""
    lines = []
    for entry in thinkingEntries:
        if entry["type"] in ("reasoning", "reasoning_b"):
            lines.append(entry["content"])
        elif entry["type"] == "tool":
            summary = _summarizeToolOutput(entry["name"], entry["output"])
            tcElapsed = _formatElapsed(entry["elapsed"])
            lines.append(f"**{entry['name']}** _({tcElapsed})_\n{summary}")
    return "\n\n".join(lines)


@cl.on_chat_start
async def onChatStart():
    """Initialize chat session with graph and checkpointer."""
    setupLogging()

    graph, checkpointerCtx = await getCompiledGraph()

    cl.user_session.set("graph", graph)
    cl.user_session.set("checkpointer_ctx", checkpointerCtx)

    threadId = str(uuid.uuid4())
    cl.user_session.set("thread_id", threadId)

    claimId = str(uuid.uuid4())
    cl.user_session.set("claim_id", claimId)

    logger.info(
        f"Chat session started - thread_id: {threadId}, claim_id: {claimId}"
    )

    await cl.Message(
        content="Welcome! I'm your expense claims assistant. "
        "Please upload a receipt image to get started."
    ).send()


@cl.on_message
async def onMessage(message: cl.Message):
    """Handle incoming messages with progressive streaming architecture.

    Flow:
    1. Create cl.Step with "Processing..." immediately
    2. Buffer streaming events, capturing Type A+B reasoning and tool calls
    3. Update step name in real-time as tools execute
    4. Set step output to markdown summary when streaming completes
    5. Send final response as a separate cl.Message below the step
    """
    graph = cl.user_session.get("graph")
    threadId = cl.user_session.get("thread_id")
    claimId = cl.user_session.get("claim_id")

    if not graph or not threadId or not claimId:
        await cl.Message(content="Error: Session not initialized properly").send()
        return

    logger.info(
        f"Message received - content_length: {len(message.content)}, "
        f"has_elements: {bool(message.elements)}"
    )

    # Extract image attachment if present
    imageB64 = None
    if message.elements:
        for element in message.elements:
            if hasattr(element, "mime") and element.mime and element.mime.startswith("image/"):
                if hasattr(element, "path") and element.path:
                    with open(element.path, "rb") as f:
                        imageBytes = f.read()
                elif hasattr(element, "content") and element.content:
                    imageBytes = (
                        element.content
                        if isinstance(element.content, bytes)
                        else element.content.encode()
                    )
                else:
                    continue
                imageB64 = base64.b64encode(imageBytes).decode("utf-8")
                logger.info(f"Image uploaded - size: {len(imageBytes)} bytes")
                break

    # Build graph input
    if imageB64:
        storeImage(claimId, imageB64)
        userText = message.content.strip()
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
        humanMsg = HumanMessage(content=message.content)

    graphInput = {
        "claimId": claimId,
        "status": "draft",
        "messages": [humanMsg],
    }

    # ── Stream events, capture reasoning (Type A+B) and tool calls ──
    thinkingEntries = []
    tokenBuffer = ""
    reasoningBuffer = ""
    finalResponse = None
    toolStartTimes = {}
    pendingToolCalls = 0
    eventCount = 0
    turnStartTime = time.time()

    # Step always shows immediately with "Analyzing..." (Gemini-style thinking indicator)
    async with cl.Step(name="Analyzing...", type="tool") as step:
        try:
            async for event in graph.astream_events(
                graphInput,
                config={"configurable": {"thread_id": threadId}},
                version="v2",
            ):
                eventCount += 1
                eventKind = event.get("event")

                if eventKind == "on_chat_model_stream":
                    if pendingToolCalls > 0:
                        continue

                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        tokenBuffer += chunk.content

                    if chunk:
                        reasoning = None
                        if hasattr(chunk, "additional_kwargs"):
                            reasoning = chunk.additional_kwargs.get("reasoning_content") or chunk.additional_kwargs.get("reasoning")
                        if not reasoning and hasattr(chunk, "response_metadata"):
                            reasoning = chunk.response_metadata.get("reasoning_content") or chunk.response_metadata.get("reasoning")
                        if reasoning:
                            reasoningBuffer += str(reasoning)
                            logger.debug(f"Type B reasoning captured: {len(str(reasoning))} chars")

                elif eventKind == "on_chat_model_end":
                    if pendingToolCalls > 0:
                        tokenBuffer = ""
                        reasoningBuffer = ""
                        continue

                    output = event.get("data", {}).get("output")
                    hasToolCalls = (
                        output
                        and hasattr(output, "tool_calls")
                        and output.tool_calls
                    )

                    if hasToolCalls:
                        cleanedBuffer = _stripToolCallJson(tokenBuffer.strip())
                        if cleanedBuffer:
                            thinkingEntries.append({
                                "type": "reasoning",
                                "content": cleanedBuffer,
                            })
                            logger.debug(f"Type A reasoning captured: {len(cleanedBuffer)} chars")

                        if reasoningBuffer.strip():
                            thinkingEntries.append({
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            })
                            logger.debug(f"Type B reasoning captured at intermediate: {len(reasoningBuffer.strip())} chars")

                        tokenBuffer = ""
                        reasoningBuffer = ""
                    else:
                        if reasoningBuffer.strip():
                            thinkingEntries.append({
                                "type": "reasoning_b",
                                "content": reasoningBuffer.strip(),
                            })
                            logger.debug(f"Type B reasoning captured at final: {len(reasoningBuffer.strip())} chars")

                        finalResponse = _stripToolCallJson(tokenBuffer)
                        tokenBuffer = ""
                        reasoningBuffer = ""

                    logger.info(
                        f"LLM generation ended - intermediate: {hasToolCalls}, "
                        f"pending_tools: {pendingToolCalls}, "
                        f"buffer_length: {len(finalResponse or tokenBuffer)}"
                    )

                elif eventKind == "on_tool_start":
                    toolName = event.get("name", "unknown")
                    toolStartTimes[toolName] = time.time()
                    pendingToolCalls += 1

                    # Show tool-specific label during execution
                    step.name = TOOL_LABELS.get(toolName, f"Running {toolName}...")
                    await step.update()

                    logger.info(
                        f"Tool call started - name: {toolName}, "
                        f"pending: {pendingToolCalls}"
                    )

                elif eventKind == "on_tool_end":
                    toolName = event.get("name", "unknown")
                    toolOutput = event.get("data", {}).get("output", "")
                    startTime = toolStartTimes.pop(toolName, None)
                    elapsed = time.time() - startTime if startTime else 0

                    thinkingEntries.append({
                        "type": "tool",
                        "name": toolName,
                        "elapsed": elapsed,
                        "output": toolOutput,
                    })

                    pendingToolCalls = max(0, pendingToolCalls - 1)

                    # Return to "Analyzing..." when all tools complete (model thinking again)
                    if pendingToolCalls == 0:
                        step.name = "Analyzing..."
                        await step.update()

                    logger.info(
                        f"Tool call completed - name: {toolName}, "
                        f"elapsed: {elapsed:.2f}s, pending: {pendingToolCalls}"
                    )

        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
            step.name = "Error"
            step.output = "An error occurred during processing."

        totalElapsed = time.time() - turnStartTime
        toolCount = sum(1 for e in thinkingEntries if e["type"] == "tool")
        toolLabel = "tool" if toolCount == 1 else "tools"

        logger.info(
            f"Streaming completed - events: {eventCount}, "
            f"thinking_entries: {len(thinkingEntries)}, "
            f"reasoning_entries: {sum(1 for e in thinkingEntries if e['type'] in ('reasoning', 'reasoning_b'))}"
        )

        # Finalize the step with summary (always set output so step renders)
        if thinkingEntries:
            step.name = f"Thought for {_formatElapsed(totalElapsed)} · {toolCount} {toolLabel}"
            step.output = _buildThinkingMarkdown(thinkingEntries)
        else:
            step.name = f"Thought for {_formatElapsed(totalElapsed)}"
            step.output = "Direct response — no tool calls needed."

    # ── Send final response as a separate message (OUTSIDE step context for correct ordering) ──
    if finalResponse and finalResponse.strip():
        finalResponse = _stripThinkingTags(finalResponse)
        await cl.Message(content=finalResponse).send()
        logger.info(f"Final response rendered - length: {len(finalResponse)}")

    else:
        logger.warning(
            f"No final response to render - events: {eventCount}, "
            f"thinking_entries: {len(thinkingEntries)}, extracting from state"
        )
        try:
            finalState = await graph.aget_state(
                config={"configurable": {"thread_id": threadId}}
            )

            # Extract last AI message from state
            messages = finalState.values.get("messages", [])
            fallbackContent = None
            for msg in reversed(messages):
                if (
                    hasattr(msg, "type")
                    and msg.type == "ai"
                    and hasattr(msg, "content")
                    and msg.content
                ):
                    fallbackContent = _stripToolCallJson(str(msg.content))
                    break

            if fallbackContent:
                fallbackContent = _stripThinkingTags(fallbackContent)
                await cl.Message(content=fallbackContent).send()
            elif thinkingEntries:
                await cl.Message(content="I encountered an issue. Please try again.").send()

        except Exception as e:
            logger.error(
                f"Error in fallback message extraction: {e}", exc_info=True
            )


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


@cl.on_chat_end
async def onChatEnd():
    """Clean up checkpointer connection pool when chat ends."""
    checkpointerCtx = cl.user_session.get("checkpointer_ctx")
    if checkpointerCtx:
        await checkpointerCtx.__aexit__(None, None, None)
    logger.info("Chat session ended")
