"""Pre-model hook: ephemeral directive injection.

Reads Phase 13 state flags (unsupportedCurrencies, clarificationPending)
and builds SystemMessage directives that are passed to the LLM via the
`llm_input_messages` channel WITHOUT being written to state.messages.

Sources:
  - LangGraph 1.1.3 installed source: chat_agent_executor.py L400-410
    (llm_input_messages is the ephemeral channel).
  - 13-CONTEXT.md "Hook architecture — message lifecycle" (ephemeral).
  - artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md
    L154, L201-202 (directive rebuilt from state per call).
"""

import logging

from langchain_core.messages import SystemMessage

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


async def preModelHook(state: dict) -> dict:
    """Build llm_input_messages with any active routing directives.

    Returns:
        dict with `llm_input_messages` key. Never writes `messages`
        (ephemeral channel — directives MUST NOT persist to state).
    """
    baseMessages = list(state.get("messages") or [])
    directives: list[SystemMessage] = []

    unsupportedCurrencies: set[str] = set(state.get("unsupportedCurrencies") or set())
    if unsupportedCurrencies:
        currencies = ", ".join(sorted(unsupportedCurrencies))
        directives.append(
            SystemMessage(
                content=(
                    f"ROUTING DIRECTIVE: Currencies {currencies} are not "
                    "supported by the automatic conversion provider. "
                    "Do NOT call convertCurrency for these currencies. "
                    "Use the askHuman tool to request a manual rate from "
                    "the user."
                )
            )
        )
        logEvent(
            logger,
            "intake.hook.pre_model.directive_injected",
            logCategory="routing",
            agent="intake",
            claimId=state.get("claimId"),
            threadId=state.get("threadId"),
            turnIndex=state.get("turnIndex", 0),
            flagName="unsupportedCurrencies",
            flagValue=sorted(unsupportedCurrencies),
            message="Pre-model directive injected: unsupportedCurrencies",
        )

    clarificationPending: bool = bool(state.get("clarificationPending"))
    if clarificationPending:
        directives.append(
            SystemMessage(
                content=(
                    "ROUTING DIRECTIVE: A clarification is pending. "
                    "You must call askHuman to surface the question. "
                    "Do NOT emit a plain-text question."
                )
            )
        )
        logEvent(
            logger,
            "intake.hook.pre_model.directive_injected",
            logCategory="routing",
            agent="intake",
            claimId=state.get("claimId"),
            threadId=state.get("threadId"),
            turnIndex=state.get("turnIndex", 0),
            flagName="clarificationPending",
            flagValue=True,
            message="Pre-model directive injected: clarificationPending",
        )

    return {"llm_input_messages": directives + baseMessages}
