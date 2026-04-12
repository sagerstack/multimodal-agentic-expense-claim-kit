"""Post-model validator hook: soft-rewrite bad AIMessages, escalate on repeat.

Trigger predicate (CONTEXT.md "Post-model validator — trigger predicate"):
    AIMessage.content is non-empty
    AND AIMessage has no tool_calls
    AND state.clarificationPending is True

Action on first drift (validatorRetryCount == 0):
    Return {
        "messages": [RemoveMessage(id=bad_ai.id), corrective_system_message],
        "validatorRetryCount": 1,
    }
    The re-invocation happens automatically via the post_model_hook_router
    loop (chat_agent_executor.py L919-956) — no tool_calls on the last
    AIMessage means the router will re-enter pre_model_hook -> agent.

Action on second drift (validatorRetryCount >= 1):
    Return {"validatorEscalate": True}
    The outer postIntakeRouter (Plan 06) picks this up and routes to
    humanEscalationNode.

Sources:
  - 13-RESEARCH.md §4 (RemoveMessage verified importable on 1.1.3)
  - artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md L154
    (belt-and-braces: state flag + pre-model directive + post-model validator)
  - docs/deep-research-systemprompt-chat-agent.md L117 (self-correction)
    -> L526 (escalate on repeat failure)
"""

import logging

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph.message import RemoveMessage

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)

_CORRECTIVE_MESSAGE = (
    "CORRECTION: You produced a user-facing question without calling "
    "askHuman. Retry: call the askHuman tool with your question now. "
    "Do not emit plain-text questions while a clarification is pending."
)


async def postModelHook(state: dict) -> dict:
    """Detect drift on the last AIMessage and either soft-rewrite or escalate.

    Returns an empty dict on clean responses (no-op — zero false positives).
    """
    messages = state.get("messages") or []
    clarificationPending: bool = bool(state.get("clarificationPending"))
    validatorRetryCount: int = int(state.get("validatorRetryCount", 0))

    # Find the most recent AIMessage
    lastAi: AIMessage | None = next(
        (m for m in reversed(messages) if isinstance(m, AIMessage)),
        None,
    )
    if lastAi is None:
        return {}

    # Trigger predicate: all three must be true
    hasContent = bool(getattr(lastAi, "content", None))
    hasToolCalls = bool(getattr(lastAi, "tool_calls", None))
    isDrift = hasContent and not hasToolCalls and clarificationPending

    if not isDrift:
        return {}

    logEvent(
        logger,
        "intake.validator.trigger",
        logCategory="routing",
        agent="intake",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        turnIndex=state.get("turnIndex", 0),
        validatorRetryCount=validatorRetryCount,
        message="Post-model validator triggered: drift detected",
    )

    if validatorRetryCount >= 1:
        # Second drift — escalate (CONTEXT.md: retry bound = 1)
        logEvent(
            logger,
            "intake.validator.escalate",
            logCategory="routing",
            agent="intake",
            claimId=state.get("claimId"),
            threadId=state.get("threadId"),
            turnIndex=state.get("turnIndex", 0),
            reason="validator_second_drift",
            message="Post-model validator escalating: second drift",
        )
        return {"validatorEscalate": True}

    # First drift — soft-rewrite
    logEvent(
        logger,
        "intake.validator.rewrite",
        logCategory="routing",
        agent="intake",
        claimId=state.get("claimId"),
        threadId=state.get("threadId"),
        turnIndex=state.get("turnIndex", 0),
        retryIndex=1,
        correctiveDirective=_CORRECTIVE_MESSAGE[:200],
        message="Post-model validator soft-rewrite: first drift",
    )
    return {
        "messages": [
            RemoveMessage(id=lastAi.id),
            SystemMessage(content=_CORRECTIVE_MESSAGE),
        ],
        "validatorRetryCount": validatorRetryCount + 1,
    }
