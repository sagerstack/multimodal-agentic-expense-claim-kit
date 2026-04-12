---
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
plan: "06"
subsystem: intake-agent
tags: [langgraph, wrapper-graph, subgraph, react-agent, routing, hooks, escalation, state]

dependency_graph:
  requires:
    - 13-01 (convertCurrency {supported: false} contract)
    - 13-02 (ClaimState six Phase 13 flag fields + _unionSet reducer)
    - 13-03 (INTAKE_AGENT_SYSTEM_PROMPT_V5)
    - 13-04 (preModelHook, postModelHook, humanEscalationNode)
    - 13-05 (postToolFlagSetter, submitClaimGuard)
  provides:
    - buildIntakeSubgraph: create_react_agent with v5 + hooks + version='v2' + checkpointer=None
    - IntakeSubgraphState: inner schema with Phase 13 flag fields shared with ClaimState
    - _mergeSubgraphResult: explicit-whitelist result → outer ClaimState translator
    - preIntakeValidator: outer pre-node (turnIndex increment, flag setters)
    - postIntakeRouter: conditional edge (validatorEscalate OR askHumanCount > 3 → humanEscalation)
    - intakeNode: rewritten to invoke subgraph via _getIntakeSubgraph
    - humanEscalation: wired as terminal node in main graph topology
  affects:
    - 13-07 (formal unit tests for wrapper graph and router)
    - 13-08 (integration tests for full hook chain)
    - 13-09 (end-to-end integration tests)

tech_stack:
  added: []
  patterns:
    - Wrapper-graph pattern: outer StateGraph wraps create_react_agent subgraph
    - IntakeSubgraphState: shared field names with ClaimState enable subgraph→outer merge
    - Delta-form messages in _mergeSubgraphResult: slice from priorCount to avoid duplicates
    - _intakeConditionalRouter: composes postIntakeRouter + evaluatorGate inline

key_files:
  created: []
  modified:
    - src/agentic_claims/agents/intake/node.py
    - src/agentic_claims/core/graph.py
    - src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py
    - tests/test_intake_agent.py
    - tests/test_graph.py

decisions:
  - "messages delta form chosen over full-list form: _mergeSubgraphResult slices result['messages'][priorCount:] and returns only new messages so the outer add_messages reducer appends without duplicates"
  - "phase field absent from IntakeSubgraphState: 13-02 rejected single-enum in favor of boolean-flag decomposition (clarificationPending + askHumanCount + unsupportedCurrencies); phase would have been redundant"
  - "_intakeConditionalRouter inline composition: postIntakeRouter returns 'humanEscalation' or 'continue'; when 'continue', evaluatorGate is called inline and returns 'submitted'/'pending' — single add_conditional_edges call maps all three outcomes"
  - "No secondary checkpointer: buildIntakeSubgraph passes checkpointer=None per 13-RESEARCH.md §7; outer graph's AsyncPostgresSaver remains the single persistence owner"
  - "getIntakeAgent retained: existing function kept for backward compat with tests that may still reference it; production traffic flows through _getIntakeSubgraph"
  - "_buildLlmAndTools extracted: shared factory for both getIntakeAgent and intakeNode, avoids duplication of ChatOpenRouter + tools construction"

metrics:
  duration: "~13 minutes"
  started: "2026-04-12T15:10:00Z"
  completed: "2026-04-12"
  tests_added: 0
  tests_updated: 14
  tests_passing: 261
---

# Phase 13 Plan 06: Wrapper Graph Wiring Summary

**One-liner:** Keystone wiring plan — assembled intake subgraph (v5 + preModelHook + postModelHook + checkpointer=None) inside outer StateGraph with preIntakeValidator → intakeSubgraph → postIntakeRouter; humanEscalation now terminal node in main graph.

## Performance

- **Duration:** ~13 minutes
- **Started:** 2026-04-12T15:10:00Z
- **Completed:** 2026-04-12
- **Tasks:** 2 (Task 1a subgraph factory + 1b outer wrapper; Task 2 graph.py wiring)
- **Tests updated:** 14 (test_intake_agent.py: 11 updated; test_graph.py: 1 updated)
- **Tests passing:** 261 (4 pre-existing failures unchanged)

## What Was Built

### Final Topology Diagram

