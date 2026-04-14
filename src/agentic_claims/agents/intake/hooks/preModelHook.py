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

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from agentic_claims.core.logging import logEvent


def _lastAskHumanQuestion(messages: list) -> str | None:
    """Return the `question` arg of the trailing askHuman ToolMessage, or None.

    Walks back from the tail; stops at the first non-ToolMessage. If the
    trailing ToolMessage is askHuman, matches its tool_call_id against the
    preceding AIMessage's tool_calls to recover the original question text.

    Used by the tail-trigger narrowing to distinguish rate/confirmation
    answers (which should NOT re-trigger the askHuman directive) from
    generic clarification answers (which should).
    """
    lastAskHumanCallId: str | None = None
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            if getattr(msg, "name", None) == "askHuman":
                lastAskHumanCallId = getattr(msg, "tool_call_id", None)
            break
        continue
    if not lastAskHumanCallId:
        return None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                if tc.get("id") == lastAskHumanCallId and tc.get("name") == "askHuman":
                    return (tc.get("args") or {}).get("question")
    return None

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
    claimSubmitted: bool = bool(state.get("claimSubmitted"))

    # D1': also trigger the askHuman directive when the user just answered an
    # askHuman and the claim isn't submitted yet. F1 clears clarificationPending
    # on askHuman resume, so without this second trigger, drift detection never
    # fires on the turn immediately after a user answer — which is exactly when
    # qwen3-class models re-ask the question as plain prose (see screenshot #5
    # in 13-DEBUG-policy-exception-loop.md).
    lastToolMessageIsAskHuman = False
    for msg in reversed(baseMessages):
        if isinstance(msg, ToolMessage):
            lastToolMessageIsAskHuman = (getattr(msg, "name", None) == "askHuman")
            break
        # First non-ToolMessage terminates the scan; we only inspect the
        # trailing run of tool results ("this turn's results").
        continue

    askHumanTailTrigger = lastToolMessageIsAskHuman and not claimSubmitted
    shouldEmitAskHumanDirective = clarificationPending or askHumanTailTrigger

    if shouldEmitAskHumanDirective:
        directives.append(
            SystemMessage(
                content=(
                    "ROUTING DIRECTIVE: A clarification is pending. "
                    "You must call askHuman to surface the question. "
                    "Do NOT emit a plain-text question."
                )
            )
        )
        triggerReason = (
            "clarificationPending"
            if clarificationPending
            else "askHuman_tail_pre_submission"
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
            flagValue=clarificationPending,
            triggerReason=triggerReason,
            message=f"Pre-model directive injected: {triggerReason}",
        )

    # Issue 2 (screenshot #6, CLAIM-018): Phase 1 step-9 confirmation gate.
    # After extractReceiptFields ran, the model must emit askHuman("Do the
    # details look correct?") before searchPolicies. Without this directive,
    # qwen3 jumps straight from the manual-rate askHuman resume to Phase 2.
    # The flag is cleared by postToolFlagSetter once the confirmation
    # askHuman's question pattern matches (contains "correct") and the user
    # answers.
    phase1ConfirmationPending: bool = bool(state.get("phase1ConfirmationPending"))
    if phase1ConfirmationPending and not claimSubmitted:
        directives.append(
            SystemMessage(
                content=(
                    "ROUTING DIRECTIVE: Phase 1 confirmation is pending. "
                    "Before advancing to Phase 2, you MUST call askHuman to "
                    "confirm the extracted receipt details with the user "
                    "(e.g. 'Do the details above look correct?'). Remaining "
                    "Phase 1 tools (convertCurrency for non-SGD currency) are "
                    "still allowed if needed. Do NOT call searchPolicies yet. "
                    "Do NOT advance to Phase 2 until the user has confirmed."
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
            flagName="phase1ConfirmationPending",
            flagValue=True,
            triggerReason="phase1_confirmation_pending",
            message="Pre-model directive injected: phase1_confirmation_pending",
        )

    return {"llm_input_messages": directives + baseMessages}
