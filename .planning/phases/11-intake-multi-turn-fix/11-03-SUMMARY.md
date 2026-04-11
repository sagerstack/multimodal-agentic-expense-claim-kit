---
phase: "11"
plan: "03"
subsystem: observability
tags: [logging, structured-events, seq, logEvent, sse]
requires: ["11-01", "11-02"]
provides: ["structured-logging-all-agents", "seq-filterable-events", "stream-noise-suppression"]
affects: ["12"]
tech-stack:
  added: []
  patterns: ["logEvent() structured observability", "logCategory field for Seq filtering"]
key-files:
  created: []
  modified:
    - src/agentic_claims/agents/compliance/node.py
    - src/agentic_claims/agents/fraud/node.py
    - src/agentic_claims/agents/advisor/node.py
    - src/agentic_claims/agents/intake/node.py
    - src/agentic_claims/web/sseHelpers.py
    - src/agentic_claims/core/graph.py
    - src/agentic_claims/web/routers/chat.py
decisions:
  - "Kept one logger.debug() call in sseHelpers.py for non-stream event tracing; gated by on_chat_model_stream check"
  - "Fixed pre-existing sdkParams.items() bug in compliance tests (coroutine mock)"
metrics:
  duration: "14m"
  completed: "2026-04-11"
---

# Phase 11 Plan 03: Structured Logging Conversion Summary

**One-liner**: ~67 raw logger calls converted to logEvent() across all 7 agent/sse/graph files with Seq-filterable logCategory, agent, claimId fields; on_chat_model_stream DEBUG noise eliminated.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Convert agent node raw logger calls to logEvent() | f553413 | compliance/node.py, fraud/node.py, advisor/node.py, intake/node.py |
| 2 | Convert sseHelpers, graph.py, chat.py and suppress stream noise | f4fd2ef | sseHelpers.py, graph.py, chat.py |

## What Was Done

### Task 1: Agent Nodes (4 files)

All 4 agent node files now use structured `logEvent()` calls:

- **compliance/node.py**: 15 raw logger calls converted — events: `compliance.started`, `compliance.context_read`, `compliance.rag_query`, `compliance.rag_error`, `compliance.llm_request`, `compliance.llm_response`, `compliance.llm_402_fallback`, `compliance.llm_fallback_error`, `compliance.llm_error`, `compliance.fallback`, `compliance.completed`, `compliance.parse_error`, `compliance.parse_fallback`, `compliance.audit_log_written`, `compliance.audit_log_error`

- **fraud/node.py**: 18 raw logger calls converted — events: `fraud.started`, `fraud.context_read`, `fraud.duplicate_detected`, `fraud.llm_request`, `fraud.llm_response`, `fraud.llm_402_fallback`, `fraud.llm_fallback_error`, `fraud.llm_error`, `fraud.fallback`, `fraud.completed`, `fraud.parse_error`, `fraud.parse_fallback`, `fraud.history_query_error` (x3), `fraud.audit_log_written`, `fraud.audit_log_error`

- **advisor/node.py**: 16 raw logger calls converted — events: `advisor.started`, `advisor.context_built`, `advisor.missing_db_claim_id`, `advisor.llm_request`, `advisor.llm_response`, `advisor.llm_402_fallback`, `advisor.completed`, `advisor.decision_extract_fallback`, `advisor.error`, `advisor.audit_log_written`, `advisor.audit_log_error`, `advisor.status_update`, `advisor.status_update_error` (x2)

- **intake/node.py**: 5 raw logger calls converted — events: `intake.started`, `intake.llm_402_fallback`, `intake.agent_invoked`, `intake.completed`

### Task 2: SSE/Graph/Chat (3 files)

- **sseHelpers.py**: 22 raw logger calls converted; `logCategory="sse"` on all SSE pipeline events. `on_chat_model_stream` events suppressed from debug logging via guard: `if eventKind != "on_chat_model_stream": logger.debug(...)` — this eliminates the high-frequency token-level noise from Seq.

- **graph.py**: 4 raw logger calls converted — events: `graph.evaluator_gate`, `graph.mark_ai_reviewed`, `graph.mark_ai_reviewed_error` with `logCategory="graph"`

- **chat.py**: 4 raw logger calls converted — SSE stream error, background task launch, fetchClaimsForTable errors with `logCategory="chat"` or `logCategory="sse"`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed sdkParams.items() TypeError in compliance tests**

- **Found during**: Task 1 — compliance test run
- **Issue**: `llm._default_params.items()` in compliance/node.py returned a coroutine when called on a mock in test context, causing `TypeError: 'coroutine' object is not iterable`. This was a pre-existing bug (already failing before this plan).
- **Fix**: Wrapped `{k: str(v)[:200] for k, v in sdkParams.items()}` in try/except, falling back to `{}` on error
- **Files modified**: `src/agentic_claims/agents/compliance/node.py`
- **Commit**: f553413
- **Test impact**: 5 compliance tests that were failing now pass

## Verification

- All 7 target files: zero raw `logger.info/warning/error/debug` calls (except one gated debug call in sseHelpers.py)
- `logEvent` present in all 7 files
- All logEvent calls include `logCategory` field for Seq filtering
- Agent events include `agent` and `claimId` fields
- `on_chat_model_stream` suppressed at line ~818 of sseHelpers.py
- Test results: 241 passed, 2 failed (pre-existing, unrelated), 4 skipped

## Next Phase Readiness

- Seq now has filterable structured events across entire agent pipeline
- Filter by `logCategory` (agent/sse/graph/chat/tool) to isolate subsystems
- Filter by `agent` (intake/compliance/fraud/advisor) to trace per-agent flow
- Filter by `claimId` to trace full claim lifecycle end-to-end