```
MAIN GRAPH (outer compile, AsyncPostgresSaver checkpointer):

  START
    │
    ▼
  preIntakeValidator        (outer pre-node: turnIndex++, postToolFlagSetter, submitClaimGuard)
    │
    ▼
  intake                    (intakeNode: invokes create_react_agent subgraph)
    │
    ├─ _intakeConditionalRouter
    │     postIntakeRouter → "humanEscalation" (validatorEscalate OR askHumanCount > 3)
    │     postIntakeRouter → "continue" → evaluatorGate → "submitted" / "pending"
    │
    ├── humanEscalation ──→ END                (terminal: writes escalated status)
    │
    ├── postSubmission ──→ compliance ─┐
    │         │          → fraud ──────┤→ markAiReviewed → advisor → END
    │         └──────────→ debugLlm ──┘
    │
    └── END   (pending path: conversation not yet submitted)

SUBGRAPH (no checkpointer):
  create_react_agent(
    model=llm,
    tools=[6 tools],
    prompt=INTAKE_AGENT_SYSTEM_PROMPT_V5,
    state_schema=IntakeSubgraphState,
    pre_model_hook=preModelHook,
    post_model_hook=postModelHook,
    version="v2",
    checkpointer=None,
  )
```

### IntakeSubgraphState — Exact Shape

```python
class IntakeSubgraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: NotRequired[int]           # required by create_react_agent internals
    unsupportedCurrencies: Annotated[set[str], _unionSet]  # union reducer (13-02)
    clarificationPending: NotRequired[bool]
    validatorRetryCount: NotRequired[int]
    validatorEscalate: NotRequired[bool]
    askHumanCount: NotRequired[int]
    claimId: NotRequired[str]       # read-only correlation
    threadId: NotRequired[str]      # read-only correlation
    turnIndex: NotRequired[int]     # read-only correlation
```

**Absent by design:** `phase` — 13-02 chose boolean-flag decomposition.

### _mergeSubgraphResult Whitelist

Explicit whitelist (frozenset `_SUBGRAPH_PROPAGATE_KEYS`):

| Key | Handling |
|---|---|
| `messages` | Delta form: `result["messages"][len(state["messages"]):]` |
| `validatorEscalate` | Copy-through if present in result |
| `clarificationPending` | Copy-through if present |
| `validatorRetryCount` | Copy-through if present |
| `askHumanCount` | Copy-through if present |
| `unsupportedCurrencies` | Copy-through as set (outer _unionSet reducer handles accumulation) |
| `claimSubmitted` | Copy-through if present |
| `extractedReceipt` | Copy-through if present |
| `currencyConversion` | Copy-through if present |
| `intakeFindings` | Copy-through if present |
| `status` | Copy-through if present |
| `dbClaimId` | Copy-through if present |
| `claimNumber` | Copy-through if present |
| `violations` | Copy-through if present |

**Invariants:** Keys absent from result are omitted (no defaulting). `remaining_steps` and other create_react_agent internals are silently dropped.

**Messages form chosen: delta.** When the subgraph result contains the full accumulated message list, we take the suffix starting at `len(state["messages"])` so that the outer `add_messages` reducer appends only the NEW messages. This avoids duplicates when the outer state already has prior messages.

### postIntakeRouter + evaluatorGate Composition

`postIntakeRouter` is called first (escalation takes precedence). If it returns `"continue"`, `evaluatorGate` is called inline. The combined function `_intakeConditionalRouter` in `graph.py` maps all three outcomes:

```
intake → _intakeConditionalRouter → {
    "humanEscalation": humanEscalationNode,
    "submitted": postSubmission,
    "pending": END,
}
```

`evaluatorGate` is unchanged — it still reads `claimSubmitted` and returns "submitted"/"pending".

### No Secondary Checkpointer

Confirmed: `buildIntakeSubgraph` passes `checkpointer=None`. The outer `getCompiledGraph` function creates a single `AsyncPostgresSaver` attached to the outer compile. `_getIntakeSubgraph` returns a compiled agent graph with no persistence of its own.

## Commits

| # | Type | Hash | Description |
|---|---|---|---|
| 1a | feat(13-06) | 7348cb9 | Define IntakeSubgraphState and buildIntakeSubgraph factory |
| 1b | feat(13-06) | e8710d7 | Rewrite intakeNode + _mergeSubgraphResult + preIntakeValidator + postIntakeRouter |
| 2 | feat(13-06) | 98c21e8 | Wire preIntakeValidator and humanEscalation into main graph topology |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan whitelist included `phase` field**

