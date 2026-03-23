"""Chainlit app entry point for Agentic Expense Claims."""

import chainlit as cl


@cl.on_chat_start
async def onChatStart():
    """Initialize chat session with welcome message."""
    await cl.Message(
        content="Agentic Expense Claims system ready. Upload a receipt to get started."
    ).send()


@cl.on_message
async def onMessage(message: cl.Message):
    """Handle incoming messages.

    This is a placeholder for Phase 2 LangGraph integration.
    Currently echoes the message content back.
    """
    response = (
        f"Received: {message.content}. "
        f"Graph processing will be connected in the next step."
    )
    await cl.Message(content=response).send()
