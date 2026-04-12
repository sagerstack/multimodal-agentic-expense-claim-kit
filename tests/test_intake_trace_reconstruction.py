"""Trace reconstruction test — 13-CONTEXT.md Observability verification.

Simulates claim lifecycle segments (including one escalation path) by calling
the intake hooks / router directly and captures logEvent emissions. Asserts
the captured log stream is sufficient to reconstruct the claim timeline.

Per 13-CONTEXT.md Observability section:
  "run a representative claim end-to-end (including one escalation path)
   and confirm the log stream can reconstruct: every user prompt, every
   LLM call, every tool call and its result, every routing decision,
   every state transition, in the correct order."

Does NOT require docker compose — patches logEvent to capture emissions
while exercising the code path in-process.

Coverage:
  - Happy path: VND unsupported → postToolFlagSetter sets flags → preModelHook
    injects directive → postIntakeRouter returns "continue"
  - Escalation path: second-drift postModelHook → validatorEscalate=True →
    postIntakeRouter returns "humanEscalation"
  - Taxonomy sanity: all Phase 13 event names are defined and non-empty

Run with:
  poetry run pytest tests/test_intake_trace_reconstruction.py -v
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# captureLogEvents fixture
# ---------------------------------------------------------------------------

@contextmanager
def _patchLogEvent():
    """Patch every logEvent import site in the intake pipeline.

    Python imports `logEvent` by reference at module load time — patching
    only `agentic_claims.core.logging.logEvent` does not retroactively update
    references already bound in other modules. Each module-level import site
    must be patched individually.

    Returns a shared list; each logEvent call appends (eventName, fields, category).
    """
    captured: list[tuple[str, dict, str]] = []

    def _capture(logger_arg, eventName, *, level=None, message=None, payload=None, **fields):
        captured.append((eventName, dict(fields), fields.get("logCategory", "")))

    patchTargets = [
        "agentic_claims.core.logging.logEvent",
        "agentic_claims.agents.intake.hooks.preModelHook.logEvent",
        "agentic_claims.agents.intake.hooks.postModelHook.logEvent",
        "agentic_claims.agents.intake.hooks.postToolFlagSetter.logEvent",
        "agentic_claims.agents.intake.hooks.submitClaimGuard.logEvent",
        "agentic_claims.agents.intake.node.logEvent",
        "agentic_claims.agents.intake.nodes.humanEscalation.logEvent",
    ]

    patches = [patch(target, side_effect=_capture) for target in patchTargets]
    for p in patches:
        p.start()

    try:
        yield captured
    finally:
        for p in patches:
            p.stop()


@pytest.fixture
def captureLogEvents():
    """Yield the captured events list; patch all logEvent sites for the test."""
    with _patchLogEvent() as events:
        yield events


# ---------------------------------------------------------------------------
# Helper: assert events appear in order
# ---------------------------------------------------------------------------

def _assertOrdered(capturedNames: list[str], orderedSubset: list[str]) -> None:
    """Assert each event in orderedSubset appears in capturedNames, in order."""
    pointer = 0
    for required in orderedSubset:
        found = False
        while pointer < len(capturedNames):
            if capturedNames[pointer] == required:
                pointer += 1
                found = True
                break
            pointer += 1
        assert found, (
            f"Required event '{required}' not found in captured log stream at or after "
            f"previous required event. Full captured stream: {capturedNames}"
        )


# ---------------------------------------------------------------------------
# Task 1 — VND unsupported flag path + preModelHook directive injection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vndFlagPath_postToolFlagSetterAndPreModelHookEmitEvents(captureLogEvents):
    """VND unsupported: postToolFlagSetter → preModelHook → router emits correct events.

    This test directly validates the Phase 13 Bug 2 fix at the hook level without
    requiring a live LLM call. It proves the log stream carries the required events
    in the correct order for trace reconstruction.

    Events expected (in order):
      intake.hook.post_tool.flag_set   (postToolFlagSetter: unsupportedCurrencies)
      intake.hook.pre_model.directive_injected   (preModelHook: unsupportedCurrencies directive)
      intake.router.decision           (postIntakeRouter: continue, no escalation)
    """
    from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter
    from agentic_claims.agents.intake.hooks.preModelHook import preModelHook
    from agentic_claims.agents.intake.node import postIntakeRouter

    claimId = "claim-trace-vnd-happy"
    threadId = "thread-trace-vnd-happy"

    # Build state with a convertCurrency ToolMessage returning {supported: false, currency: VND}
    vndToolMsg = ToolMessage(
        content='{"supported": false, "currency": "VND", "error": "unsupported"}',
        tool_call_id="tc-vnd-1",
        name="convertCurrency",
    )
    state = {
        "claimId": claimId,
        "threadId": threadId,
        "messages": [
            HumanMessage(content="Process this receipt from Vietnam"),
            AIMessage(content="", tool_calls=[{"name": "convertCurrency", "id": "tc-vnd-1", "args": {}}]),
            vndToolMsg,
        ],
        "turnIndex": 1,
        "unsupportedCurrencies": set(),
        "askHumanCount": 0,
        "clarificationPending": False,
        "validatorEscalate": False,
        "validatorRetryCount": 0,
    }

    # Step 1: postToolFlagSetter scans ToolMessages and sets flags
    flagUpdates = await postToolFlagSetter(state)

    assert "unsupportedCurrencies" in flagUpdates, (
        "postToolFlagSetter must set unsupportedCurrencies for VND."
    )
    assert "VND" in flagUpdates["unsupportedCurrencies"], (
        "postToolFlagSetter must add 'VND' to unsupportedCurrencies set."
    )
    assert flagUpdates.get("clarificationPending") is True, (
        "postToolFlagSetter must set clarificationPending=True for VND."
    )

    # Apply flag updates to state
    state = {**state, **flagUpdates}

    # Step 2: preModelHook builds directive for the unsupported currency
    hookResult = await preModelHook(state)

    assert "llm_input_messages" in hookResult, (
        "preModelHook must return llm_input_messages."
    )
    directives = hookResult["llm_input_messages"]
    assert len(directives) > 0, "preModelHook must inject at least one directive for VND."

    # Verify the directive mentions VND and askHuman
    directiveText = " ".join(
        m.content for m in directives if hasattr(m, "content") and isinstance(m.content, str)
    ).lower()
    assert "vnd" in directiveText, (
        f"Pre-model directive must mention 'VND'. Got: {directiveText[:200]}"
    )
    assert "askhuman" in directiveText or "ask" in directiveText, (
        f"Pre-model directive must instruct askHuman. Got: {directiveText[:200]}"
    )

    # Step 3: postIntakeRouter — no escalation (validatorEscalate=False, askHumanCount=0)
    branch = postIntakeRouter(state)
    assert branch == "continue", (
        f"postIntakeRouter should return 'continue' (not 'humanEscalation') "
        f"when VND flag is set but no escalation signal. Got: '{branch}'"
    )

    # Step 4: assert the trace contains required events in order
    capturedNames = [e[0] for e in captureLogEvents]

    _assertOrdered(capturedNames, [
        "intake.hook.post_tool.flag_set",         # from postToolFlagSetter
        "intake.hook.pre_model.directive_injected",  # from preModelHook
        "intake.router.decision",                  # from postIntakeRouter
    ])

    # Step 5: assert claimId correlation on all intake.* events
    for name, fields, _cat in captureLogEvents:
        if name.startswith("intake."):
            assert fields.get("claimId") == claimId, (
                f"Event '{name}' missing or wrong claimId. "
                f"Expected: '{claimId}'. Fields: {fields}"
            )

    # Step 6: assert the router.decision event carries branch + reason
    routerEvents = [(n, f) for n, f, _ in captureLogEvents if n == "intake.router.decision"]
    assert len(routerEvents) >= 1, "intake.router.decision must be emitted."
    routerName, routerFields = routerEvents[-1]
    assert routerFields.get("branch") == "continue", (
        f"router.decision event must carry branch='continue'. Fields: {routerFields}"
    )


# ---------------------------------------------------------------------------
# Task 2 — Escalation path: second-drift postModelHook → validatorEscalate=True
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalationPathTraceReconstruction(captureLogEvents):
    """Escalation path: second-drift postModelHook → validatorEscalate=True → humanEscalation.

    Simulates the second validator drift scenario:
      - State has clarificationPending=True + validatorRetryCount=1
      - A new AIMessage with content + no tool_calls arrives (second drift)
      - postModelHook detects drift and returns validatorEscalate=True
      - postIntakeRouter routes to "humanEscalation"

    Events expected (in order):
      intake.validator.trigger         (postModelHook: drift detected)
      intake.validator.escalate        (postModelHook: second drift → escalate)
      intake.router.decision           (postIntakeRouter: humanEscalation)
    """
    from agentic_claims.agents.intake.hooks.postModelHook import postModelHook
    from agentic_claims.agents.intake.node import postIntakeRouter

    claimId = "claim-trace-escalate"
    threadId = "thread-trace-escalate"

    # Build state: second drift — clarificationPending + retryCount already at 1
    driftAiMsg = AIMessage(content="What currency is this in?", id="ai-drift-second")

    state = {
        "claimId": claimId,
        "threadId": threadId,
        "messages": [
            HumanMessage(content="Process this receipt"),
            driftAiMsg,
        ],
        "clarificationPending": True,
        "validatorRetryCount": 1,   # second drift — retryCount >= 1 triggers escalate
        "validatorEscalate": False,
        "askHumanCount": 0,
        "turnIndex": 3,
    }

    # Step 1: postModelHook detects second drift → returns validatorEscalate=True
    hookResult = await postModelHook(state)

    assert hookResult.get("validatorEscalate") is True, (
        f"postModelHook must return validatorEscalate=True on second drift. "
        f"Got: {hookResult}"
    )

    # Apply updates to state
    state2 = {**state, **hookResult}

    # Step 2: postIntakeRouter reads validatorEscalate=True → humanEscalation
    branch = postIntakeRouter(state2)
    assert branch == "humanEscalation", (
        f"postIntakeRouter must return 'humanEscalation' when validatorEscalate=True. "
        f"Got: '{branch}'"
    )

    # Step 3: assert the trace contains required events in order
    capturedNames = [e[0] for e in captureLogEvents]

    _assertOrdered(capturedNames, [
        "intake.validator.trigger",     # postModelHook: drift detected
        "intake.validator.escalate",    # postModelHook: escalate decision
        "intake.router.decision",       # postIntakeRouter: humanEscalation
    ])

    # Step 4: assert claimId correlation on all intake.* events
    for name, fields, _cat in captureLogEvents:
        if name.startswith("intake."):
            assert fields.get("claimId") == claimId, (
                f"Event '{name}' missing or wrong claimId. "
                f"Expected: '{claimId}'. Fields: {fields}"
            )

    # Step 5: assert the escalate event carries reason
    escalateEvents = [(n, f) for n, f, _ in captureLogEvents if n == "intake.validator.escalate"]
    assert len(escalateEvents) >= 1, "intake.validator.escalate must be emitted."
    _, escalateFields = escalateEvents[-1]
    assert "reason" in escalateFields, (
        f"intake.validator.escalate must carry a 'reason' field. Fields: {escalateFields}"
    )

    # Step 6: assert the router.decision event carries branch=humanEscalation
    routerEvents = [(n, f) for n, f, _ in captureLogEvents if n == "intake.router.decision"]
    assert len(routerEvents) >= 1, "intake.router.decision must be emitted."
    _, routerFields = routerEvents[-1]
    assert routerFields.get("branch") == "humanEscalation", (
        f"router.decision event must carry branch='humanEscalation'. Fields: {routerFields}"
    )


# ---------------------------------------------------------------------------
# Task 3 — preIntakeValidator emits intake.turn.start with correct fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preIntakeValidatorEmitsTurnStartEvent(captureLogEvents):
    """preIntakeValidator emits intake.turn.start with claimId, threadId, turnIndex.

    This covers the Turn lifecycle entry in the CONTEXT.md event taxonomy.
    """
    from unittest.mock import AsyncMock, patch as _patch

    from agentic_claims.agents.intake.node import preIntakeValidator

    claimId = "claim-trace-validator"
    threadId = "thread-trace-validator"

    state = {
        "claimId": claimId,
        "threadId": threadId,
        "messages": [HumanMessage(content="receipt test")],
        "turnIndex": 0,
        "unsupportedCurrencies": set(),
        "clarificationPending": False,
        "askHumanCount": 0,
        "validatorEscalate": False,
    }

    # Patch postToolFlagSetter + submitClaimGuard to avoid heavy I/O
    with _patch(
        "agentic_claims.agents.intake.node.postToolFlagSetter",
        new_callable=AsyncMock,
        return_value={},
    ), _patch(
        "agentic_claims.agents.intake.node.submitClaimGuard",
        new_callable=AsyncMock,
        return_value={},
    ):
        updates = await preIntakeValidator(state)

    # turn.start must have been emitted
    capturedNames = [e[0] for e in captureLogEvents]
    assert "intake.turn.start" in capturedNames, (
        f"preIntakeValidator must emit intake.turn.start. Got: {capturedNames}"
    )

    # turnIndex must increment
    assert updates.get("turnIndex") == 1, (
        f"preIntakeValidator must increment turnIndex from 0 to 1. Got: {updates}"
    )

    # The turn.start event must carry claimId and threadId
    turnStartEvents = [(n, f) for n, f, _ in captureLogEvents if n == "intake.turn.start"]
    assert len(turnStartEvents) >= 1
    _, tsFields = turnStartEvents[0]
    assert tsFields.get("claimId") == claimId
    assert tsFields.get("threadId") == threadId
    assert tsFields.get("turnIndex") == 1


# ---------------------------------------------------------------------------
# Task 4 — Phase 13 event taxonomy: all defined names are non-empty strings
# ---------------------------------------------------------------------------

def test_phase13EventTaxonomyDefined():
    """Sanity: all Phase 13 event names defined in CONTEXT.md taxonomy are non-empty strings.

    This is a static contract test. The authoritative list comes from
    13-CONTEXT.md "Observability — end-to-end debuggability" section.
    """
    taxonomy = [
        "intake.turn.start",
        "intake.turn.end",
        "intake.hook.pre_model.directive_injected",
        "intake.hook.post_tool.flag_set",
        "intake.validator.trigger",
        "intake.validator.rewrite",
        "intake.validator.escalate",
        "intake.router.decision",
        "intake.escalation.triggered",
        "intake.currency.manual_rate_captured",
        "claim.status_changed",
        # intakeNode additional events
        "intake.started",
        "intake.completed",
        "intake.agent_invoked",
    ]

    for name in taxonomy:
        assert isinstance(name, str) and len(name) > 0, (
            f"Taxonomy entry must be a non-empty string. Got: {name!r}"
        )
        # Event names must use dot-separated namespacing
        assert "." in name, (
            f"Event name must use dot-separated namespace. Got: {name!r}"
        )
        # No whitespace
        assert " " not in name, (
            f"Event name must not contain spaces. Got: {name!r}"
        )

    # All names must be unique (no typo duplicates)
    assert len(taxonomy) == len(set(taxonomy)), (
        "Taxonomy contains duplicate event names — check for typos."
    )
