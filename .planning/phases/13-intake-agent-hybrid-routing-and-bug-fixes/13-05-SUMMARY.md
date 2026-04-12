---
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
plan: "05"
subsystem: hooks
tags: [routing, hooks, state-flags, hallucination-guard, langgraph, intake-agent, tdd]

dependency_graph:
  requires:
    - 13-01: convertCurrency {supported: False} contract (read by postToolFlagSetter)
    - 13-02: ClaimState unsupportedCurrencies, clarificationPending, askHumanCount, validatorEscalate fields
  provides:
    - postToolFlagSetter: ToolMessage → Phase 13 state flag derivation
    - submitClaimGuard: submitClaim hallucination detection (Bug 3 / Criterion 4)
  affects:
    - 13-06-PLAN (wires both hooks into the wrapper graph)
    - 13-07-PLAN (postModelHook can rely on postToolFlagSetter having already set clarificationPending)
    - 13-09-PLAN (integration tests verify the full hook chain)

tech_stack:
  added: []
  patterns:
    - Post-tool hook pattern: trailing ToolMessage scan (this-turn scope) → partial state update
    - submitClaim hallucination guard: phrase regex + tool_call/ToolMessage correlation
    - logEvent(logger, event, logCategory=...) convention (not plan's incorrect dict first-arg form)

key_files:
  created:
    - src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py
    - src/agentic_claims/agents/intake/hooks/submitClaimGuard.py
    - tests/test_post_tool_flag_setter.py
    - tests/test_submit_claim_guard.py
  modified: []

decisions:
  - "logEvent(logger, event, **fields) convention applied — plan examples used incorrect dict-as-first-arg form; fixed automatically"
  - "postToolFlagSetter scans only the trailing unbroken run of ToolMessages (this-turn scope), not full history"
  - "submitClaimGuard escalates immediately on first hallucination detection — no soft-rewrite for this class (per 13-CONTEXT.md)"
  - "Both functions are async def for consistency with wrapper graph node signature (Plan 06)"

metrics:
  duration: "~8 minutes"
  started: "2026-04-12T14:46:53Z"
  completed: "2026-04-12T14:55:09Z"
  tests_added: 21
  tests_passing: 276
---

# Phase 13 Plan 05: Post-Tool Flag Setter and Submit Guard Summary

**One-liner:** `postToolFlagSetter` translates `{supported: false}` ToolMessages into `unsupportedCurrencies`/`clarificationPending` flags, and `submitClaimGuard` catches the submitClaim hallucination class (Bug 3) by correlating AIMessage prose with actual tool call evidence.

## Performance

- **Duration:** ~8 minutes
- **Started:** 2026-04-12T14:46:53Z
- **Completed:** 2026-04-12T14:55:09Z
- **Tasks:** 2 (+ TDD test commits)
- **Tests added:** 21 (10 postToolFlagSetter, 11 submitClaimGuard)
- **Tests passing:** 276 / 276 non-pre-existing

## What Was Built

### postToolFlagSetter (`hooks/postToolFlagSetter.py`)

**Trigger predicate:** Called after the intake subgraph turn completes. Scans the unbroken trailing run of ToolMessages (messages after the last non-ToolMessage in state.messages).

**Flag derivation rules:**

| ToolMessage condition | State flag(s) set |
|---|---|
| `convertCurrency` with `{supported: false, currency: X}` | `unsupportedCurrencies: {X}`, `clarificationPending: True` |
| `askHuman` (any content — interrupt resumed) | `askHumanCount: current + 1` |
| `ToolMessage.status == "error"` (any tool) | `validatorEscalate: True` |
| Any other ToolMessage | No flags set (returns `{}`) |

**Idempotency guarantee:** Scanning the same trailing ToolMessages twice produces the same update dict. The `_unionSet` reducer on `unsupportedCurrencies` (Plan 02) makes accumulation across calls safe — calling postToolFlagSetter twice with the same state results in the same final set because `{VND} | {VND} == {VND}`.

**Scope boundary:** Only the unbroken trailing ToolMessage run is scanned. ToolMessages from prior turns (separated by an AIMessage or HumanMessage) are not re-processed. This prevents double-counting `askHumanCount` across turns.

### submitClaimGuard (`hooks/submitClaimGuard.py`)

**Trigger predicate:** Fires when the most recent AIMessage in state.messages contains one of the submission-success phrases AND no `submitClaim` tool_call + ToolMessage pair exists in the current turn (since the last HumanMessage).

**Submission-success phrases recognized:**

| Pattern | Example match |
|---|---|
| `claim (has been\|is\|was) submitted` | "Your claim has been submitted" |
| `successfully submitted` | "I have successfully submitted your expense claim" |
| `claim number is` | "Your claim number is CLAIM-042" |
| `submission (complete\|successful)` | "Submission complete. Your claim is in the queue." |

**No-false-positive guarantee:** If both a `submitClaim` tool_call on an AIMessage AND a `submitClaim` ToolMessage (result) are found in the current turn, the guard returns `{}` (legitimate acknowledgement path). The check requires both the call and the result to be present — an AIMessage with `tool_calls` but no matching ToolMessage (e.g., interrupted turn) would still trigger the guard.

**Escalation strategy:** Immediate `{validatorEscalate: True}` — no soft-rewrite for this class. Per 13-CONTEXT.md: submitClaim hallucinations are severe enough to require human review, not LLM retry.

**Edge cases evaluated:**
- Phrase in historical AIMessage (prior turns) — safe because we scan from the end of messages and the last AIMessage is the freshest one; older AIMessages don't re-trigger.
- `askHuman` response containing submission language — not an AIMessage, so not triggered.
- Interrupted turn (tool_call exists but no ToolMessage yet) — guard fires. Correct: if the turn was interrupted before the tool result arrived, we cannot confirm the submission happened.

## Task Commits

| # | Type | Hash | Description |
|---|---|---|---|
| 1a | test(13-05) | b3a3ad7 | Failing tests for postToolFlagSetter (RED) |
| 1b | feat(13-05) | df8c890 | Implement postToolFlagSetter hook (GREEN) |
| 2a | test(13-05) | cc71070 | Failing tests for submitClaimGuard (RED) |
| 2b | feat(13-05) | 03f3169 | Implement submitClaimGuard (Bug 3 / Criterion 4) (GREEN) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed incorrect `logEvent` call convention in plan examples**

- **Found during:** Task 1 implementation (reading `core/logging.py`)
- **Issue:** The plan's code examples call `logEvent("intake.hook.post_tool.flag_set", {...}, category="routing")` — passing the event string as first arg and a dict as second. The actual signature is `logEvent(logger: logging.Logger, event: str, *, logCategory=..., **fields)`. The first arg must be a `logging.Logger` instance, and the kwarg is `logCategory=` not `category=` (also confirmed by 13-01-SUMMARY.md decision).
- **Fix:** All `logEvent` calls use `logEvent(logger, event_string, logCategory="routing", **fields)` with module-level `logger = logging.getLogger(__name__)`.
- **Files modified:** Both new hook modules (plan examples were wrong, not existing code).
- **Impact:** Zero — the correct pattern was applied before the modules were run. All 21 tests pass.

## Verification

| Criterion | Status |
|---|---|
| postToolFlagSetter detects `{supported: false}` convertCurrency and sets unsupportedCurrencies + clarificationPending | PASS — 2 dedicated tests |
| postToolFlagSetter increments askHumanCount on askHuman ToolMessage | PASS — 2 tests (from-zero and from-N) |
| postToolFlagSetter idempotent across repeated calls | PASS — explicit idempotency test |
| submitClaimGuard detects hallucinated submission (success language without tool call) | PASS — 4 phrase-variant tests |
| submitClaimGuard does NOT trigger on legitimate acknowledgement after real submitClaim | PASS — 2 no-false-positive tests |
| Every flag-set emits logEvent with proper fields | PASS — logEvent emission tests for both modules |
| Both modules importable as standalone functions | PASS — import verification |
| No wiring into node.py (Plan 06 concern) | PASS — only hooks/ directory touched |
| Full suite regression | PASS — 276 passing, 4 pre-existing failures unchanged |

## Must-Haves Verification

| Must-have truth | Verified |
|---|---|
| postToolFlagSetter scans ToolMessages for {supported: false} → unsupportedCurrencies + clarificationPending | TRUE |
| postToolFlagSetter detects askHuman ToolMessages and increments askHumanCount | TRUE |
| submitClaimGuard detects submission-success language without submitClaim tool call/result | TRUE |
| submitClaimGuard does NOT fire on legitimate acknowledgements after real submitClaim | TRUE |
| Both modules are pure state-in / partial-state-out | TRUE — no global mutation |
| Every flag-set emits intake.hook.post_tool.flag_set logEvent | TRUE |
| Covers ROADMAP Success Criterion #4 (submitClaim hallucination guard) | TRUE |
| Extends substrate for #5 (askHumanCount increment path) | TRUE |

## Next Phase Readiness

- Plan 13-06 (wrapper graph wiring) is unblocked — both hook modules are importable standalone functions
- Plan 13-07 (postModelHook) can rely on `clarificationPending` being set by postToolFlagSetter before it reads it
- Plan 13-09 (integration tests) will wire all hooks and verify end-to-end routing

---
*Phase: 13-intake-agent-hybrid-routing-and-bug-fixes*
*Completed: 2026-04-12*
