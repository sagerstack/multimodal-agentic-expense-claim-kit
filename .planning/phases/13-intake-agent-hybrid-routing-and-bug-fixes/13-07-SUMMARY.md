---
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
plan: "07"
subsystem: intake-agent
tags: [testing, hooks, wrapper-graph, preModelHook, postModelHook, postToolFlagSetter, submitClaimGuard, humanEscalation, router, tdd]

dependency_graph:
  requires:
    - 13-01 (convertCurrency {supported: false} contract — regression test confirmed present)
    - 13-04 (preModelHook, postModelHook, humanEscalationNode)
    - 13-05 (postToolFlagSetter, submitClaimGuard — dedicated test files already covering 10+11 tests)
    - 13-06 (buildIntakeSubgraph, _mergeSubgraphResult, preIntakeValidator, postIntakeRouter)
  provides:
    - tests/test_intake_hooks.py: 18 tests covering all four hook modules
    - tests/test_intake_agent.py: 13 new tests covering wrapper-graph topology, boundary conditions,
      integration flow, and humanEscalationNode MCP call
  affects:
    - 13-08 (VND end-to-end integration tests depend on these unit tests as foundation)
    - 13-09 (smoke + regression suite runs after these pass)

tech_stack:
  added: []
  patterns:
    - ephemeral-channel testing (assert 'messages' not in result for preModelHook)
    - boundary condition coverage (askHumanCount == 3 not escalated, > 3 escalated)
    - integration-shaped test with mocked subgraph (preIntakeValidator -> intakeNode -> postIntakeRouter)
    - getSettings() patching for MCP URL verification without env file dependency

key_files:
  created:
    - tests/test_intake_hooks.py
  modified:
    - tests/test_intake_agent.py

decisions:
  - decision: "Representative tests for postToolFlagSetter and submitClaimGuard in test_intake_hooks.py rather than duplicating all 21 tests from dedicated files"
    rationale: "Dedicated test files test_post_tool_flag_setter.py (10 tests) and test_submit_claim_guard.py (11 tests) already provide exhaustive coverage from Plan 13-05 TDD. test_intake_hooks.py confirms the same key contracts without redundancy."
  - decision: "phase key omitted from _mergeSubgraphResult propagation test"
    rationale: "phase field is intentionally absent from ClaimState and _SUBGRAPH_PROPAGATE_KEYS (13-02 chose boolean-flag decomposition over single enum). Plan template's six-flags test was adjusted to five flags."
  - decision: "getSettings() patched in humanEscalationNode test to inject known db_mcp_url"
    rationale: "Test env uses http://localhost:8002/mcp/ (no 'mcp-db' substring). Patching getSettings() with mockDbMcpUrl='http://mcp-db:8000/mcp/' cleanly verifies the URL comes from settings without env file coupling."
  - decision: "_buildSubgraphInput patch removed from integration test"
    rationale: "Function does not exist — intakeNode builds subgraph input inline. Existing _patchIntakeNode helper pattern (patches _buildLlmAndTools + _getIntakeSubgraph) is sufficient and already established in the test file."

metrics:
  duration: "7 minutes"
  completed: "2026-04-12"
---

# Phase 13 Plan 07: Hook and Router Unit Tests Summary

**One-liner:** Unit test suite for all four hook modules (preModelHook, postModelHook, postToolFlagSetter, submitClaimGuard) plus wrapper-graph topology coverage (preIntakeValidator, postIntakeRouter, buildIntakeSubgraph, _mergeSubgraphResult) and humanEscalationNode MCP call assertion.

## What Was Built

### Task 1: tests/test_intake_hooks.py (new file)

18 tests covering all four hook modules:

| Group | Tests | Key assertions |
|-------|-------|----------------|
| preModelHook | 5 | Directive injected with currency name, both directives on both flags, no directives on clean state, directive prepended before base messages, `messages` key ABSENT from return (ephemeral channel) |
| postModelHook | 6 | No-op clean (clarificationPending=False), no-op when tool_calls present, no-op when no AIMessage, soft-rewrite on first drift (ReturnMessage present, retryCount=1), escalate on second drift (validatorEscalate=True), no-op on empty AIMessage content |
| postToolFlagSetter | 4 | Representative: unsupported VND sets flags, supported currency no-ops, askHuman increments count, idempotent on same state |
| submitClaimGuard | 3 | Representative: legitimate ack (tool call + ToolMessage) allowed, hallucinated success escalates, non-submission content no-ops |

### Task 2: tests/test_intake_agent.py (extended, +13 tests)