- **Found during:** Task 1a (implementing IntakeSubgraphState)
- **Issue:** Plan 13-06 whitelist included `phase` in both `IntakeSubgraphState` and `_SUBGRAPH_PROPAGATE_KEYS`. However, 13-02-SUMMARY and STATE.md both document that the `phase` field was explicitly rejected: "Boolean-flag decomposition chosen over single phase enum." The `phase` field does not exist in `ClaimState`. Including it would cause a silent write to a non-existent state key.
- **Fix:** Removed `phase` from `IntakeSubgraphState` and `_SUBGRAPH_PROPAGATE_KEYS`. Added doc comment explaining the absence.
- **Files modified:** node.py (IntakeSubgraphState definition, _SUBGRAPH_PROPAGATE_KEYS)

**2. [Rule 3 - Blocking] stale comment in agentSystemPrompt_v5.py**

- **Found during:** Task 1b v4.1 removal verification
- **Issue:** v5 prompt file had a stale comment "Until then, v4_1 remains active in node.py." After Task 1b removed the v4_1 import, this comment was actively misleading.
- **Fix:** Updated the comment to "agentSystemPrompt_v4_1 is no longer imported anywhere in src/."
- **Files modified:** agentSystemPrompt_v5.py

**3. [Rule 2 - Missing Critical] tests needed updating for new code path**

- **Found during:** Task 1b verification (all 8 intakeNode tests failed)
- **Issue:** Existing `test_intake_agent.py` tests patched `getIntakeAgent` but `intakeNode` now routes through `_getIntakeSubgraph`. 8 tests failed immediately. `test_graph.py::test_complianceAndFraudRunInParallel` asserted `allNodes[0] == "intake"` but `preIntakeValidator` runs first.
- **Fix:** Rewrote tests to patch `_buildLlmAndTools` + `_getIntakeSubgraph` via `_patchIntakeNode` context manager helper. Updated graph test assertion to check `allNodes[0] == "preIntakeValidator"`. All 18 tests in both files now pass.
- **Files modified:** tests/test_intake_agent.py, tests/test_graph.py

## Must-Haves Verification

| Must-have truth | Verified |
|---|---|
| buildIntakeSubgraph uses v5 prompt, v2 version, checkpointer=None | TRUE — smoke test passes |
| preIntakeValidator increments turnIndex + applies flag setters | TRUE — implementation correct |
| postIntakeRouter routes on validatorEscalate OR askHumanCount > 3 | TRUE — boundaries explicit (> 3, not >= 3) |
| _mergeSubgraphResult has explicit whitelist | TRUE — frozenset _SUBGRAPH_PROPAGATE_KEYS |
| All six Phase 13 flags propagate subgraph → outer state | TRUE — in whitelist and IntakeSubgraphState |
| humanEscalation wired into main graph; evaluatorGate unchanged | TRUE — _intakeConditionalRouter composes both |
| grep -r agentSystemPrompt_v4_1 src/ returns zero import matches | TRUE — only docstring references remain |
| Existing poetry run pytest tests/test_intake_agent.py tests/test_graph.py passes | TRUE — 18/18 pass |
| 13-06-SUMMARY.md created | TRUE — this file |

## ROADMAP Success Criteria Covered

- **Criterion #1** (hooks wired): preModelHook + postModelHook wired into create_react_agent subgraph via buildIntakeSubgraph
- **Criterion #2** (v5 imported / v4.1 decommissioned): INTAKE_AGENT_SYSTEM_PROMPT_V5 imported; v4.1 import removed from all src/
- **Criterion #5 (routing half)**: postIntakeRouter conditional edge to humanEscalation on askHumanCount > 3

## Next Phase Readiness

- Plan 13-07 (formal unit tests): unblocked — all symbols importable, topology established
- Plan 13-08 (integration tests): unblocked — full hook chain wired
- Plan 13-09 (end-to-end): blocked on Plan 13-07/08 completion

---
*Phase: 13-intake-agent-hybrid-routing-and-bug-fixes*
*Completed: 2026-04-12*
