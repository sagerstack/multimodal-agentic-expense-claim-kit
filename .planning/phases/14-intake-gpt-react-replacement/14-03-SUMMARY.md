---
phase: 14
plan: "03"
subsystem: intake-gpt-agent
tags: [langgraph, deterministic-routing, workflow-gates, tdd, reasonNode]
requires:
  - "14-02"
provides:
  - "Three deterministic runtime bypasses in reasonNode: field_confirmation_answered->searchPolicies, policy_answered(violations)->policy_justification, policy_justification_answered->submit_confirmation"
affects:
  - "14-04"
  - "14-05"
  - "14-06"
tech-stack:
  added: []
  patterns:
    - "Deterministic runtime bypass before LLM call: check currentStep + pendingInterrupt==None + result-not-yet-present → build synthetic AIMessage with tool_calls → return without invoking LLM"
key-files:
  created: []
  modified:
    - src/agentic_claims/agents/intake_gpt/graph.py
    - tests/test_intake_gpt.py
decisions:
  - "Gate 3 replaces the prior policy_justification_answered->submitClaim direct bypass. The new chain is: policy_justification_answered -> submit_confirmation -> submit_confirmation_answered -> submitClaim. This inserts an explicit user consent step before submission."
  - "_pendingInterruptFromToolCalls has no kind allowlist — accepts any kind unconditionally. No widen required. G0a and G0b passed immediately."
  - "Compliant-path submit_confirmation (no violation) stays LLM-driven in this plan. Gate 2 only fires when _hasPolicyViolation returns True. The LLM handles the compliant summary phrasing."
  - "lastResolution.outcome==answer guard added to submit_confirmation_answered->submitClaim bypass to prevent declined confirmations from triggering submitClaim."
metrics:
  duration: "4m 13s"
  completed: "2026-04-14"
---

# Phase 14 Plan 03: Deterministic reasonNode Gates Summary

Three deterministic runtime gates hardened in `reasonNode` so the LLM cannot skip or narrate past workflow transitions. Each gate inspects `currentStep`, verifies `pendingInterrupt is None`, and emits a synthetic `AIMessage` with tool_calls — the LLM is never invoked at these checkpoints.

## Gates Implemented

### Gate 1: field_confirmation_answered -> searchPolicies

**Trigger**: `currentStep == "field_confirmation_answered"` + `pendingInterrupt is None` + `policySearchResults` absent + `lastResolution.outcome == "answer"`

**Action**: `_buildSearchPoliciesAiMessage` constructs a `searchPolicies` query from `slots.claimData.category` and `slots.claimData.amountSgd`. Advances `currentStep` to `"searching_policies"`.

### Gate 2: policy_answered (with violations) -> policy_justification

**Trigger**: `currentStep == "policy_answered"` + `pendingInterrupt is None` + `_hasPolicyViolation(slots)` returns True

**Action**: `_buildPolicyJustificationAiMessage` emits `requestHumanInput(kind="policy_justification")`. Sets `pendingInterrupt` via `_pendingInterruptFromToolCalls`. Advances `currentStep` to `"policy_justification"`, `status` to `"blocked"`.

Violation detection: explicit `violation: True` marker in `policySearchResults` OR `claimAmountSgd > policyCap` numeric comparison.

Compliant path (no violation) falls through to the LLM — intentional, per plan scope.

### Gate 3: policy_justification_answered -> submit_confirmation

**Trigger**: `currentStep == "policy_justification_answered"` + `pendingInterrupt is None` + `submissionResult` absent + `lastResolution.outcome == "answer"`

**Action**: `_buildSubmitConfirmationAiMessage` emits `requestHumanInput(kind="submit_confirmation")` with a summary contextMessage (category, amount, merchant, justification). Sets `pendingInterrupt`. Advances `currentStep` to `"submit_confirmation"`, `status` to `"blocked"`.

This replaces the prior direct `policy_justification_answered -> submitClaim` bypass. The chain is now: `policy_justification_answered -> submit_confirmation -> submit_confirmation_answered -> submitClaim`.

## `_pendingInterruptFromToolCalls` Kind Handling

No allowlist present. The helper accepts any `requestHumanInput` tool_call and reads `args["kind"]` unconditionally. G0a (`policy_justification`) and G0b (`submit_confirmation`) passed on first run — no code change required.

## Existing Bypass Updates

- Removed `"policy_justification_answered"` from the `submit_confirmation_answered` trigger set (Gate 3 now owns that transition).
- Added `lastResolution.outcome == "answer"` guard to prevent a declined `submit_confirmation` from firing `submitClaim`.

## Existing Test Update

`test_reasonNodeSkipsLlmAndCallsSubmitClaimAfterPolicyJustificationWithoutPrebuiltDraft` was renamed and updated to `test_reasonNodeSkipsLlmAndRequestsSubmitConfirmationAfterPolicyJustification`. The test now asserts Gate 3 behavior (`submit_confirmation` interrupt) instead of the old direct-to-`submitClaim` path. State fixture updated to include `claimData.amountSgd` so `_buildSubmitConfirmationAiMessage` can build the contextMessage.

## Test Results

| Phase | Tests | Result |
|-------|-------|--------|
| G0a prerequisite (policy_justification helper) | 1 | Pass (immediate — no allowlist) |
| G0b prerequisite (submit_confirmation helper) | 1 | Pass (immediate — no allowlist) |
| G1 gate (searchPolicies after field_confirmation_answered) | 1 | RED then GREEN |
| G2 gate (policy_justification when violations) | 1 | RED then GREEN |
| G3 gate (submit_confirmation after justification) | 1 | RED then GREEN |
| Prior tests (29 pre-existing) | 29 | All pass |
| **Total** | **34** | **34/34 PASS** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Existing test `test_reasonNodeSkipsLlmAndCallsSubmitClaimAfterPolicyJustificationWithoutPrebuiltDraft` broken by Gate 3**

- **Found during**: GREEN phase
- **Issue**: The existing test asserted `policy_justification_answered -> submitClaim` directly, which is the exact behavior Gate 3 replaces. After the gate was added, the test failed because `submit_confirmation` is now requested instead.
- **Fix**: Renamed test to `test_reasonNodeSkipsLlmAndRequestsSubmitConfirmationAfterPolicyJustification`. Updated state fixture to include `claimData.amountSgd` so `_buildSubmitConfirmationAiMessage` can build a contextMessage. Updated assertions to verify `submit_confirmation` kind and `pendingInterrupt` state.
- **Files modified**: `tests/test_intake_gpt.py`
- **Commit**: 7c40dd1

## Next Phase Readiness

Gate 4 (compliant-path submit_confirmation — no policy violation) remains LLM-driven. If LLM narration bypasses it in practice, add a 4th deterministic gate in Plan 14-06. The current 3 gates cover the violation pathway completely.
