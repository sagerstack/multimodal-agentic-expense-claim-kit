"""Debug node — sends a trivial hello world to the same LLM to isolate SDK timing issues."""

import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_claims.agents.shared.llmFactory import buildAgentLlm
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


async def debugLlmNode(state: ClaimState) -> dict:
    """Send a trivial prompt to the same model and log timing."""
    settings = getSettings()
    modelName = settings.openrouter_model_llm
    llm = buildAgentLlm(settings, temperature=0.1)

    llmMessages = [
        SystemMessage(content="You are a helpful assistant. Reply in one sentence."),
        HumanMessage(content="Say hello world.\n/no_think"),
    ]

    sdkParams = llm._default_params
    logger.info(
        "debugLlmNode LLM request",
        extra={
            "claimId": state.get("claimId", "unknown"),
            "model": modelName,
            "sdkParams": {k: str(v)[:200] for k, v in sdkParams.items()},
        },
    )
    startTime = time.time()

    try:
        response = await llm.ainvoke(llmMessages)
        elapsed = round(time.time() - startTime, 2)
        logger.info(
            "debugLlmNode LLM response",
            extra={
                "claimId": state.get("claimId", "unknown"),
                "model": modelName,
                "elapsedSeconds": elapsed,
                "rawResponse": response.content[:500] if response.content else None,
            },
        )
    except Exception as e:
        elapsed = round(time.time() - startTime, 2)
        logger.error(
            "debugLlmNode LLM failed",
            extra={
                "claimId": state.get("claimId", "unknown"),
                "elapsedSeconds": elapsed,
                "error": str(e)[:500],
            },
        )

    return {}
