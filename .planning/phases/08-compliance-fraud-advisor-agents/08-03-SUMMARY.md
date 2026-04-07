---
plan: 08-03
status: complete
completed: 2026-04-06
---

# Plan 08-03 Summary: Fraud Agent — Tool Call Pattern

## Tasks Completed

### Task 1: Fraud agent node, prompt, and query helpers
- `agents/fraud/prompts/fraudSystemPrompt.py`: FRAUD_SYSTEM_PROMPT — detection rules: duplicate (high), date proximity (medium), frequency anomaly (medium), amount anomaly (low), legit (default)
- `agents/fraud/tools/queryClaimsHistory.py`:
  - `_sanitize(value)`: escapes `'` → `''` for SQL injection prevention
  - `exactDuplicateCheck`: sanitizes employeeId, merchant, receiptDate; casts amount to float
  - `recentClaimsByEmployee`: sanitizes employeeId; casts days to int
  - `claimsByMerchantAndEmployee`: sanitizes both string values
- `agents/fraud/node.py`: full Tool Call pattern
  - Uses `buildAgentLlm` and `extractJsonBlock` from shared package
  - `_isExactDuplicate`: short-circuits LLM when exact match found
  - `_computeAverage`, `_countMerchantIn30Days`: statistics helpers
  - `_runDbQueries`: 3 parallel-safe queries, each with try/except
  - LLM call with 402 fallback
  - `_writeAuditLog`: `insertAuditLog` with action=fraud_check (non-fatal)

### Task 2: Unit tests
- `tests/test_fraud_agent.py`: 5 tests
  - `testFraudLegitNoDuplicates`: empty DB → legit verdict, LLM called
  - `testFraudExactDuplicateShortCircuit`: duplicate row returned → verdict=duplicate, LLM assert_not_called()
  - `testFraudSuspiciousFrequencyAnomaly`: 5 recent claims → suspicious with frequency_anomaly flag
  - `testFraudAuditLogWritten`: verifies insertAuditLog called with action=fraud_check, claimId=12
  - `testFraudSanitizePreventsInjection`: `_sanitize("O'Reilly")` → `"O''Reilly"`, injection string neutralised

- `tests/test_graph.py`: updated routing assertions ("Fraud Agent" → "Fraud Check")

## Commits
- `130e69f` feat(08-03): fraud agent — Tool Call pattern with duplicate detection, SQL sanitization, audit logging

## Test Results
- 184 passed, 0 failures (pre-existing E2E error unchanged)

## Success Criteria Verification
1. 3 DB queries with sanitized SQL — PASS
2. Exact duplicate short-circuits LLM — PASS (verified by assert_not_called)
3. SQL injection prevention via _sanitize — PASS (dedicated test)
4. 402 LLM fallback — PASS
5. Audit log entry with action=fraud_check — PASS
6. 5 unit tests all pass — PASS
