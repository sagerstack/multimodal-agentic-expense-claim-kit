"""Chainlit app entry point for Agentic Expense Claims.

Architecture: Buffer-first with HTML thinking panels.
- All streaming events are buffered in memory first (Chainlit shows loading)
- Thinking panel rendered as HTML <details> inside the response Message
- Guarantees correct ordering: thinking panel above, response below
- No thinking panel for direct responses (no tool usage)
"""

import asyncio
import base64
import json
import logging
import time
import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage
from agentic_claims.core.logging import setupLogging

logger = logging.getLogger(__name__)

REPLAY_DELAY_MS = 8


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


def _buildThinkingHtml(toolCalls: list, totalElapsed: float) -> str:
    """Build an HTML <details> block for the thinking panel."""
    elapsed = _formatElapsed(totalElapsed)
    toolCount = len(toolCalls)
    toolLabel = "tool" if toolCount == 1 else "tools"

    toolLines = []
    for tc in toolCalls:
        summary = _summarizeToolOutput(tc["name"], tc["output"])
        tcElapsed = _formatElapsed(tc["elapsed"])
        toolLines.append(
            f'<div class="thinking-tool">'
            f'<b>{tc["name"]}</b> '
            f'<span class="thinking-elapsed">({tcElapsed})</span>'
            f'<div class="thinking-summary">{summary}</div>'
            f'</div>'
        )

    toolsHtml = "\n".join(toolLines)

    return (
        f'<details class="thinking-panel">\n'
        f'<summary>Thought for {elapsed} · {toolCount} {toolLabel}</summary>\n'
        f'{toolsHtml}\n'
        f'</details>\n\n'
    )


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
    """Handle incoming messages with buffer-first streaming architecture.

    Flow:
    1. Buffer ALL streaming events in memory (Chainlit shows loading indicator)
    2. If tool calls occurred: render thinking Step(s) with tool summaries
    3. Replay final response as a streamed chat Message
    4. Skip thinking panel entirely for direct responses (no tools)
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

    # ── Phase 1: Buffer ALL streaming events ──
    # Chainlit shows its built-in loading indicator while we process
    tokenBuffer = ""
    toolCalls = []
    finalResponse = None
    currentToolName = None
    currentToolStartTime = None
    pendingToolCalls = 0
    eventCount = 0
    turnStartTime = time.time()

    try:
        async for event in graph.astream_events(
            graphInput,
            config={"configurable": {"thread_id": threadId}},
            version="v2",
        ):
            eventCount += 1
            eventKind = event.get("event")

            if eventKind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    tokenBuffer += chunk.content

            elif eventKind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                hasToolCalls = (
                    output
                    and hasattr(output, "tool_calls")
                    and output.tool_calls
                )

                if hasToolCalls:
                    # About to call tools — discard narration tokens
                    tokenBuffer = ""
                else:
                    # Candidate final response — overwrite (last one wins)
                    finalResponse = tokenBuffer
                    tokenBuffer = ""

                logger.info(
                    f"LLM generation ended - intermediate: {hasToolCalls}, "
                    f"pending_tools: {pendingToolCalls}, "
                    f"buffer_length: {len(finalResponse or tokenBuffer)}"
                )

            elif eventKind == "on_tool_start":
                currentToolName = event.get("name", "unknown")
                currentToolStartTime = time.time()
                pendingToolCalls += 1
                logger.info(
                    f"Tool call started - name: {currentToolName}, "
                    f"pending: {pendingToolCalls}"
                )

            elif eventKind == "on_tool_end":
                toolName = event.get("name", "unknown")
                toolOutput = event.get("data", {}).get("output", "")
                elapsed = (
                    time.time() - currentToolStartTime
                    if currentToolStartTime
                    else 0
                )

                toolCalls.append({
                    "name": toolName,
                    "elapsed": elapsed,
                    "output": toolOutput,
                })

                pendingToolCalls = max(0, pendingToolCalls - 1)
                logger.info(
                    f"Tool call completed - name: {toolName}, "
                    f"elapsed: {elapsed:.2f}s, pending: {pendingToolCalls}"
                )
                currentToolName = None
                currentToolStartTime = None

    except Exception as e:
        logger.error(f"Error during streaming: {e}", exc_info=True)
        await cl.Message(
            content="I ran into an issue processing your request. Please try again."
        ).send()
        return

    totalElapsed = time.time() - turnStartTime
    logger.info(
        f"Streaming completed - events: {eventCount}, tools: {len(toolCalls)}"
    )

    # ── Phase 2: Render response (with thinking panel if tools were called) ──
    if finalResponse and finalResponse.strip():
        if toolCalls:
            # Single message: HTML thinking panel + streamed response below
            thinkingHtml = _buildThinkingHtml(toolCalls, totalElapsed)
            responseMsg = cl.Message(content=thinkingHtml)
        else:
            # Direct response — no thinking panel
            responseMsg = cl.Message(content="")

        await responseMsg.send()

        for token in finalResponse:
            await responseMsg.stream_token(token)
            await asyncio.sleep(REPLAY_DELAY_MS / 1000)

        await responseMsg.update()
        logger.info(f"Final response replayed - length: {len(finalResponse)}")

    else:
        # Fallback: events captured but no final text response
        # This happens when: tool returns error and LLM produces no text,
        # nested graph doesn't emit expected events, or interrupt occurred
        logger.warning(
            f"No final response to render - events: {eventCount}, "
            f"tools: {len(toolCalls)}, extracting from state"
        )
        try:
            finalState = await graph.aget_state(
                config={"configurable": {"thread_id": threadId}}
            )

            # Check for interrupt (askHuman)
            interruptTasks = finalState.tasks if hasattr(finalState, "tasks") else []
            hasInterrupt = any(
                hasattr(t, "interrupts") and t.interrupts for t in interruptTasks
            )

            if hasInterrupt:
                # Extract interrupt value (the question to ask the user)
                for task in interruptTasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interruptValue = task.interrupts[0].value
                        content = ""
                        if toolCalls:
                            content = _buildThinkingHtml(toolCalls, totalElapsed)
                        content += str(interruptValue)
                        await cl.Message(content=content).send()
                        return

            # No interrupt — extract last AI message from state
            messages = finalState.values.get("messages", [])
            fallbackContent = None
            for msg in reversed(messages):
                if (
                    hasattr(msg, "type")
                    and msg.type == "ai"
                    and hasattr(msg, "content")
                    and msg.content
                ):
                    fallbackContent = msg.content
                    break

            if fallbackContent:
                content = ""
                if toolCalls:
                    content = _buildThinkingHtml(toolCalls, totalElapsed)
                content += fallbackContent
                responseMsg = cl.Message(content=content)
                await responseMsg.send()
            elif toolCalls:
                # Show thinking panel even without text (so user sees tool errors)
                thinkingHtml = _buildThinkingHtml(toolCalls, totalElapsed)
                await cl.Message(
                    content=thinkingHtml
                    + "I encountered an issue. Please try again."
                ).send()

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
