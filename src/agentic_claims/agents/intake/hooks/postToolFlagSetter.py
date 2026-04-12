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

from langchain_core.messages import ToolMessage

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


async def postToolFlagSetter(state: dict) -> dict:
    """Scan the latest ToolMessages and derive Phase 13 state flag updates.

    Should be called in the outer wrapper graph after the intake subgraph
    returns (Plan 06 wires this). Idempotent: reading the same ToolMessages
    twice produces the same flag set because unsupportedCurrencies uses
    set-union reducer (Plan 02) so accumulating across calls is safe, and
    other flags are last-write-wins booleans.

    Scan scope: the unbroken trailing run of ToolMessages since the last
    non-ToolMessage. This represents "this turn's tool results" only — we
    do not re-scan older turns.

    Returns an empty dict if no relevant ToolMessages are present.
    """
    messages = state.get("messages") or []
    claimId = state.get("claimId")
    threadId = state.get("threadId")

    # Collect the unbroken trailing run of ToolMessages since the last
    # non-ToolMessage (AIMessage / HumanMessage). This is "this turn's results".
    thisTurnTools: list[ToolMessage] = []
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

        # askHuman resumed -> increment loop counter + resolve pending clarification
        if toolName == "askHuman":
            askHumanIncrement += 1
            # F1 (13-12): askHuman ToolMessage is definitionally a user answer.
            # If a clarification was pending, it is now resolved.
            # Source: 13-DEBUG-policy-exception-loop.md F1; 13-DEBUG-display-regression.md Fix C.
            if state.get("clarificationPending"):
                clearClarificationPending = True
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

    return updates
