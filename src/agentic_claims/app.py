"""Chainlit app entry point for Agentic Expense Claims."""

import uuid

import chainlit as cl
from langchain_core.messages import HumanMessage

from agentic_claims.core.graph import getCompiledGraph


@cl.on_chat_start
async def onChatStart():
    """Initialize chat session with graph and checkpointer."""
    # Create compiled graph with Postgres checkpointer
    graph, checkpointer = await getCompiledGraph()

    # Store in session for use in message handler
    cl.user_session.set("graph", graph)
    cl.user_session.set("checkpointer", checkpointer)

    # Generate unique thread ID for this conversation
    threadId = str(uuid.uuid4())
    cl.user_session.set("thread_id", threadId)

    await cl.Message(
        content="Agentic Expense Claims system ready. Upload a receipt to get started."
    ).send()


@cl.on_message
async def onMessage(message: cl.Message):
    """Handle incoming messages by invoking the LangGraph."""
    # Retrieve graph and thread ID from session
    graph = cl.user_session.get("graph")
    threadId = cl.user_session.get("thread_id")

    if not graph or not threadId:
        await cl.Message(content="Error: Session not initialized properly").send()
        return

    # Create initial claim state
    initialState = {
        "claimId": str(uuid.uuid4()),
        "status": "draft",
        "messages": [HumanMessage(content=message.content)],
    }

    # Invoke graph with checkpointer config
    result = await graph.ainvoke(
        initialState, config={"configurable": {"thread_id": threadId}}
    )

    # Extract and send all agent messages
    # Skip the first message (user's HumanMessage) and send the rest
    agentMessages = result["messages"][1:]  # Skip HumanMessage

    for msg in agentMessages:
        await cl.Message(content=msg.content).send()


@cl.on_chat_end
async def onChatEnd():
    """Clean up checkpointer connection when chat ends."""
    checkpointer = cl.user_session.get("checkpointer")
    if checkpointer:
        # Close the checkpointer connection pool
        await checkpointer.conn.__aexit__(None, None, None)
