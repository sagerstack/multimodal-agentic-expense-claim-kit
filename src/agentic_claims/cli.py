"""Headless CLI interface for LangGraph conversation.

This module provides:
1. ConversationRunner: Programmatic interface for testing and automation
2. Interactive CLI: Terminal-based chat interface (python -m agentic_claims.cli)

The CLI bypasses Chainlit and drives the same LangGraph graph used by app.py.
Supports multi-turn conversation, interrupt detection, and image upload from file path.
"""

import asyncio
import base64
import json
import logging
import sys
import uuid

from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agentic_claims.core.graph import getCompiledGraph
from agentic_claims.core.imageStore import storeImage
from agentic_claims.core.logging import setupLogging

logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    """Record of a tool call during a conversation turn."""
    name: str
    output: str


@dataclass
class TurnResult:
    """Result of a single conversation turn."""
    messages: list[str] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    isInterrupted: bool = False
    interruptQuestion: str | None = None
    interruptData: dict | None = None


class ConversationRunner:
    """Headless LangGraph conversation runner for CLI and testing.

    Drives the same graph as app.py but without Chainlit dependency.
    Supports multi-turn conversation.

    Usage (programmatic):
        runner = ConversationRunner(envFile=".env.e2e")
        await runner.start()
        turn1 = await runner.send("Process this receipt", imagePath="receipt.jpg")
        if turn1.isInterrupted:
            turn2 = await runner.send("yes")
        await runner.close()

    Usage (interactive):
        python -m agentic_claims.cli
    """

    def __init__(self, envFile: str = ".env.local"):
        """Initialize runner with settings from specified env file.

        Args:
            envFile: Path to environment file for Settings
        """
        # Load env file into os.environ so all getSettings() calls use these values
        # (env vars take priority over env files in pydantic-settings)
        import os
        from dotenv import load_dotenv
        load_dotenv(envFile, override=True)
        from agentic_claims.core.config import Settings
        self._settings = Settings(_env_file=envFile)

        self.graph = None
        self._checkpointerCtx = None
        self.threadId = str(uuid.uuid4())
        self.claimId = str(uuid.uuid4())
        self._messageCount = 0
        self._awaitingClarification = False

    async def start(self) -> str:
        """Initialize graph with Postgres checkpointer.

        Returns:
            Welcome message string
        """
        setupLogging()
        self.graph, self._checkpointerCtx = await getCompiledGraph()
        logger.info(
            f"CLI session started - thread_id: {self.threadId}, claim_id: {self.claimId}"
        )
        return "Welcome! I'm your expense claims assistant. Upload a receipt image to get started."

    async def send(self, text: str, imagePath: str | None = None) -> TurnResult:
        """Send a message to the agent and get the response.

        Args:
            text: User message text
            imagePath: Optional path to receipt image file

        Returns:
            TurnResult with messages, tool steps, and interrupt state
        """
        if not self.graph:
            raise RuntimeError("Call start() before send()")

        config = {"configurable": {"thread_id": self.threadId}}

        # Handle image upload
        if imagePath:
            imagePath = str(Path(imagePath).resolve())
            with open(imagePath, "rb") as f:
                imageB64 = base64.b64encode(f.read()).decode("utf-8")
            storeImage(self.claimId, imageB64)
            logger.info(f"Image loaded from {imagePath}")

            userText = text.strip()
            if userText:
                humanMsg = HumanMessage(
                    content=(
                        f'User says: "{userText}"\n\n'
                        f"I've also uploaded a receipt image for claim {self.claimId}. "
                        f"Please process it using extractReceiptFields."
                    )
                )
            else:
                humanMsg = HumanMessage(
                    content=(
                        f"I've uploaded a receipt image for claim {self.claimId}. "
                        f"Please process it using extractReceiptFields. "
                        f"No expense description was provided."
                    )
                )

        # Build invoke input
        if self._awaitingClarification:
            invokeInput = Command(
                resume={
                    "action": "correct" if "correct" in text.lower() else "confirm",
                    "corrected_data": text,
                    "response": text,
                }
            )
            self._awaitingClarification = False
            logger.info(f"Resuming from interrupt with: {text[:100]}")
        else:
            if not imagePath:
                humanMsg = HumanMessage(content=text)
            invokeInput = {
                "claimId": self.claimId,
                "status": "draft",
                "messages": [humanMsg],
            }

        # Invoke graph
        logger.info("Graph invoke started")
        result = await self.graph.ainvoke(invokeInput, config=config)
        logger.info("Graph invoke completed")

        # Extract new messages from result
        turn = TurnResult()

        if isinstance(result, dict) and "messages" in result:
            allMessages = result["messages"]
            newMessages = allMessages[self._messageCount:]
            self._messageCount = len(allMessages)

            for msg in newMessages:
                if hasattr(msg, "type") and msg.type == "ai":
                    # Capture tool calls as StepRecords
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        for tc in msg.tool_calls:
                            turn.steps.append(StepRecord(
                                name=tc.get("name", "unknown"),
                                output="",  # Output comes from ToolMessage
                            ))
                    # Capture user-facing content
                    if hasattr(msg, "content") and msg.content:
                        turn.messages.append(msg.content)

                elif hasattr(msg, "type") and msg.type == "tool":
                    # Match tool output to most recent StepRecord with empty output
                    toolName = getattr(msg, "name", "unknown")
                    toolContent = str(msg.content)[:500] if hasattr(msg, "content") else ""
                    for step in reversed(turn.steps):
                        if step.name == toolName and not step.output:
                            step.output = toolContent
                            break

        # Check for interrupt
        finalState = await self.graph.aget_state(config=config)
        if finalState.next:
            for task in finalState.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    payload = task.interrupts[0].value
                    turn.isInterrupted = True
                    turn.interruptQuestion = payload.get("question", "Please confirm or correct:")
                    turn.interruptData = payload.get("data", {})
                    self._awaitingClarification = True
                    logger.info(f"Interrupt detected: {turn.interruptQuestion[:100]}")
                    break

        logger.info(
            f"Turn complete - messages: {len(turn.messages)}, "
            f"steps: {len(turn.steps)}, interrupted: {turn.isInterrupted}"
        )
        return turn

    async def close(self):
        """Cleanup graph checkpointer connection pool."""
        if self._checkpointerCtx:
            await self._checkpointerCtx.__aexit__(None, None, None)
            logger.info("CLI session closed")

    @property
    def allToolCalls(self) -> list[str]:
        """Get all tool call names from the conversation so far (for assertions)."""
        # Re-read from graph state to get complete history
        return []  # Populated by test via TurnResult.steps


