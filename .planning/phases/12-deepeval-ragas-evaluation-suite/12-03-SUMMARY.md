---
phase: 12-deepeval-ragas-evaluation-suite
plan: 03
subsystem: testing
tags: [deepeval, metrics, GEval, HallucinationMetric, BaseMetric, deterministic, semantic, retrieval]

# Dependency graph
requires:
  - phase: 12-01
    provides: EvalConfig (LiteLLMModel judge), BENCHMARKS, METRIC_MAPPING from dataset.py

provides:
  - eval/src/metrics/deterministic.py -- 4 custom BaseMetric subclasses for 8 deterministic benchmarks
  - eval/src/metrics/semantic.py -- getSemanticMetric() factory for 10 GEval instances
  - eval/src/metrics/safety.py -- getHallucinationMetric() for ER-018
  - eval/src/metrics/retrieval.py -- getRetrievalMetrics() for ER-009/014/017
  - eval/src/metrics/__init__.py -- getMetricsForBenchmark() dispatcher + buildTestCase()

affects:
  - 12-04 (runner calls getMetricsForBenchmark and buildTestCase for every benchmark)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "BaseMetric subclasses with measure/a_measure/is_successful/__name__ for deterministic scoring"
    - "GEval with evaluation_steps only (criteria mutually exclusive per deepeval API)"
    - "HallucinationMetric uses context (list[str]) sourced from groundTruthFacts, NOT retrieval_context"
    - "Native deepeval ContextualPrecision/Recall/Faithfulness -- no RAGAS wrappers"
    - "ER-018 gets HallucinationMetric only -- no retrieval metrics"
    - "ER-009/014/017 get GEval + 3 retrieval metrics (4 total)"

key-files:
  created:
    - eval/src/metrics/deterministic.py
    - eval/src/metrics/semantic.py
    - eval/src/metrics/safety.py
    - eval/src/metrics/retrieval.py
  modified:
    - eval/src/metrics/__init__.py

key-decisions:
  - "GEval uses evaluation_steps only -- criteria and evaluation_steps are mutually exclusive"
  - "HallucinationMetric context comes from groundTruthFacts (benchmark known facts), not retrieved chunks"
  - "ER-018 deliberately excluded from retrieval metrics -- different evaluation axis (hallucination vs RAG precision)"
  - "AmountReconciliationMetric reads claimedAmountInReport OR claimedAmount to support ER-015 dataset field name"

# Metrics
duration: 9min
completed: 2026-04-11
---

# Phase 12 Plan 03: Metrics Engine -- All Scoring Classes Summary

**4 deterministic BaseMetric subclasses + 11 GEval/HallucinationMetric instances + 3 retrieval metrics wired through getMetricsForBenchmark dispatcher covering all 20 MMGA benchmarks**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-11T15:05:33Z
- **Completed:** 2026-04-11T15:15:03Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- 4 deterministic metric classes with pure Python scoring (no LLM calls): DocumentTypeMetric, ReceiptCompletenessMetric, FieldExtractionMetric, AmountReconciliationMetric
- getDeterministicMetric() factory maps 8 benchmark IDs to correct class instances
- 10 GEval instances via getSemanticMetric() factory (evaluation_steps only, threshold=0.7)
- getHallucinationMetric() for ER-018 with threshold=0.1 and context from groundTruthFacts
- getRetrievalMetrics() returning ContextualPrecision/Recall/Faithfulness (native deepeval, not RAGAS)
- getMetricsForBenchmark() dispatcher correctly routes all 20 benchmark IDs
- buildTestCase() builder with correct context/retrieval_context sourcing per benchmark tier
- All 241 existing tests continue to pass

## Task Commits

1. **Task 1: Implement deterministic BaseMetric subclasses** - `02ae58d` (feat)
2. **Task 2: Implement semantic, safety, retrieval metrics and dispatcher** - `62b426e` (feat)

## Files Created/Modified

- `eval/src/metrics/deterministic.py` -- 4 BaseMetric subclasses + getDeterministicMetric() factory
- `eval/src/metrics/semantic.py` -- getSemanticMetric() with 11 benchmark evaluation_steps configs
- `eval/src/metrics/safety.py` -- getHallucinationMetric() for ER-018
- `eval/src/metrics/retrieval.py` -- getRetrievalMetrics() (ContextualPrecision/Recall/Faithfulness)
- `eval/src/metrics/__init__.py` -- getMetricsForBenchmark() dispatcher + buildTestCase() builder

## Decisions Made

- **GEval: evaluation_steps only** -- criteria and evaluation_steps are mutually exclusive per deepeval API. Using evaluation_steps gives rubric-graded scoring with explicit pass/fail logic per step.
- **HallucinationMetric context from groundTruthFacts** -- The HallucinationMetric `context` parameter takes list[str] of known facts. For ER-018, these are the known receipt facts that the agent should NOT contradict or invent beyond.
- **ER-018 excluded from retrieval metrics** -- Retrieval metrics (Contextual Precision/Recall/Faithfulness) evaluate RAG pipeline quality against policy chunks. ER-018 tests hallucination avoidance, a different evaluation axis. Adding retrieval metrics to ER-018 would be conceptually wrong.
- **AmountReconciliationMetric dual key support** -- The ER-015 benchmark uses `claimedAmountInReport` in companionMetadata. The metric checks both `claimedAmount` and `claimedAmountInReport` to avoid KeyError.

## Deviations from Plan

None -- plan executed exactly as written.

## Next Phase Readiness

- Plan 12-04 (runner) can call `getMetricsForBenchmark(benchmarkId, judgeModel)` and `buildTestCase(capturedResult, benchmark)` for every benchmark
- LiteLLM SSL warning (cannot verify model cost map cert) is non-blocking -- falls back to local cache
- All 20 benchmark IDs handled by dispatcher with correct metric counts verified

---
*Phase: 12-deepeval-ragas-evaluation-suite*
*Completed: 2026-04-11*
