---
phase: 13
plan: 02
subsystem: state
tags: [langgraph, state, reducers, typing]

dependency_graph:
  requires: []
  provides:
    - ClaimState with six Phase 13 routing fields
    - _unionSet reducer for set-union accumulation
    - RemoveMessage/REMOVE_ALL_MESSAGES import verification
  affects:
    - 13-03 (askHumanCount loop bounds read from state)
    - 13-04 (postModelHook reads validatorEscalate, validatorRetryCount)
    - 13-05 (clarificationPending + askHumanCount used by outer router)
    - 13-06 (turnIndex used for log correlation)

tech_stack:
  added: []
  patterns:
    - Annotated reducer on TypedDict field (LangGraph set-union accumulation)
    - Boolean-flag decomposition instead of phase enum (composable state flags)

key_files:
  created:
    - tests/test_state_reducers.py
  modified:
    - src/agentic_claims/core/state.py

decisions:
  - "Boolean-flag decomposition chosen over single phase enum per CONTEXT.md; composable flags (clarificationPending + askHumanCount + unsupportedCurrencies) provide finer-grained routing control without enum exhaustion problems"
  - "TypedDict fields have no default factories — consuming code uses .get(field, default) convention per existing project pattern"
  - "RemoveMessage/REMOVE_ALL_MESSAGES confirmed importable from langgraph.graph.message (verified at runtime against LangGraph 1.1.3 installed in .venv)"

metrics:
  duration: "6 minutes"
  completed: "2026-04-12"
---

# Phase 13 Plan 02: ClaimState Reducers Summary

**One-liner:** Added six Phase 13 routing fields to ClaimState with `_unionSet` set-union reducer for `unsupportedCurrencies`, enabling code-enforced loop bounds and directive injection.

## What Was Built

### _unionSet Reducer (`src/agentic_claims/core/state.py`)

A module-level reducer function that merges two optional sets via union. LangGraph calls this when any node returns a partial state update for the `unsupportedCurrencies` field. The reducer handles all null-ness combinations cleanly: `None | None → set()`, `None | {x} → {x}`, `{x} | {y} → {x, y}`.

### Six New ClaimState Fields

| Field | Type | Reducer | Purpose |
|---|---|---|---|
| `askHumanCount` | `int` | (replace) | Loop-bound counter; incremented per askHuman interrupt |
| `unsupportedCurrencies` | `Annotated[set[str], _unionSet]` | `_unionSet` | Additive across turns — persists unsupported currency codes |
| `clarificationPending` | `bool` | (replace) | Set by post-tool flag setter when user input is required |
| `validatorRetryCount` | `int` | (replace) | Soft-rewrite attempts counter per turn |
| `validatorEscalate` | `bool` | (replace) | postModelHook → outer router escalation signal |
| `turnIndex` | `int` | (replace) | Per-turn correlation counter for log events |

All existing fields preserved verbatim — additive change only.

### Reducer Unit Tests (`tests/test_state_reducers.py`)

Six tests locking `_unionSet` behavior:

| Test | Verifies |
|---|---|
| `test_unionSetMergesTwoSets` | `{VND} | {THB} == {VND, THB}` |
| `test_unionSetHandlesNoneExisting` | `None | {VND} == {VND}` |
| `test_unionSetHandlesNoneUpdate` | `{VND} | None == {VND}` |
| `test_unionSetHandlesBothNone` | `None | None == set()` |
| `test_unionSetIsIdempotentOnDuplicateCurrency` | `{VND} | {VND} == {VND}` |
| `test_unionSetAccumulatesAcrossMultipleCalls` | Multi-turn simulation: VND → VND+THB → VND+THB+IDR |

## Decisions Made

### Boolean-flag Decomposition vs Single Phase Enum

ROADMAP Criterion 5 mentions a "phase field." CONTEXT.md's hook architecture uses individual boolean flags instead of a single phase enum. The flags approach was chosen because:

1. **Composability** — `clarificationPending=True` + `askHumanCount=2` gives more routing information than `phase="clarification"` alone
2. **No exhaustion** — Adding new routing signals doesn't require expanding an enum and updating all match/case branches
3. **LangGraph alignment** — Individual fields with reducers map directly to partial state updates from nodes

The module docstring documents this decision explicitly, satisfying ROADMAP Criterion 5 by decomposition.

### Default Convention

TypedDict fields carry no default factories. Consuming code uses `.get("field", default)` pattern, which matches the existing convention in the codebase (e.g., `state.get("claimSubmitted", False)` in graph.py).

## RemoveMessage / REMOVE_ALL_MESSAGES Verification

Runtime verification against installed LangGraph 1.1.3:

```
from langgraph.graph.message import RemoveMessage, REMOVE_ALL_MESSAGES  → OK
```

Plan 05 (post-model hook, soft-rewrite) can rely on these imports without a dependency surprise.

## Test Results

```
tests/test_state_reducers.py    6/6 passed
tests/test_graph.py             6/6 passed
Full suite:                     253 passed, 4 skipped, 4 pre-existing failures
```

Pre-existing failures are tracked open bugs (intake narrative E2E, extract receipt fields blur test, currency tool error correction, active page indicator) — none caused by this plan.

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash | Type | Description |
|---|---|---|
| `98c92ab` | feat(13-02) | Add _unionSet reducer and six Phase 13 ClaimState fields |
| `a7ea75a` | test(13-02) | Add reducer unit tests for _unionSet |
