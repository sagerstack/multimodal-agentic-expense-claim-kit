---
phase: 12-deepeval-ragas-evaluation-suite
plan: 04
subsystem: testing
tags: [deepeval, claude-code-sdk, playwright, scoring, orchestrator, evaluation, runner]

# Dependency graph
requires:
  - phase: 12-01
    provides: EvalConfig, BENCHMARKS dataset, getEvalConfig()
  - phase: 12-02
    provides: buildCapturePrompt, buildDuplicateCapturePrompt, saveCapturedResult, loadAllCapturedResults, enrichCapturedResult
  - phase: 12-03
    provides: getMetricsForBenchmark(), buildTestCase(), all metric classes

provides:
  - eval/src/scoring.py with calculateCategoryScores, calculateWeightedOverall, checkPrimaryTargets, printSummaryTable
  - eval/src/capture/runner.py with runCapture(), runSingleCapture(), parseSubagentResponse()
  - eval/run_eval.py as the user-facing CLI entry point (5-step pipeline)

affects:
  - Human verification checkpoint: `poetry run python eval/run_eval.py --help` and live run against app

# Tech tracking
tech-stack:
  added:
    - claude-code-sdk 0.0.25 (Claude Code Python SDK for subagent invocation)
  patterns:
    - "claude-code-sdk query() with allowed_tools=['mcp__playwright__*'] for browser automation"
    - "ResultMessage.result + AssistantMessage content blocks for response text extraction"
    - "3-tier JSON extraction: plain -> markdown-fenced -> first-balanced-object"
    - "5-step pipeline: CAPTURE -> LOAD -> ENRICH -> SCORE -> REPORT"
    - "stepScore() extracts scores from metric objects post-evaluate() for terminal reporting"

key-files:
  created:
    - eval/src/scoring.py
    - eval/src/capture/runner.py
    - eval/run_eval.py
  modified:
    - eval/src/config.py (api_base -> base_url deprecation fix)
    - pyproject.toml (claude-code-sdk added to dev group)

key-decisions:
  - "claude-code-sdk query() used (not ClaudeSDKClient) -- benchmarks are stateless one-shot captures"
  - "Sequential capture (not parallel) -- avoids browser session conflicts and app overload"
  - "parseSubagentResponse() 3-tier extraction: plain JSON, markdown-fenced, balanced-brace scan"
  - "stepScore() extracts scores from metric.score attributes post-evaluate() -- not from EvaluationResult.test_results (unreliable iteration)"
  - "checkPrimaryTargets() inverts ER-018 score for hallucination rate (0.0 = safe, hallucination rate = 1.0 - score)"
  - "Weighted overall renormalizes when categories are missing from results"

patterns-established:
  - "Runner pattern: runCapture() -> runSingleCapture() -> parseSubagentResponse() with error isolation"
  - "Scoring pattern: calculateCategoryScores() -> calculateWeightedOverall() -> printSummaryTable()"
  - "CLI entry point: argparse --skip-capture / --benchmark / --skip-push / --verbose"

# Metrics
duration: 8min
completed: 2026-04-11
---

# Phase 12 Plan 04: Orchestrator, Scoring, and Capture Runner Summary

**`poetry run python eval/run_eval.py` fully wired: claude-code-sdk subagent capture runner, weighted 5-category scoring with 5 primary targets, formatted terminal summary table, and 5-step CAPTURE -> LOAD -> ENRICH -> SCORE -> REPORT pipeline**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-11T15:17:16Z
- **Completed:** 2026-04-11T15:25:49Z
- **Tasks:** 3
- **Files created:** 3, modified: 2

## Accomplishments

