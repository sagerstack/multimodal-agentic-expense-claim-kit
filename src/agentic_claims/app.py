"""Chainlit app entry point for Agentic Expense Claims."""

import base64
import json
import logging
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

    # Get current message count from graph state before invoke
    messageCountBefore = 0
    try:
        currentState = await graph.aget_state(config={"configurable": {"thread_id": threadId}})
        messageCountBefore = len(currentState.values.get("messages", []))
        logger.info(f"Current message count before invoke: {messageCountBefore}")
    except Exception as e:
        logger.warning(f"Could not get state message count, assuming 0: {e}")
        messageCountBefore = 0

    # Wrap agent processing in a Chainlit Step for collapsible chain-of-thought
    async with cl.Step(name="Processing Receipt", type="tool") as processingStep:
        processingStep.input = (
            "Extracting receipt fields, validating policy, converting currency" if imageB64
            else "Handling user response"
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

        # Separate messages into CoT entries and user-facing messages
        if isinstance(result, dict) and "messages" in result:
            agentMessages = result["messages"]
            newMessages = agentMessages[messageCountBefore:]  # Only new messages from this turn

            logger.info(f"Processing agent messages - total_count: {len(agentMessages)}, new_count: {len(newMessages)}")

            cotEntries = []
            userFacingMessages = []

            for msg in newMessages:
                if hasattr(msg, "type") and msg.type == "ai":
                    # Check if this is a tool-call-only message (has tool_calls but no content)
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            toolName = tc.get("name", "unknown")
                            toolArgs = json.dumps(tc.get("args", {}))[:200]
                            cotEntries.append(f"**Tool Call:** {toolName}({toolArgs})")

                    if hasattr(msg, "content") and msg.content:
                        # AI message with user-facing content
                        userFacingMessages.append(msg)

                elif hasattr(msg, "type") and msg.type == "tool":
                    # ToolMessage - capture for CoT
                    toolName = getattr(msg, "name", "unknown")
                    toolContent = str(msg.content)[:500] if hasattr(msg, "content") else ""
                    cotEntries.append(f"**Tool Result ({toolName}):** {toolContent}")

            # Write CoT to Step output (visible in collapsed panel)
            if cotEntries:
                processingStep.output = "\n\n".join(cotEntries)
            else:
                processingStep.output = "No intermediate reasoning captured"
        else:
            processingStep.output = "No messages in result"

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

    # Step 6: Send user-facing messages to main chat (AFTER Step context exits)
    messagesSent = 0
    for msg in userFacingMessages:
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
