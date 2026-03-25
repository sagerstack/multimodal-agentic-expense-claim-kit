"""Chainlit app entry point for Agentic Expense Claims."""

import base64
import json
import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage


@cl.on_chat_start
async def onChatStart():
    """Initialize chat session with graph and checkpointer."""
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
                break

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

    # Step 5: Check for interrupt (clarification request from askHuman tool)
    if hasattr(result, "__contains__") and "__interrupt__" in result:
        interruptPayload = result["__interrupt__"][0].value
        question = interruptPayload.get("question", "Please confirm or correct the following:")
        data = interruptPayload.get("data", {})

        await cl.Message(content=question).send()
        if data:
            await cl.Message(content=f"```json\n{json.dumps(data, indent=2)}\n```").send()

        cl.user_session.set("awaiting_clarification", True)
        return

    # Step 6: Send agent response messages
    if isinstance(result, dict) and "messages" in result:
        agentMessages = result["messages"]
        # Find new AI messages (skip existing ones)
        for msg in agentMessages:
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                await cl.Message(content=msg.content).send()


@cl.on_chat_end
async def onChatEnd():
    """Clean up checkpointer connection pool when chat ends."""
    checkpointerCtx = cl.user_session.get("checkpointer_ctx")
    if checkpointerCtx:
        await checkpointerCtx.__aexit__(None, None, None)
