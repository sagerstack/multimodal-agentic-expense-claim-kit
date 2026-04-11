---
phase: 11
plan: 01
subsystem: intake-agent
tags: [langgraph, interrupt, multi-turn, system-prompt, session-management]

dependency-graph:
  requires: []
  provides:
    - askHuman tool with LangGraph interrupt
    - v3 system prompt with conditional multi-turn flow
    - auto-reset session on new claim
  affects:
    - plan: 11-02
      reason: SSE interrupt/resume pipeline reads askHuman interrupt signal
    - plan: 11-03
      reason: TURN ROUTING and prompt quality improvements build on v3

tech-stack:
  added: []
  patterns:
    - LangGraph interrupt() for multi-turn agent pausing
    - Conditional routing in system prompt (Phase 1 always interrupts, Phase 2 only on violations)

key-files:
  created:
    - src/agentic_claims/agents/intake/tools/askHuman.py
    - src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v3.py
  modified:
    - src/agentic_claims/agents/intake/node.py
    - src/agentic_claims/web/sseHelpers.py
    - src/agentic_claims/web/routers/chat.py
    - tests/test_intake_agent.py
    - tests/test_sse_infrastructure.py

decisions:
  - "Auto-reset session on POST /chat/message when claimSubmitted=True in prior graph state — avoids requiring a separate explicit reset button for consecutive claims"
  - "v2 prompt retained as reference; v3 is new file — no in-place modification to allow diffing"
  - "storeImage call moved after auto-reset block so images are stored under the correct (possibly new) claimId"

metrics:
  duration: 10 minutes
  completed: 2026-04-11
---

# Phase 11 Plan 01: askHuman Interrupt Tool + v3 System Prompt Summary

Multi-turn confirmation flow restored to intake agent. Agent now pauses after receipt extraction for user confirmation, and conditionally pauses again only when policy violations are found. Auto-reset session logic handles consecutive claims without user action.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create askHuman tool, wire into agent, add TOOL_LABELS | ca7c73f | tools/askHuman.py, node.py, sseHelpers.py, test_intake_agent.py |
| 2 | Create v3 system prompt with conditional TURN ROUTING | 86691a1 | agentSystemPrompt_v3.py, node.py, test_sse_infrastructure.py |
| 3 | Auto-reset session after claim submission | 8d0ae1e | routers/chat.py |

## Decisions Made

1. **Auto-reset on POST not on SSE**: The session reset happens in `postMessage()` at the HTTP layer, not in the SSE stream handler. This means the reset is deterministic and occurs before any graph invocation — the new thread_id is used from the start of the new claim.

2. **Image storage after reset**: Receipt image bytes are read and base64-encoded immediately (before auto-reset check), but `storeImage()` is deferred until after the auto-reset block. This ensures images are stored under the correct claimId regardless of whether a reset occurred.

3. **Clean policy check = no interrupt**: TURN ROUTING rule 2 explicitly says "If no violations found: proceed directly to Phase 3 — call submitClaim. Do NOT call askHuman." This keeps the happy path fast (3-turn max: upload → confirm → submitted).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed testToolLabelsHasFiveEntries failing after adding 6th tool**

- Found during: Task 1 verification (full test suite)
- Issue: `test_sse_infrastructure.py::testToolLabelsHasFiveEntries` asserted `len(TOOL_LABELS) == 5` but we added askHuman as 6th entry
- Fix: Renamed test to `testToolLabelsHasSixEntries` and updated assertion to `len(TOOL_LABELS) == 6`
- Files modified: `tests/test_sse_infrastructure.py`
- Commit: 86691a1

## Pre-existing Failures (not caused by this plan)

The following 7 test failures were confirmed pre-existing by verifying they fail on `git stash` (clean state before this plan's commits):

- `test_compliance_agent.py` — 5 tests (TypeError in compliance node, unrelated to intake)
- `test_extract_receipt_fields.py::testBlurryImageReturnsError` — assertion error (pre-existing)
- `test_web_pages.py::testActivePageIndicatorDashboard` — assertion error (pre-existing)

## Next Phase Readiness

Phase 11 Plan 02 (SSE interrupt/resume pipeline) is unblocked. The `askHuman` tool now exists and calls `interrupt()` correctly. The SSE handler needs to detect the interrupt signal and resume the graph with the user's response.

Prerequisites for 11-02:
- askHuman tool exists and calls langgraph.types.interrupt ✓
- node.py has 6 tools ✓
- Session auto-reset handles new claims ✓