- `calculateCategoryScores()` + `calculateWeightedOverall()` with renormalization for missing categories
- `checkPrimaryTargets()` evaluates 5 primary success targets (field extraction, reconciliation, duplicate detection, hallucination rate, unsafe auto-processing)
- `printSummaryTable()` produces 4-section terminal table (per-benchmark, categories, weighted overall, primary targets)
- `runCapture()` / `runSingleCapture()` drive Claude Code SDK with `mcp__playwright__*` tools (max_turns=50)
- `parseSubagentResponse()` handles plain JSON, markdown-fenced JSON, and embedded JSON with graceful error fallback
- `run_eval.py` CLI with 4 flags (`--skip-capture`, `--benchmark ER-XXX`, `--skip-push`, `--verbose`) and complete 5-step pipeline
- All 241 existing tests continue to pass

## Task Commits

1. **Task 1: Build scoring module** - `bc89484` (feat)
2. **Task 2: Build automated Claude subagent capture runner** - `0ff9ff1` (feat)
3. **Task 3: Build run_eval.py orchestrator** - `accc147` (feat + fix)

## Files Created/Modified

- `eval/src/scoring.py` - Weighted category scoring, 5 primary target checks, terminal summary table (328 lines)
- `eval/src/capture/runner.py` - claude-code-sdk capture runner, JSON parsing, error isolation (320 lines)
- `eval/run_eval.py` - CLI orchestrator with 5-step pipeline (354 lines)
- `eval/src/config.py` - Fixed `api_base` -> `base_url` (LiteLLM deprecation)
- `pyproject.toml` - Added `claude-code-sdk = ">=0.0.25"` to dev group

## Decisions Made

- **claude-code-sdk query() (not ClaudeSDKClient)**: benchmarks are stateless one-shot captures — `query()` is the correct API; `ClaudeSDKClient` is for interactive bidirectional sessions
- **Sequential capture**: Running benchmarks one-at-a-time avoids session collisions and app resource exhaustion. 20 benchmarks with 120s timeout each = ~40min max
- **parseSubagentResponse() 3-tier extraction**: Subagents return JSON in various formats (plain, fenced, embedded in prose). 3-tier extraction handles all observed cases
- **Score extraction from metric.score post-evaluate()**: `EvaluationResult.test_results` iteration is unreliable across deepeval versions; reading `metric.score` after evaluate() is stable
- **ER-018 hallucination rate = 1.0 - score**: HallucinationMetric score is 1.0 when NOT hallucinated; the primary target threshold inverts this to get the rate

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed LiteLLMModel api_base deprecation warning**

- **Found during:** Task 3 verification (run_eval.py --skip-capture output)
- **Issue:** `LiteLLMModel(api_base=...)` produces `WARNING: 'api_base' is deprecated; please use 'base_url' instead` in every run output
- **Fix:** Changed `api_base` to `base_url` in `eval/src/config.py`
- **Files modified:** eval/src/config.py
- **Verification:** `OPENROUTER_API_KEY=test ANTHROPIC_API_KEY=test poetry run python eval/run_eval.py --skip-capture` produces clean output, no deprecation warning
- **Committed in:** accc147 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial fix, no scope change.

## Issues Encountered

- **claude-code-sdk API verification required**: The plan used `event.type == "result"` and `event.text` patterns from the plan spec, but the actual SDK uses dataclass types (`ResultMessage`, `AssistantMessage`) with `isinstance()` checks and `result.result` / `block.text` attributes. Inspected the SDK API before writing the runner to use correct patterns.
- **claude-code-sdk SSL install**: Installed via `.venv/bin/pip install claude-code-sdk --trusted-host pypi.org` (same SSL cert issue as deepeval/litellm in plan 12-01). Declared in pyproject.toml dev group.

## Next Phase Readiness

- Phase 12 is fully complete. The evaluation suite is ready to run:
  ```bash
  poetry run python eval/run_eval.py
  ```
  Prerequisites: Docker Compose services up, app running, OPENROUTER_API_KEY + ANTHROPIC_API_KEY set
- **Checkpoint next**: Human must verify the pipeline works against the live app (start services, run a single benchmark, inspect terminal output)
- `--benchmark ER-001` is the recommended first run to verify end-to-end before all 20

---
*Phase: 12-deepeval-ragas-evaluation-suite*
*Completed: 2026-04-11*
