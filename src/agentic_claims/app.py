"""Chainlit app entry point for Agentic Expense Claims."""

import base64
import json
import logging
import sys
import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage

# Initialize module logger
logger = logging.getLogger(__name__)


def setupLogging():
    """Configure structured JSON logging for the application."""
    try:
        # Configure root logger
        rootLogger = logging.getLogger()
        rootLogger.setLevel(logging.INFO)

        # Create console handler with JSON-like format
        consoleHandler = logging.StreamHandler(sys.stdout)
        consoleHandler.setLevel(logging.INFO)

        # Simple structured format (JSON-like but readable)
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
        )
        consoleHandler.setFormatter(formatter)

        # Remove existing handlers to avoid duplicates
        rootLogger.handlers.clear()
        rootLogger.addHandler(consoleHandler)

        logger.info("Structured logging initialized")
    except Exception as e:
        # Fallback to stderr if logging setup fails
        print(f"[ERROR] Failed to setup logging: {e}", file=sys.stderr)


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
        content="Agentic Expense Claims system ready. Upload a receipt to get started."
    ).send()


@cl.on_message
async def onMessage(message: cl.Message):
    """Handle incoming messages with image upload and interrupt support."""
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

    # Wrap agent processing in a Chainlit Step for collapsible chain-of-thought
    async with cl.Step(name="Processing Receipt", type="tool") as processingStep:
        processingStep.input = (
            "Processing receipt image..." if imageB64 else "Handling user response..."
        )

        logger.info(f"Graph invoke started - input_keys: claimId={claimId}, status=draft, messages")

        # Step 2: If resuming from interrupt (clarification)
        if awaitingClarification:
            # User's message is the response to the clarification request
            result = await graph.ainvoke(
                Command(
                    resume={
                        "action": "correct" if "correct" in message.content.lower() else "confirm",
                        "corrected_data": message.content,
                        "response": message.content,
                    }
                ),
                config={"configurable": {"thread_id": threadId}},
            )
            cl.user_session.set("awaiting_clarification", False)
        else:
            # Step 3: Build human message (text-only; image stored separately to avoid context overflow)
            if imageB64:
                storeImage(claimId, imageB64)
                humanMsg = HumanMessage(
                    content=f"I've uploaded a receipt image for claim {claimId}. Please process it using extractReceiptFields."
                )
            else:
                humanMsg = HumanMessage(content=message.content)

            # Step 4: Invoke graph
            inputState = {
                "claimId": claimId,
                "status": "draft",
                "messages": [humanMsg],
            }

            result = await graph.ainvoke(
                inputState, config={"configurable": {"thread_id": threadId}}
            )

        logger.info(
            f"Graph invoke completed - has_interrupt: {hasattr(result, '__contains__') and '__interrupt__' in result}, "
            f"result_type: {type(result).__name__}"
        )

        # Set processing step output
        processingStep.output = (
            "Receipt processing complete" if not (hasattr(result, "__contains__") and "__interrupt__" in result)
            else "Awaiting clarification"
        )

    # Step 5: Check for interrupt (clarification request from askHuman tool)
    if hasattr(result, "__contains__") and "__interrupt__" in result:
        interruptPayload = result["__interrupt__"][0].value
        question = interruptPayload.get("question", "Please confirm or correct the following:")
        data = interruptPayload.get("data", {})

        logger.info("Interrupt detected - clarification requested")

        await cl.Message(content=question).send()
        if data:
            await cl.Message(content=f"```json\n{json.dumps(data, indent=2)}\n```").send()

        cl.user_session.set("awaiting_clarification", True)
        return

    # Step 6: Send agent response messages (filter out ToolMessages and empty AI messages)
    if isinstance(result, dict) and "messages" in result:
        agentMessages = result["messages"]
        logger.info(f"Processing agent messages - total_count: {len(agentMessages)}")

        # Find new AI messages with content (skip ToolMessages, function calls, empty messages)
        messagesSent = 0
        for msg in agentMessages:
            # Only send AI messages with actual content
            if hasattr(msg, "type") and msg.type == "ai" and hasattr(msg, "content") and msg.content:
                # Log first 100 chars of each message
                logContent = msg.content[:100] + ("..." if len(msg.content) > 100 else "")
                logger.info(f"Sending message - preview: {logContent}")

                await cl.Message(content=msg.content).send()
                messagesSent += 1

        logger.info(f"Messages sent to user - count: {messagesSent}")


@cl.on_chat_end
async def onChatEnd():
    """Clean up checkpointer connection pool when chat ends."""
    checkpointerCtx = cl.user_session.get("checkpointer_ctx")
    if checkpointerCtx:
        await checkpointerCtx.__aexit__(None, None, None)
    logger.info("Chat session ended")
