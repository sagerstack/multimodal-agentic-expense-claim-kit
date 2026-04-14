---
phase: 12-deepeval-ragas-evaluation-suite
plan: 02
subsystem: testing
tags: [playwright, subagent, capture, enrichment, psycopg, qdrant, benchmarks, evaluation]

# Dependency graph
requires:
  - phase: 12-01
    provides: EvalConfig, BENCHMARKS dataset, eval package structure

provides:
  - eval/src/capture/subagent.py with buildCapturePrompt, buildDuplicateCapturePrompt
  - eval/src/capture/enrichment.py with enrichCapturedResult, enrichAllResults
  - saveCapturedResult/loadCapturedResult/loadAllCapturedResults persistence helpers

affects:
  - 12-04 (runner imports buildCapturePrompt, saveCapturedResult, enrichCapturedResult)

# Tech tracking
tech-stack:
  added:
    - psycopg (async PostgreSQL -- already in project, now used by eval module)
    - httpx (async HTTP for Qdrant -- already in project, now used by eval module)
  patterns:
    - "Subagent prompt builder: natural-language Playwright instructions per benchmark"
    - "Two-session duplicate pattern for ER-013 (buildDuplicateCapturePrompt)"
    - "Enrichment queries claims + audit_log then re-fetches Qdrant chunks by section ref"
    - "Anti-pattern warning in every prompt: #aiMessages = system under test, not instructions"

key-files:
  created:
    - eval/src/capture/subagent.py
    - eval/src/capture/enrichment.py

# Decisions
key-decisions:
  - "Credentials sourced exclusively from EvalConfig.evalUsername / evalPassword -- no hardcoded values"
  - "ER-013 uses dedicated buildDuplicateCapturePrompt for two-session pattern (logout between sessions)"
  - "Enrichment step overrides agentDecision with authoritative DB value when available"
  - "Qdrant queries use scroll API with section metadata filter on expense_policies collection"
  - "psycopg (not asyncpg) used for DB queries -- already declared in project dependencies"

# Metrics
duration: 17min
completed: 2026-04-11
---

# Phase 12 Plan 02: Capture Layer -- Subagent Prompts and DB Enrichment Summary

**Playwright prompt builder for all 20 benchmarks with credentials from EvalConfig, two-session ER-013 duplicate pattern, and async DB+Qdrant enrichment for compliance/fraud/advisor findings**

## Performance

- **Duration:** 17 min
- **Started:** 2026-04-11T15:04:40Z
- **Completed:** 2026-04-11T15:21:40Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments

- `buildCapturePrompt(benchmark, config)` produces a complete natural-language Playwright MCP prompt for all 20 benchmarks, with DOM selectors verified against the real `chat.html` template (`#doneTarget`, `#aiMessages`, `#interruptTarget`, `input[type="file"][name="receipt"]`, `textarea[name="message"]`)
- Anti-pattern warning embedded in every prompt: `#aiMessages` is the system under test, not instructions for the subagent
- `buildDuplicateCapturePrompt(benchmark, config)` handles ER-013 two-session pattern: Session 1 submits and notes claim number, Session 2 resubmits and captures the duplicate detection output
- Credentials sourced from `config.evalUsername` / `config.evalPassword` -- no hardcoded values anywhere
- `enrichCapturedResult(capturedResult, dbUrl, qdrantUrl)` queries `claims` table for `compliance_findings`, `fraud_findings`, `advisor_decision`, `advisor_findings` via `psycopg` async
- Policy chunk re-fetch: queries `audit_log` for `policy_check` action rows, extracts `policyRefs`, then scrolls Qdrant `expense_policies` collection by section filter
- All edge cases verified: missing claimId, DB unreachable, Qdrant unreachable -- all log warnings and return gracefully without crashing
- Result persistence: `saveCapturedResult`, `loadCapturedResult`, `loadAllCapturedResults` with JSON serialization

## Task Commits

1. **Task 1: Build subagent prompt builder for Playwright capture** - `5240009` (feat)
2. **Task 2: Build DB enrichment module for post-capture data** - `03669f4` (feat)

## Files Created/Modified

- `eval/src/capture/subagent.py` - Prompt builder, duplicate variant, persistence helpers (452 lines)
- `eval/src/capture/enrichment.py` - Async DB + Qdrant enrichment (332 lines)

## Decisions Made

- **Credentials from EvalConfig only**: `config.evalUsername` and `config.evalPassword` are interpolated into the prompt at runtime. No strings like `employee1` or `password123` appear in source.
- **ER-013 two-session design**: Uses `/logout` between sessions to clear the session cookie. Session 2 output is what gets scored (the duplicate detection response).
- **psycopg over asyncpg**: Project already uses psycopg (declared in pyproject.toml); no new dependency needed.
- **Qdrant scroll API**: Used `POST /collections/expense_policies/points/scroll` with a `section` metadata filter to pull relevant policy chunks.
- **advisorReasoning parsing**: `_parseAdvisorReasoning()` tries common keys (`reasoning`, `rationale`, `explanation`, `summary`, `message`) before falling back to full JSON serialization.
- **DB enrichment overrides agentDecision**: If `advisor_decision` column is populated in the DB, it replaces the browser-scraped `agentDecision` value (DB is authoritative).

## Deviations from Plan

None -- plan executed exactly as written.

## Next Phase Readiness

- Plan 12-03 (metrics module) can proceed independently of the capture layer
- Plan 12-04 (runner) imports `buildCapturePrompt`, `saveCapturedResult`, `enrichCapturedResult` from the modules built here
- **Note**: ER-018 `18.pdf` is still missing from `eval/invoices/` -- capture will return the file-not-found error JSON gracefully (handled in prompt instructions)

---
*Phase: 12-deepeval-ragas-evaluation-suite*
*Completed: 2026-04-11*
