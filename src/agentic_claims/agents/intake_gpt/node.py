"""Outer wrapper node for the intake-gpt replacement path."""

from __future__ import annotations

import logging
import time

from langchain_core.runnables import RunnableConfig

from agentic_claims.agents.intake_gpt.graph import buildIntakeGptSubgraph
from agentic_claims.agents.intake_gpt.translators import (
    buildIntakeGptInput,
    mergeIntakeGptResult,
)
from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)
_intakeGptSubgraphSingleton = None


def _getIntakeGptSubgraph():
    """Build and memoize the intake-gpt subgraph."""
    global _intakeGptSubgraphSingleton
    if _intakeGptSubgraphSingleton is None:
        settings = getSettings()
        llm = buildAgentLlm(
            settings,
            temperature=0.1,
            reasoning={"enabled": True, "summary": "concise"},
        )
        _intakeGptSubgraphSingleton = buildIntakeGptSubgraph(llm)
    return _intakeGptSubgraphSingleton


async def intakeGptNode(state: ClaimState, config: RunnableConfig | None = None) -> dict:
    """Invoke the intake-gpt subgraph and translate its result back to ClaimState."""
    nodeStart = time.time()
    claimId = state.get("claimId")
    threadId = state.get("threadId")
    turnIndex = state.get("turnIndex", 0)
    logEvent(
        logger,
        "intake.agent_invoked",
        logCategory="agent",
        agent="intake-gpt",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        messageCount=len(state.get("messages", [])),
        message="intake-gpt node invoking subgraph",
    )
    subgraph = _getIntakeGptSubgraph()
    result = await subgraph.ainvoke(buildIntakeGptInput(state), config=config)
    merged = mergeIntakeGptResult(state, result)
    logEvent(
        logger,
        "intake.completed",
        logCategory="agent",
        agent="intake-gpt",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        elapsedMs=round((time.time() - nodeStart) * 1000),
        stateUpdateKeys=list(merged.keys()),
        message="intake-gpt node completed",
    )
    logEvent(
        logger,
        "intake.turn.end",
        logCategory="agent",
        agent="intake-gpt",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        message="intake-gpt turn end",
    )
    return merged
