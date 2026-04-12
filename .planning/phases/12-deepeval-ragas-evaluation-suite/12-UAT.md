---
status: diagnosed
phase: 12-deepeval-ragas-evaluation-suite
source: [12-01-SUMMARY.md, 12-02-SUMMARY.md, 12-03-SUMMARY.md, 12-04-SUMMARY.md]
started: 2026-04-12T00:00:00Z
updated: 2026-04-12T00:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CLI help and smoke test
expected: `poetry run python eval/run_eval.py --help` prints usage with flags --skip-capture, --benchmark ER-XXX, --skip-push, --verbose. No tracebacks. No "api_base deprecated" warning.
result: pass

### 2. Dry-run pipeline (--skip-capture) loads config and dataset
expected: `OPENROUTER_API_KEY=test ANTHROPIC_API_KEY=test poetry run python eval/run_eval.py --skip-capture` runs cleanly. Logs show LOAD step attempting to read eval/results/ (empty → "no results found" message), not a Python error. 20 benchmarks visible in dataset.
result: skipped
reason: blocked by ANTHROPIC_API_KEY capture blocker (test 3); low-value in isolation (only confirms imports)

### 3. Single-benchmark live capture (ER-001)
expected: With Docker stack up, app at http://localhost:8000, and OPENROUTER_API_KEY + ANTHROPIC_API_KEY set: `poetry run python eval/run_eval.py --benchmark ER-001 --verbose` launches Playwright via Claude subagent, uploads eval/invoices/1.pdf, converses with intake agent, and writes eval/results/ER-001.json containing receipt fields + agent decision.
result: issue
reported: "but i dont have an anthropic api key to use.. this looks like an assumption was made"
severity: blocker

### 4. Enrichment populates DB and Qdrant fields
expected: After capture of a benchmark that submits a claim (e.g. ER-001), the saved result JSON in eval/results/ includes non-null compliance_findings, fraud_findings, advisor_decision (from claims table) and at least one retrieved policy chunk (from Qdrant expense_policies collection).
result: skipped
reason: blocked by capture blocker (test 3) — cannot test enrichment without captured data

### 5. Scoring + terminal summary table
expected: Scoring step produces a terminal summary with 4 sections: per-benchmark scores, per-category scores (5 MMGA categories), weighted overall score, and 5 primary targets (field extraction, reconciliation, duplicate detection, hallucination rate, unsafe auto-processing). Numbers render, columns align, no exceptions.
result: skipped
reason: blocked by capture blocker (test 3) — no scored run to display

### 6. ER-018 missing-file and ER-013 duplicate detection handled gracefully
expected: Running `--benchmark ER-018` does not crash despite 18.pdf being absent — runner writes a file-not-found error JSON and scoring reports it as a failed capture rather than aborting the pipeline. Running `--benchmark ER-013` executes the two-session pattern (login, submit, logout, login again, resubmit) and captures the duplicate-detection response.
result: skipped
reason: blocked by capture blocker (test 3)

### 7. Confident AI dashboard push (or --skip-push respected)
expected: Running without --skip-push pushes the evaluation run to Confident AI — a new run appears on the dashboard. Running with --skip-push sets DEEPEVAL_IGNORE_ERRORS=true and completes without attempting the push (no auth errors if CONFIDENT_AI_API_KEY is unset).
result: skipped
reason: blocked by capture blocker (test 3) — no scored run to push

## Summary

total: 7
passed: 1
issues: 1
pending: 0
skipped: 5

## Gaps

- truth: "Eval suite runs end-to-end against the live app using the project's configured LLM provider (OpenRouter)"
  status: failed
  reason: "User reported: but i dont have an anthropic api key to use.. this looks like an assumption was made. Capture phase requires ANTHROPIC_API_KEY via claude-code-sdk — an unflagged second LLM provider. Project convention per CLAUDE.md is OpenRouter-only (LLM=qwen, VLM=qwen-vl, judge=gpt-4o all via OpenRouter). Nothing in 12-04-PLAN.md or STATE.md surfaced this as a new external credential requirement."
  severity: blocker
  test: 3
  root_cause: "eval/src/capture/runner.py uses claude-code-sdk (query() function) to spawn a Claude subagent that drives Playwright MCP tools for browser automation. claude-code-sdk authenticates against Anthropic's API directly (requires ANTHROPIC_API_KEY env var — validated in eval/src/config.py:46-50). This introduces a second LLM provider dependency that conflicts with the project's OpenRouter-only convention documented in CLAUDE.md (LLM, VLM, and judge model all route through OpenRouter). The capture phase and the evaluation phase are architecturally separate: the subagent only drives the browser; it does not evaluate. Benchmarks are stateless one-shot flows (documented decision in 12-04-SUMMARY.md) — a Claude subagent provides no advantage over a deterministic parameterized Playwright script."
  root_cause_files:
    - "eval/src/capture/runner.py (claude-code-sdk query() calls, max_turns=50)"
    - "eval/src/config.py:46-50 (ANTHROPIC_API_KEY validation)"
    - "pyproject.toml (claude-code-sdk>=0.0.25 in dev group)"
  recommended_fix: "Replace claude-code-sdk subagent in eval/src/capture/runner.py with a direct parameterized Playwright script (login → upload → chat → wait-for-done → scrape DOM). Remove ANTHROPIC_API_KEY from getEvalConfig() in eval/src/config.py. Remove claude-code-sdk dev dependency. Preserve entire evaluation pipeline (enrichment, metrics, scoring, judge via OpenRouter, Confident AI push). The 20 benchmarks share near-identical UI flows — one generic script parameterized by Benchmark dataclass (file path, message script, expected interrupt/resume cycles) covers all cases including ER-013 two-session duplicate pattern."
  artifacts:
    - path: "eval/src/capture/runner.py"
      issue: "Entire module uses claude-code-sdk query() — must be rewritten as direct Playwright automation"
    - path: "eval/src/config.py"
      issue: "Lines 46-50 validate ANTHROPIC_API_KEY — remove validation and anthropicApiKey field from EvalConfig dataclass"
    - path: "pyproject.toml"
      issue: "claude-code-sdk dev dependency — remove"
    - path: "eval/src/capture/subagent.py"
      issue: "buildCapturePrompt and buildDuplicateCapturePrompt produce natural-language prompts for the subagent — obsolete after rewrite, but the DOM selector knowledge (#doneTarget, #aiMessages, #interruptTarget, file input, textarea selectors) must be preserved in the new script"
  missing:
    - "Parameterized Playwright script (Python, via playwright package) covering: login form submission, file upload, chat message send, SSE stream completion detection via #doneTarget, interrupt/resume detection via #interruptTarget, final DOM scrape of #aiMessages into structured JSON"
    - "Two-session variant for ER-013 duplicate detection (logout between sessions)"
    - "Error handling for missing invoice files (ER-018 18.pdf) — script writes file-not-found JSON and continues to next benchmark"
    - "Config change removing ANTHROPIC_API_KEY requirement and anthropicApiKey field"
    - "Dependency removal: claude-code-sdk from pyproject.toml dev group"
    - "playwright package installed as dev dependency (if not already present for Phase 10 E2E tests)"
  debug_session: ""
