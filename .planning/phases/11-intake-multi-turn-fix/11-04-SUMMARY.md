---
phase: 11
plan: "04"
name: "Intake Tools + OpenRouter Structured Logging"
subsystem: observability
tags: [logging, structured-events, logEvent, observability, seq, intake-tools, openrouter]

dependency-graph:
  requires: ["11-03"]
  provides: ["structured logEvent() coverage for all intake tools and openrouter client"]
  affects: ["phase-12"]

tech-stack:
  added: []
  patterns: ["logEvent() with logCategory/toolName/mcpServer fields", "llm lifecycle event pattern"]

file-tracking:
  key-files:
    created: []
    modified:
      - src/agentic_claims/agents/intake/tools/searchPolicies.py
      - src/agentic_claims/agents/intake/tools/convertCurrency.py
      - src/agentic_claims/agents/intake/tools/extractReceiptFields.py
      - src/agentic_claims/agents/intake/tools/getClaimSchema.py
      - src/agentic_claims/infrastructure/openrouter/client.py

decisions:
  - "logCategory='tool' used uniformly for all intake tool events"
  - "logCategory='llm' used for openrouter client lifecycle events"
  - "vlm_fallback event added for extractReceiptFields (not in plan spec but covers the 402-fallback warning call)"
  - "callVlm() not instrumented — delegates to callLlm() which already has the logging; double-logging avoided"

metrics:
  duration: "4 min"
  completed: "2026-04-11"
---

# Phase 11 Plan 04: Intake Tools + OpenRouter Structured Logging Summary

Converted all raw `logger.info/warning/error` calls in 4 intake tool files and added structured LLM lifecycle logging to the OpenRouter client using `logEvent()`.

## What Was Done

### Task 1: 4 Intake Tool Files

Each file received `from agentic_claims.core.logging import logEvent` and all raw logger calls were converted to structured `logEvent()` calls with `logCategory="tool"`, `toolName`, and `mcpServer` where applicable.

**searchPolicies.py** (2 calls converted):
- `tool.searchPolicies.started` — includes query, limit, mcpServer="mcp-rag"
- `tool.searchPolicies.completed` — includes elapsed, resultCount

**convertCurrency.py** (2 calls converted):
- `tool.convertCurrency.started` — includes amount, fromCurrency, toCurrency, mcpServer="mcp-currency"
- `tool.convertCurrency.completed` — includes elapsed

**extractReceiptFields.py** (4 calls converted):
- `tool.extractReceiptFields.started` — includes claimId
- `tool.extractReceiptFields.vlm_fallback` — WARNING level, includes primaryModel, fallbackModel, error (covers the 402-fallback path)
- `tool.extractReceiptFields.vlm_completed` — includes claimId, elapsed
- `tool.extractReceiptFields.completed` — includes claimId, elapsed, hasFields

**getClaimSchema.py** (2 calls converted):
- `tool.getClaimSchema.started`
- `tool.getClaimSchema.completed` — includes elapsed

### Task 2: OpenRouter Client

Added structured LLM call lifecycle logging to `openrouter/client.py` (DEPRECATED but still tested):

- `llm.call_started` — logCategory="llm", model, messageCount (fires before retry loop)
- `llm.call_completed` — logCategory="llm", model, elapsed, attempt (fires on success)
- `llm.call_retrying` — WARNING level, model, attempt, maxRetries, error (non-final failures)
- `llm.call_failed` — ERROR level, model, elapsed, attempt, maxRetries, error (final failure)

`callVlm()` was intentionally not instrumented — it delegates to `callLlm()`, which already has the logging.

## Verification Results

- `poetry run pytest tests/test_openrouter.py -v` — 7/7 passed
- `poetry run pytest tests/test_intake_tools.py tests/test_extract_receipt_fields.py -v` — 24/25 passed (1 pre-existing failure: `testBlurryImageReturnsError` — quality gate is commented out in source, unrelated to this plan)
- Zero raw `logger.info/warning/error` calls in the 4 tool files (only a commented-out block remains)
- All 4 logEvent event names confirmed present in openrouter/client.py

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] vlm_fallback event added for extractReceiptFields**
- **Found during:** Task 1 implementation
- **Issue:** The plan spec listed the warning at line 101 as "quality_rejected" but the actual code at that location is the 402 VLM fallback warning, not a quality check (quality gate is commented out)
- **Fix:** Named the event `tool.extractReceiptFields.vlm_fallback` to accurately reflect the actual code path
- **Files modified:** src/agentic_claims/agents/intake/tools/extractReceiptFields.py

## Next Phase Readiness

Observability gap closure (Issue #0, sub-gaps a and d) is complete. All intake tools and the OpenRouter client now emit structured events filterable by `logCategory`, `toolName`, and `mcpServer` in Seq. Plans 11-03 and 11-04 together cover the full observability scope.