async def _interactiveLoop():
    """Run interactive CLI chat loop."""
    print("=" * 60)
    print("  Agentic Expense Claims - CLI Interface")
    print("=" * 60)
    print()
    print("Commands:")
    print("  upload:<path>  - Upload a receipt image")
    print("  quit           - Exit the CLI")
    print()

    runner = ConversationRunner(envFile=".env.e2e")
    welcome = await runner.start()
    print(f"Agent: {welcome}")
    print()

    try:
        while True:
            try:
                userInput = input("You: ").strip()
            except EOFError:
                break

            if not userInput:
                continue
            if userInput.lower() == "quit":
                break

            # Parse upload command
            imagePath = None
            text = userInput
            if userInput.lower().startswith("upload:"):
                imagePath = userInput[7:].strip()
                text = input("Description (or press Enter to skip): ").strip()

            turn = await runner.send(text or "", imagePath=imagePath)

            # Print tool calls
            for step in turn.steps:
                print(f"  [Tool: {step.name}]")

            # Print messages
            for msg in turn.messages:
                print(f"Agent: {msg}")
                print()

            # Print interrupt
            if turn.isInterrupted:
                if turn.interruptQuestion:
                    print(f"Agent: {turn.interruptQuestion}")
                if turn.interruptData:
                    print(f"  {json.dumps(turn.interruptData, indent=2)}")
                print()

    finally:
        await runner.close()
        print("Session closed.")


if __name__ == "__main__":
    asyncio.run(_interactiveLoop())
