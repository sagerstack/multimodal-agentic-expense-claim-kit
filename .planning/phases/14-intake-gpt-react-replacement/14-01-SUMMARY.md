---
phase: 14
plan: 01
subsystem: intake-gpt
tags: [tdd, red-phase, interrupt-state-machine, classifier]

dependency-graph:
  requires: []
  provides: ["red-phase tests pinning Phase 14 interrupt classifier contract"]
  affects: ["14-02", "14-03"]

tech-stack:
  added: []
  patterns: ["TDD red phase — tests define contract before implementation"]

key-files:
  created: []
  modified:
    - tests/test_intake_gpt.py

decisions:
  - "4 of 7 tests fail (not 5 as estimated) — 3 tests pass because the behaviors are already correctly implemented in current code"
  - "E501 errors in test file are pre-existing (lines 162, 301, 653, 849) — no E402 errors introduced"

metrics:
  duration: "~5 min"
  completed: "2026-04-14"
---

# Phase 14 Plan 01: Red-Phase Interrupt State Machine Contract Tests Summary

**One-liner:** 7 TDD red-phase tests appended to test_intake_gpt.py pinning the deterministic interrupt classifier and interruptResolutionNode contracts.

## What Was Done

Appended 7 new CamelCase test functions to `tests/test_intake_gpt.py`. Imports for `_classifyInterruptReply`, `_buildRuntimeContext`, and `interruptResolutionNode` were added to the existing import block at the top of the file.

## Test Results (Red Phase)

Total tests: 29 (22 original + 7 new)

| Test | Result | Reason |
|------|--------|--------|
| `test_classifyInterruptReplyRejectsNegativeTokenForFieldConfirmation` | FAIL | Bug A: "no"/"nope"/"cancel" fall through to catch-all `return "answer"` for field_confirmation |
| `test_classifyInterruptReplyRejectsNegativeTokenForPolicyJustification` | FAIL | Bug A: same catch-all — negative tokens classified as "answer" for policy_justification |
| `test_classifyInterruptReplyDetectsSideQuestionForPolicyJustification` | FAIL | No interrogative-word or `?`-ending detection exists for policy_justification |
| `test_classifyInterruptReplyPreservesJustificationTextVerbatim` | PASS | Already correct — free-form text falls to catch-all "answer" which is right |
| `test_interruptResolutionNodePreservesPendingInterruptOnSideQuestion` | FAIL | `interruptResolutionNode` is a stub that does not call `_classifyInterruptReply` or write `lastResolution` |
| `test_applyToolResultsNodeStoresVerbatimJustificationText` | PASS | Already correct — `applyToolResultsNode` stores `responseText` verbatim for policy_justification |
| `test_buildRuntimeContextExposesPendingInterruptAndSideQuestionOutcome` | PASS | Already correct — `_buildRuntimeContext` serializes `pendingInterrupt` and `lastResolution` into JSON payload |

**4 failing (not 5 as estimated)** — 3 tests pass because the current implementation already handles those behaviors correctly.

## Unexpectedly Passing Tests

Tests 4, 6, 7 pass against the current code:

- **Test 4** (verbatim justification text): The catch-all `return "answer"` in `_classifyInterruptReply` correctly returns "answer" for free-form text that is neither affirmative nor a known token. This is correct behavior — the bug is only for negative tokens.
- **Test 6** (applyToolResultsNode verbatim storage): `applyToolResultsNode` already uses `responseText` directly for `policy_justification` — the text is already stored verbatim.
- **Test 7** (_buildRuntimeContext): The function already serializes `pendingInterrupt` and `lastResolution` as JSON, which includes all required fields (`kind`, `question`, `outcome`).

## Imports Added

Added to the existing `from agentic_claims.agents.intake_gpt.graph import (...)` block:
- `_buildRuntimeContext`
- `_classifyInterruptReply`
- `interruptResolutionNode`

## Deviations from Plan

### Deviation — Fewer Failures Than Estimated

- **Type:** Automatic finding (not a rule deviation)
- **Found during:** Test execution
- **Issue:** Plan estimated "at least 5 of 7 new tests FAIL" — actual result is 4 failures
- **Root cause:** 3 behaviors are already correctly implemented in the current codebase
- **Impact:** None — 4 failing tests still pin the actual bugs (Bug A: negative-token classifier, side-question detection, stub interruptResolutionNode). The 3 passing tests confirm pre-existing correct behavior.
- **Action:** Documented. No test changes made (tests are correct, estimation was slightly off).

None - no modifications to existing tests or source code. Imports added to top of file, no E402 violations.

## Commits

| Hash | Message |
|------|---------|
| 82626ba | test(14-01): add red-phase tests for interrupt state machine contract |

## Next Phase Readiness

Plan 14-02 can proceed: it needs to fix `_classifyInterruptReply` to handle negative tokens for `field_confirmation` and `policy_justification`, add side-question detection, and implement `interruptResolutionNode` properly. The 4 failing tests will turn green after those fixes.
