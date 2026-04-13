"""Post-tool flag setter: derives routing state flags from ToolMessages.

Scans recent ToolMessages in state.messages and translates their content
into Phase 13 state flags that downstream hooks read:
  - convertCurrency ToolMessage with {supported: false, currency: X}
    -> unsupportedCurrencies: {X}, clarificationPending: True
  - askHuman ToolMessage (any result — the interrupt resumed)
    -> askHumanCount += 1
    -> IF state.clarificationPending was True: clarificationPending: False
       (the user's answer resolves the pending state)
  - Any tool error (ToolMessage.status == "error")
    -> validatorEscalate: True (routes to humanEscalationNode)

Flag-clearing semantics (F1, Plan 13-12):
  - askHuman ToolMessage AND state.clarificationPending was True
    -> clarificationPending: False (the user's answer resolves the pending state)

  - When a turn has BOTH convertCurrency(supported=false) AND an askHuman
    ToolMessage, the clarification stays True (a new unsupported currency was
    detected; the pending state moves from one topic to another). This matches
    the "last write wins" semantic: clearClarificationPending is applied BEFORE
    setClarification, so a turn with both ends up pending=True.

  - Clearing is EXCLUSIVE to askHuman ToolMessages. convertCurrency,
    searchPolicies, and submitClaim ToolMessages do NOT clear the flag.
    Rationale: only askHuman represents a user answer that resolves a pending
    clarification.

This module is the single place in Phase 13 where raw tool output is
inspected for routing decisions. The LLM never does this — the prompt
(v5, Plan 03) strips all such instructions.

Pure state-in / partial-state-out, idempotent. No side effects beyond
logEvent calls.

Sources:
  - 13-RESEARCH.md §2 "Risk 4: askHumanCount increment timing"
    (recommended: scan in post-tool, not in preIntakeValidator)
  - 13-CONTEXT.md "Hook architecture — directive injection"
  - artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md
    L153 (Gap 3 — structured error -> state flag)
  - 13-01-SUMMARY.md (convertCurrency {supported} contract)
  - 13-02-SUMMARY.md (ClaimState field definitions and reducers)
  - 13-DEBUG-policy-exception-loop.md F1 (clear on askHuman resolution)
  - 13-DEBUG-display-regression.md Fix C (same fix, consolidated)
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


def _safeJsonParse(content: Any) -> Any:
    """Parse ToolMessage.content defensively — may be a JSON string or dict."""
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except (ValueError, TypeError):
            return content
    return content


async def postToolFlagSetter(state: dict, scanMode: str = "trailing") -> dict:
    """Scan ToolMessages and derive Phase 13 state flag updates.

    Two scan modes:
      - "trailing" (default): walk back from end, stop at first non-ToolMessage.
        Use this from preIntakeValidator where state.messages is the full
        checkpointed history — the trailing run is the interrupt-resume tool(s)
        just filled by Command(resume=...).
      - "full-delta": scan every ToolMessage in state["messages"]. Use this from
        the post-subgraph site where state["messages"] is the subgraph's
        *delta* (only this turn's new messages). Required because qwen3 often
        emits an AIMessage (e.g., JSON content, error-recovery prose) AFTER a
        tool call, which would hide prior ToolMessages from the trailing scan.
        Source: 13-DEBUG-phase1-skip.md Issue 2 (CLAIM-022 regression).

    Idempotency: unsupportedCurrencies uses set-union so repeat-adds are safe.
    Boolean flags are last-write-wins. askHumanCount is an increment counter
    and MUST NOT be incremented in "full-delta" mode — it would double-count
    with the preIntakeValidator trailing scan that fires next turn on resume.
    """
    messages = state.get("messages") or []
    claimId = state.get("claimId")
    threadId = state.get("threadId")

    if scanMode == "full-delta":
        thisTurnTools: list[ToolMessage] = [
            m for m in messages if isinstance(m, ToolMessage)
        ]
    else:
        # Trailing scan: unbroken run of ToolMessages from the end.
        thisTurnTools = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                thisTurnTools.append(msg)
            else:
                break
        thisTurnTools.reverse()

    if not thisTurnTools:
        return {}

    currentAskHumanCount = int(state.get("askHumanCount") or 0)
    newUnsupported: set[str] = set()
    setClarification = False
    clearClarificationPending = False
    setEscalate = False
    askHumanIncrement = 0
    setPhase1Confirmation = False
    clearPhase1Confirmation = False

    for tm in thisTurnTools:
        toolName = getattr(tm, "name", None) or ""
        parsed = _safeJsonParse(getattr(tm, "content", None))

        # convertCurrency -> unsupportedCurrencies + clarificationPending
        if toolName == "convertCurrency" and isinstance(parsed, dict):
            if parsed.get("supported") is False:
                currency = parsed.get("currency")
                if currency:
                    newUnsupported.add(currency)
                    setClarification = True
                    logEvent(
                        logger,
                        "intake.hook.post_tool.flag_set",
                        logCategory="routing",
                        claimId=claimId,
                        threadId=threadId,
                        flagName="unsupportedCurrencies",
                        flagValue=currency,
                        toolName=toolName,
                        agent="intake",
                    )

        # searchPolicies -> set clarificationPending so drift detection fires
        # on the next turn. After a policy search the agent must either confirm
        # the summary or elicit a justification — both require askHuman. If the
        # LLM emits the question as plain text, preModelHook's drift detection
        # reads clarificationPending and can rewrite the turn.
        # Source: 13-DEBUG-policy-exception-loop.md F3.
        if toolName == "searchPolicies":
            setClarification = True
            logEvent(
                logger,
                "intake.hook.post_tool.flag_set",
                logCategory="routing",
                claimId=claimId,
                threadId=threadId,
                flagName="clarificationPending",
                flagValue=True,
                toolName=toolName,
                reason="searchPolicies_expects_user_response",
                agent="intake",
            )

        # extractReceiptFields -> set phase1ConfirmationPending so the model
        # must ask the step-9 confirmation ("Do the details look correct?")
        # before searchPolicies. Source: 13-DEBUG-phase1-skip.md (Issue 2).
        if toolName == "extractReceiptFields":
            setPhase1Confirmation = True
            logEvent(
                logger,
                "intake.hook.post_tool.flag_set",
                logCategory="routing",
                claimId=claimId,
                threadId=threadId,
                flagName="phase1ConfirmationPending",
                flagValue=True,
                toolName=toolName,
                reason="extractReceiptFields_expects_user_confirmation",
                agent="intake",
            )

        # askHuman resumed -> increment loop counter + resolve pending clarification.
        # Skip increment in "full-delta" mode: the post-subgraph delta never
        # contains an askHuman ToolMessage (interrupt pauses the subgraph before
        # the ToolMessage is appended). The trailing scan on the NEXT turn's
        # preIntakeValidator is the single counting point — avoids double-count.
        if toolName == "askHuman" and scanMode == "trailing":
            askHumanIncrement += 1
            # F1 (13-12): askHuman ToolMessage is definitionally a user answer.
            # If a clarification was pending, it is now resolved.
            # Source: 13-DEBUG-policy-exception-loop.md F1; 13-DEBUG-display-regression.md Fix C.
            if state.get("clarificationPending"):
                clearClarificationPending = True

            # Issue 2: clear phase1ConfirmationPending ONLY when the paired
            # askHuman question asked the confirmation pattern (contains
            # "correct" case-insensitive). A manual-rate askHuman question
            # ("Can you share the exchange rate?") must NOT clear the flag —
            # the model still owes the user the confirmation step.
            if state.get("phase1ConfirmationPending"):
                question = _findAskHumanQuestion(messages, getattr(tm, "tool_call_id", None))
                if question and "correct" in question.lower():
                    clearPhase1Confirmation = True
                    logEvent(
                        logger,
                        "intake.hook.post_tool.flag_set",
                        logCategory="routing",
                        claimId=claimId,
                        threadId=threadId,
                        flagName="phase1ConfirmationPending",
                        flagValue=False,
                        toolName=toolName,
                        reason="confirmation_askHuman_resolved",
                        agent="intake",
                    )
            logEvent(
                logger,
                "intake.hook.post_tool.flag_set",
                logCategory="routing",
                claimId=claimId,
                threadId=threadId,
                flagName="askHumanCount",
                flagValue=currentAskHumanCount + askHumanIncrement,
                toolName=toolName,
                agent="intake",
            )

        # Critical tool failure (MCP unreachable, VLM permanent error)
        # Detected via ToolMessage.status == "error".
        if getattr(tm, "status", None) == "error":
            setEscalate = True
            logEvent(
                logger,
                "intake.hook.post_tool.flag_set",
                logCategory="routing",
                claimId=claimId,
                threadId=threadId,
                flagName="validatorEscalate",
                flagValue=True,
                toolName=toolName,
                reason="tool_status_error",
                agent="intake",
            )

    updates: dict[str, Any] = {}
    if newUnsupported:
        updates["unsupportedCurrencies"] = newUnsupported

    # F1: clear on askHuman resume BEFORE reapplying setClarification, so
    # a turn that has both (unusual — new unsupported + a separate askHuman)
    # correctly ends up with clarificationPending=True (last-write-wins: the
    # new unsupported-currency event wins over the resolution).
    if clearClarificationPending and not setClarification:
        updates["clarificationPending"] = False
        logEvent(
            logger,
            "intake.hook.post_tool.flag_set",
            logCategory="routing",
            claimId=claimId,
            threadId=threadId,
            flagName="clarificationPending",
            flagValue=False,
            toolName="askHuman",
            reason="askHuman_resolved_pending",
            agent="intake",
        )

    if setClarification:
        updates["clarificationPending"] = True

    if askHumanIncrement:
        updates["askHumanCount"] = currentAskHumanCount + askHumanIncrement
    if setEscalate:
        updates["validatorEscalate"] = True

    # Issue 2: phase1ConfirmationPending. Clear takes precedence when both
    # signals appear in the same turn (unusual — would require both an
    # extractReceiptFields call AND a confirmation-askHuman resume in the
    # same trailing tool run, which cannot happen in normal flow).
    if clearPhase1Confirmation:
        updates["phase1ConfirmationPending"] = False
    elif setPhase1Confirmation:
        updates["phase1ConfirmationPending"] = True

    return updates


def _findAskHumanQuestion(messages: list, toolCallId: str | None) -> str | None:
    """Locate the `question` arg from the AIMessage.tool_call paired with a
    given askHuman ToolMessage (matched by tool_call_id).

    Used by Issue 2 to distinguish the step-9 confirmation askHuman (question
    contains "correct") from manual-rate / currency-code askHumans so the
    phase1ConfirmationPending flag only clears when the user confirmed.
    """
    if not toolCallId:
        return None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", None) or []:
                if tc.get("id") == toolCallId and tc.get("name") == "askHuman":
                    args = tc.get("args") or {}
                    return args.get("question")
    return None
