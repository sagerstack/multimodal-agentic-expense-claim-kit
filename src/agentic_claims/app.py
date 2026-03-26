"""Chainlit app entry point for Agentic Expense Claims.

Architecture: Thinking-first streaming with parent wrapper Steps.
- All intermediate LLM reasoning + tool calls render inside nested Thinking Steps
- Only the final LLM response (no tool_calls) replays as a chat Message
- Parent wrapper Step keeps the busy indicator active throughout processing
"""

import asyncio
import base64
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
        return f"Thought for {minutes} min {seconds} seconds"
    return f"Thought for {int(elapsed)} seconds"


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
    """Handle incoming messages with thinking-first streaming architecture.

    Flow per invocation:
    1. Open a parent "Processing" Step (keeps spinner alive)
    2. For each ReAct cycle: buffer LLM tokens, classify on on_chat_model_end
       - If tool_calls present: intermediate thinking -> nested Thinking Step
       - If no tool_calls: final response -> buffer for replay
    3. Close parent Step
    4. Replay final response via stream_token() for typing effect
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

    # Streaming state
    tokenBuffer = ""
    thinkingLog = []
    finalResponse = None
    currentToolName = None
    currentToolStep = None
    toolStartTime = None
    eventCount = 0
    turnStartTime = time.time()

    try:
        # Parent wrapper Step keeps spinner alive for the entire turn
        parentStep = cl.Step(name="Processing", type="tool")
        parentStep.input = "Processing your request"
        await parentStep.send()

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
                    # Intermediate thinking — capture narration in thinking log
                    if tokenBuffer.strip():
                        thinkingLog.append(f"**Reasoning:** {tokenBuffer.strip()}")
                    tokenBuffer = ""
                else:
                    # Final response — store for replay after parent Step closes
                    finalResponse = tokenBuffer
                    tokenBuffer = ""

                logger.info(
                    f"LLM generation ended - intermediate: {hasToolCalls}, "
                    f"buffer_length: {len(finalResponse or tokenBuffer)}"
                )

            elif eventKind == "on_tool_start":
                toolName = event.get("name", "unknown")
                currentToolName = toolName
                toolStartTime = time.time()

                # Open a nested Thinking Step inside the parent
                currentToolStep = cl.Step(
                    name="Thinking",
                    type="tool",
                    parent_id=parentStep.id,
                    show_input=True,
                )
                currentToolStep.input = f"Calling {toolName}"
                await currentToolStep.send()

                thinkingLog.append(f"Calling {toolName}...")
                parentStep.output = "\n\n".join(thinkingLog)
                await parentStep.update()

                logger.info(f"Tool call started - name: {toolName}")

            elif eventKind == "on_tool_end":
                toolName = event.get("name", "unknown")
                toolOutput = event.get("data", {}).get("output", "")

                if currentToolStep and toolStartTime:
                    elapsed = time.time() - toolStartTime
                    currentToolStep.name = _formatElapsed(elapsed)

                    # Build tool result summary for the Thinking panel
                    outputSummary = _summarizeToolOutput(toolName, toolOutput)
                    currentToolStep.output = outputSummary

                    await currentToolStep.update()
                    logger.info(f"Tool call completed - name: {toolName}, elapsed: {elapsed:.2f}s")

                # Update thinking log with completion
                if thinkingLog and thinkingLog[-1].startswith(f"Calling {toolName}"):
                    thinkingLog[-1] = f"Completed {toolName}"
                else:
                    thinkingLog.append(f"Completed {toolName}")

                parentStep.output = "\n\n".join(thinkingLog)
                await parentStep.update()

                currentToolStep = None
                currentToolName = None
                toolStartTime = None

        # Close the parent wrapper Step
        totalElapsed = time.time() - turnStartTime
        parentStep.name = _formatElapsed(totalElapsed)
        parentStep.output = "\n\n".join(thinkingLog) if thinkingLog else "Completed"
        await parentStep.update()

    except Exception as e:
        logger.error(f"Error during streaming: {e}", exc_info=True)
        # Close parent Step on error
        parentStep.name = "Error during processing"
        parentStep.output = str(e)
        await parentStep.update()
        await cl.Message(
            content="I ran into an issue processing your request. Please try again."
        ).send()
        return

    logger.info(f"Streaming completed - events_processed: {eventCount}")

    # Replay final response as a streamed chat message
    if finalResponse and finalResponse.strip():
        responseMsg = cl.Message(content="")
        await responseMsg.send()

        for token in finalResponse:
            await responseMsg.stream_token(token)
            await asyncio.sleep(REPLAY_DELAY_MS / 1000)

        await responseMsg.update()
        logger.info(f"Final response replayed - length: {len(finalResponse)}")

    elif eventCount == 0:
        # Fallback: no streaming events captured (nested graph issue)
        logger.warning("No streaming events captured - using fallback message extraction")
        try:
            finalState = await graph.aget_state(
                config={"configurable": {"thread_id": threadId}}
            )
            messages = finalState.values.get("messages", [])
            if messages:
                lastMsg = messages[-1]
                if (
                    hasattr(lastMsg, "type")
                    and lastMsg.type == "ai"
                    and hasattr(lastMsg, "content")
                    and lastMsg.content
                ):
                    await cl.Message(content=lastMsg.content).send()
        except Exception as e:
            logger.error(f"Error in fallback message extraction: {e}", exc_info=True)


def _summarizeToolOutput(toolName: str, toolOutput) -> str:
    """Create a human-readable summary of a tool's output for the Thinking panel."""
    try:
        if isinstance(toolOutput, str):
            import json
            data = json.loads(toolOutput)
        elif hasattr(toolOutput, "content"):
            import json
            data = json.loads(toolOutput.content) if isinstance(toolOutput.content, str) else toolOutput.content
        else:
            data = toolOutput

        if not isinstance(data, dict):
            return f"Completed {toolName}"

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
