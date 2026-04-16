---
phase: 14-intake-gpt-react-replacement
plan: "02"
subsystem: agent
tags: [intake-gpt, langgraph, interrupt, side-question, classification]

# Dependency graph
requires:
  - phase: 14-01
    provides: 7 failing tests pinning interrupt classifier contract (TDD red phase)
provides:
  - Symmetric _classifyInterruptReply with pure-logic side-question detection
  - Implemented interruptResolutionNode (was a no-op stub)
  - Side-question preservation in applyToolResultsNode across all interrupt kinds
  - Bug C fix: intakeFindings.justification written verbatim even when intakeFindings was empty
affects:
  - 14-03 through 14-07 (all depend on correct interrupt classification contract)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-logic side-question detection: trailing '?' OR starts with interrogative word (no LLM needed)"
    - "Symmetric interrupt classification: negative tokens never yield 'answer' for any kind"
    - "Side-question guard: early return in applyToolResultsNode preserves pendingInterrupt"

key-files:
  created: []
  modified:
    - src/agentic_claims/agents/intake_gpt/graph.py

key-decisions:
  - "Negative tokens added to _NEGATIVE_TOKENS: 'skip' and 'never mind' (semantically negative, needed for policy_justification test coverage)"
  - "_buildRuntimeContext Task 3 is a no-op: JSON serialization of intakeState already surfaces pendingInterrupt.kind, question, and lastResolution.outcome natively"
  - "interruptResolutionNode writes lastResolution but does NOT clear pendingInterrupt — that ownership stays in applyToolResultsNode when ToolMessage arrives"
  - "side_question detection runs BEFORE negative/affirmative token checks so interrogatives always win (e.g. 'is this correct?' → side_question, not answer)"

patterns-established:
  - "Token constant guard pattern: _containsNegativeToken / _containsAffirmativeToken helpers for multi-word token matching"
  - "Early return guard in ToolMessage handler to prevent state mutation on side_question outcome"

# Metrics
duration: 3min
completed: 2026-04-14
---

# Phase 14 Plan 02: Interrupt Classifier Green Phase Summary

**Symmetric `_classifyInterruptReply`, implemented `interruptResolutionNode`, and side-question preservation — 4 failing tests turned green, all 29 pass**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T12:18:44Z
- **Completed:** 2026-04-14T12:21:56Z
- **Tasks:** 2 (Task 3 was a no-op verification)
- **Files modified:** 1

## Accomplishments

- Closed Bug A (symmetric classification): negative tokens ("no", "nope", "cancel", "skip", "never mind") never fall through to "answer" for any interrupt kind
- Closed Bug A (side-question preservation): pure-logic interrogative detection runs before token checks; pendingInterrupt stays set on side_question across all interrupt kinds
- Closed Bug C (verbatim justification): removed `if intakeFindings:` guard that was silently discarding justification text when intakeFindings was empty
- `interruptResolutionNode` is fully implemented — classifies the latest HumanMessage against pendingInterrupt, writes `lastResolution`, updates workflow status

## Task Commits

1. **Task 1: Symmetric _classifyInterruptReply** - `b675342` (fix)
2. **Task 2: Implement interruptResolutionNode + side-question guard** - `bf750f1` (feat)
3. **Task 3: _buildRuntimeContext no-op** - no commit needed (test already passing)

## New Module-Level Constants Introduced

| Constant | Value | Purpose |
|----------|-------|---------|
| `_INTERROGATIVE_PREFIXES` | `("what", "why", "how", "when", "who", "is", "can", "does", "will")` | Pure-logic side-question detection |
| `_NEGATIVE_TOKENS` (extended) | added `"skip"`, `"never mind"` | Cover policy_justification negative replies |

## New Helper Functions Introduced

| Function | Purpose |
|----------|---------|
| `_isSideQuestionText(text)` | Trailing `?` OR starts with interrogative word |
| `_containsNegativeToken(lowered)` | Exact match or multi-word token substring check |
| `_containsAffirmativeToken(lowered)` | Exact match or multi-word token substring check |

## Files Modified

- `src/agentic_claims/agents/intake_gpt/graph.py` — all changes

## Test Coverage

| Before (14-01 delivered) | After |
|--------------------------|-------|
| 25 passing, 4 failing | 29 passing, 0 failing |

Bugs closed:
- **Bug A (symmetric)**: `test_classifyInterruptReplyRejectsNegativeTokenForFieldConfirmation`, `test_classifyInterruptReplyRejectsNegativeTokenForPolicyJustification`
- **Bug A (side-question)**: `test_classifyInterruptReplyDetectsSideQuestionForPolicyJustification`, `test_interruptResolutionNodePreservesPendingInterruptOnSideQuestion`
- **Bug C (verbatim)**: `test_applyToolResultsNodeStoresVerbatimJustificationText`

## Decisions Made

- "skip" and "never mind" added to `_NEGATIVE_TOKENS` — they are semantically negative and required for the policy_justification test coverage
- Task 3 (`_buildRuntimeContext`) confirmed as no-op: the function already serializes the full intakeState dict as JSON, which naturally includes `pendingInterrupt.kind`, `pendingInterrupt.question`, and `lastResolution.outcome`. The test assertions were already satisfied.
- `interruptResolutionNode` does NOT mutate pendingInterrupt for answer/cancel_claim outcomes — ownership of that state advancement stays in `applyToolResultsNode` when the ToolMessage arrives. This preserves the existing flow contract.

## Deviations from Plan

None — plan executed exactly as written. Task 3 correctly identified as a no-op.

## Issues Encountered

None.

## Next Phase Readiness

- All 29 tests in `tests/test_intake_gpt.py` passing
- `_classifyInterruptReply` contract is fully locked in — Plan 14-06 can safely re-classify field_confirmation + negative token to `correction_requested` without disturbing other branches
- `interruptResolutionNode` is functional and writing `lastResolution` for LLM context injection
- Side-question preservation chain is complete: classifier → interruptResolutionNode → applyToolResultsNode all honour the invariant

---
*Phase: 14-intake-gpt-react-replacement*
*Completed: 2026-04-14*