| Group | Tests | Key assertions |
|-------|-------|----------------|
| preIntakeValidator | 2 | turnIndex incremented by 1, validatorRetryCount reset to 0; initialises to 1 when absent |
| postIntakeRouter | 5 | Escalates on validatorEscalate, escalates on count=4, boundary count=3 stays on "continue", normal state continues, precedence: validatorEscalate over low count |
| buildIntakeSubgraph | 1 | checkpointer=None, version='v2', INTAKE_AGENT_SYSTEM_PROMPT_V5, pre_model_hook and post_model_hook both wired |
| _mergeSubgraphResult | 3 | All 5 Phase 13 flags propagated, absent keys omitted, messages are delta-only (suffix from priorCount) |
| Integration | 1 | preIntakeValidator → intakeNode (mocked subgraph) → postIntakeRouter: validatorEscalate=True propagates through _mergeSubgraphResult and routes to "humanEscalation" |
| humanEscalationNode | 1 | mcpCallTool called once with serverUrl=settings.db_mcp_url, toolName=updateClaimStatus, claimId=42, newStatus=escalated, actor=intake_agent; result has status=escalated, claimSubmitted=False, terminal message, escalationMetadata in intakeFindings |

## Test Count Summary

| File | Pre-existing | New (13-07) | Total |
|------|-------------|-------------|-------|
| tests/test_intake_hooks.py | 0 | 18 | 18 |
| tests/test_intake_agent.py | 12 | 13 | 25 |
| tests/test_intake_tools.py | — | 0 (verified) | — |
| **New tests this plan** | — | **31** | — |

**Plan 01 regression test present:** `test_convertCurrencyReturnsStructuredErrorOnUnsupportedCurrency` confirmed at line 229 of test_intake_tools.py (asserts `result.get("supported") is False`).

## Full Suite Results

```
311 passed, 4 skipped, 5 failed (all pre-existing)
```

Pre-existing failures (not introduced by this plan):
1. `test_e2e_intake_narrative.py::test_intake_narrative_restaurant_receipt` — E2E requiring real Docker services
2. `test_extract_receipt_fields.py::testBlurryImageReturnsError` — Image quality gate disabled
3. `test_intake_e2e_vnd.py::test_vndReceiptTriggersManualRateViaHookDrivenFlow` — Integration test for 13-08 scope; file was untracked pre-existing before this plan's commits
4. `test_plan_001_bug_fixes.py::testCurrencyToolErrorProducesCorrectionMessage` — Plan 01 compatibility test targeting older behavior
5. `test_web_pages.py::testActivePageIndicatorDashboard` — Frontend UI test

## Boundary and Integration Coverage

**Boundary test confirmed:** `test_postIntakeRouterDoesNotEscalateAtExactlyThreeAskHuman` — verifies `askHumanCount == 3` returns `"continue"` (ROADMAP Criterion 5 boundary).

**Integration test confirmed:** `test_preIntakeValidatorThroughIntakeNodeThroughPostIntakeRouterPropagatesFlags` — mocked subgraph returning `{validatorEscalate: True}` propagates through `_mergeSubgraphResult` and is correctly routed to `"humanEscalation"` by `postIntakeRouter` (ROADMAP Criterion 1 correctness proof).

## Deviations from Plan

### Auto-adapted (Rule 1 — implementation reality differs from plan template)

**1. phase key removed from _mergeSubgraphResult test**
- Plan template included `phase` in the six-flag propagation test
- Reality: `phase` is intentionally absent from `_SUBGRAPH_PROPAGATE_KEYS` (13-02 decision: boolean-flag decomposition over enum)
- Fix: test asserts five flags only (validatorEscalate, clarificationPending, validatorRetryCount, askHumanCount, unsupportedCurrencies)

**2. _buildSubgraphInput patch removed from integration test**
- Plan template patched `_buildSubgraphInput` in the integration test
- Reality: function does not exist — intakeNode builds input inline
- Fix: used existing `_buildLlmAndTools` + `_getIntakeSubgraph` patch pattern from `_patchIntakeNode` helper already in the file

**3. humanEscalationNode URL assertion adjusted**
- Plan template: `assert "mcp-db" in callKwargs.get("serverUrl", "")`
- Reality: test env `db_mcp_url = http://localhost:8002/mcp/` — no "mcp-db" substring
- Fix: patched `getSettings()` to inject `db_mcp_url = "http://mcp-db:8000/mcp/"`, then asserted `callKwargs.get("serverUrl") == mockDbMcpUrl`. This correctly verifies the URL comes from `settings.db_mcp_url`, not from a hardcoded literal.

**4. postToolFlagSetter and submitClaimGuard tests are representative (not full duplicates)**
- Plan spec: "Consolidate or supplement as needed"
- Reality: Dedicated files (test_post_tool_flag_setter.py: 10 tests, test_submit_claim_guard.py: 11 tests) already exist from Plan 13-05 TDD. test_intake_hooks.py includes 4 representative tests for each module, confirming contracts without duplication.

## ROADMAP Coverage

- Criterion 5: Boundary condition `askHumanCount == 3` covered — test_postIntakeRouterDoesNotEscalateAtExactlyThreeAskHuman
- Criterion 10: "New tests cover hooks, validator, state reducers" — test_intake_hooks.py (hooks) + test_intake_agent.py (validator preIntakeValidator + _mergeSubgraphResult) fully satisfy

## Next Phase Readiness

Plan 13-08 (VND end-to-end integration test) can proceed. The test_intake_e2e_vnd.py file was already present as an untracked file; its failure indicates it depends on something still in progress in the upstream plans. The unit-test foundation provided by 13-07 is complete.
