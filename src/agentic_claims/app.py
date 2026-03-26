"""Chainlit app entry point for Agentic Expense Claims."""

import base64
import json
import logging
import time
import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage
from agentic_claims.core.logging import setupLogging

# Initialize module logger
logger = logging.getLogger(__name__)


@cl.on_chat_start
async def onChatStart():
    """Initialize chat session with graph and checkpointer."""
    # Setup logging on app startup
    setupLogging()

    # Create compiled graph with Postgres checkpointer
    graph, checkpointerCtx = await getCompiledGraph()

    # Store in session for use in message handler
    cl.user_session.set("graph", graph)
    cl.user_session.set("checkpointer_ctx", checkpointerCtx)

    # Generate unique thread ID for this conversation
    threadId = str(uuid.uuid4())
    cl.user_session.set("thread_id", threadId)

    # Generate unique claim ID for this claim submission session
    claimId = str(uuid.uuid4())
    cl.user_session.set("claim_id", claimId)

    # Initialize conversation state
    cl.user_session.set("awaiting_clarification", False)

    logger.info(
        f"Chat session started - thread_id: {threadId}, claim_id: {claimId}"
    )

    await cl.Message(
        content="Welcome! I'm your expense claims assistant. Please upload a receipt image to get started."
    ).send()


@cl.on_message
async def onMessage(message: cl.Message):
    """Handle incoming messages with streaming event loop and per-tool Steps."""
    # Retrieve session context
    graph = cl.user_session.get("graph")
    threadId = cl.user_session.get("thread_id")
    claimId = cl.user_session.get("claim_id")
    awaitingClarification = cl.user_session.get("awaiting_clarification", False)

    if not graph or not threadId or not claimId:
        await cl.Message(content="Error: Session not initialized properly").send()
        return

    logger.info(
        f"Message received - content_length: {len(message.content)}, "
        f"has_elements: {bool(message.elements)}, "
        f"awaiting_clarification: {awaitingClarification}"
    )

    # Step 1: Check for image attachments
    imageB64 = None
    if message.elements:
        for element in message.elements:
            if hasattr(element, "mime") and element.mime and element.mime.startswith("image/"):
                # Read image file content
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
                await cl.Message(content="Receipt image received. Processing...").send()
                logger.info(f"Image uploaded - size: {len(imageBytes)} bytes")
                break

    logger.info(f"Graph streaming started - claimId={claimId}, status=draft")

    # Step 2: Build input for graph
    if awaitingClarification:
        # User's message is the response to the clarification request
        inputOrCommand = Command(
            resume={
                "action": "correct" if "correct" in message.content.lower() else "confirm",
                "corrected_data": message.content,
                "response": message.content,
            }
        )
        cl.user_session.set("awaiting_clarification", False)
    else:
        # Build human message (text-only; image stored separately)
        if imageB64:
            storeImage(claimId, imageB64)
            userText = message.content.strip()
            if userText:
                humanMsg = HumanMessage(
                    content=f'User says: "{userText}"\n\nI\'ve also uploaded a receipt image for claim {claimId}. Please process it using extractReceiptFields.'
                )
            else:
                humanMsg = HumanMessage(
                    content=f"I've uploaded a receipt image for claim {claimId}. Please process it using extractReceiptFields. No expense description was provided."
                )
        else:
            humanMsg = HumanMessage(content=message.content)

        inputOrCommand = {
            "claimId": claimId,
            "status": "draft",
            "messages": [humanMsg],
        }

    # Step 3: Stream events and create per-tool Steps
    currentStreamMsg = None  # Current message being streamed
    currentStep = None       # Current Step element for tool call
    toolStartTime = None     # Track tool execution time
    eventCount = 0

    try:
        async for event in graph.astream_events(
            inputOrCommand,
            config={"configurable": {"thread_id": threadId}},
            version="v2",
        ):
            eventCount += 1
            eventKind = event.get("event")

            # on_chat_model_stream: Stream tokens to main chat
            if eventKind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    # Finalize any open Step before streaming LLM content
                    if currentStep is not None:
                        elapsed = time.time() - toolStartTime
                        if elapsed >= 60:
                            minutes = int(elapsed // 60)
                            seconds = int(elapsed % 60)
                            currentStep.name = f"Thought for {minutes} min {seconds} seconds"
                        else:
                            currentStep.name = f"Thought for {int(elapsed)} seconds"
                        await currentStep.send()
                        currentStep = None
                        toolStartTime = None

                    # Create or append to current streamed message
                    if currentStreamMsg is None:
                        currentStreamMsg = cl.Message(content="")
                        await currentStreamMsg.send()

                    # Stream token
                    await currentStreamMsg.stream_token(chunk.content)

            # on_chat_model_end: Finalize streamed message
            elif eventKind == "on_chat_model_end":
                if currentStreamMsg is not None:
                    await currentStreamMsg.update()
                    logger.info(f"Finalized streamed message - length: {len(currentStreamMsg.content)}")
                    currentStreamMsg = None

            # on_tool_start: Open a "Thinking" Step
            elif eventKind == "on_tool_start":
                # Finalize any pending streamed message
                if currentStreamMsg is not None:
                    await currentStreamMsg.update()
                    currentStreamMsg = None

                toolName = event.get("name", "unknown")
                logger.info(f"Tool call started - name: {toolName}")

                # Open Step with "Thinking" name
                currentStep = cl.Step(name="Thinking", type="tool")
                await currentStep.send()
                toolStartTime = time.time()

            # on_tool_end: Close Step with elapsed time
            elif eventKind == "on_tool_end":
                if currentStep is not None and toolStartTime is not None:
                    elapsed = time.time() - toolStartTime
                    toolName = event.get("name", "unknown")

                    # Format elapsed time
                    if elapsed >= 60:
                        minutes = int(elapsed // 60)
                        seconds = int(elapsed % 60)
                        currentStep.name = f"Thought for {minutes} min {seconds} seconds"
                    else:
                        currentStep.name = f"Thought for {int(elapsed)} seconds"

                    logger.info(f"Tool call completed - name: {toolName}, elapsed: {elapsed:.2f}s")
                    await currentStep.send()
                    currentStep = None
                    toolStartTime = None

    except Exception as e:
        logger.error(f"Error during streaming: {e}", exc_info=True)
        await cl.Message(content=f"Error: {str(e)}").send()
        return

    logger.info(f"Streaming completed - events_processed: {eventCount}")

    # Step 4: Check for interrupt via aget_state (streaming doesn't expose __interrupt__)
    try:
        finalState = await graph.aget_state(config={"configurable": {"thread_id": threadId}})

        # Check if next node is empty (indicating interrupt)
        if not finalState.next and finalState.tasks:
            # Interrupt detected - extract from tasks
            for task in finalState.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    interruptPayload = task.interrupts[0].value
                    question = interruptPayload.get("question", "Please confirm or correct the following:")
                    data = interruptPayload.get("data", {})

                    logger.info("Interrupt detected via aget_state - clarification requested")

                    await cl.Message(content=question).send()
                    if data:
                        await cl.Message(content=f"```json\n{json.dumps(data, indent=2)}\n```").send()

                    cl.user_session.set("awaiting_clarification", True)
                    return

        # Fallback: If no events captured (nested graph issue), extract from state
        if eventCount == 0:
            logger.warning("No streaming events captured - using fallback message extraction")
            messages = finalState.values.get("messages", [])
            if messages:
                lastMsg = messages[-1]
                if hasattr(lastMsg, "type") and lastMsg.type == "ai" and hasattr(lastMsg, "content") and lastMsg.content:
                    await cl.Message(content=lastMsg.content).send()

    except Exception as e:
        logger.error(f"Error checking state: {e}", exc_info=True)


@cl.on_chat_end
async def onChatEnd():
    """Clean up checkpointer connection pool when chat ends."""
    checkpointerCtx = cl.user_session.get("checkpointer_ctx")
    if checkpointerCtx:
        await checkpointerCtx.__aexit__(None, None, None)
    logger.info("Chat session ended")
