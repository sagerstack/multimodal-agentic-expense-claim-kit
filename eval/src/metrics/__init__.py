"""Metrics dispatcher and test case builder for the MMGA evaluation suite.

getMetricsForBenchmark: maps benchmark IDs to the correct metric list.
buildTestCase: maps captured result fields to deepeval LLMTestCase fields.

Context / retrieval_context routing:
  - ER-018 ONLY: context = benchmark["groundTruthFacts"] (for HallucinationMetric).
    HallucinationMetric uses context (list[str]), NOT retrieval_context.
  - ER-009, ER-014, ER-017: retrieval_context = captured retrievedPolicyChunks
    (for ContextualPrecision/Recall/Faithfulness). context = None.
  - All other benchmarks: context = None, retrieval_context = None.
"""

from deepeval.metrics.base_metric import BaseMetric
from deepeval.models import LiteLLMModel
from deepeval.test_case import LLMTestCase

from eval.src.dataset import METRIC_MAPPING, getBenchmarkById
from eval.src.metrics.deterministic import getDeterministicMetric
from eval.src.metrics.retrieval import RETRIEVAL_BENCHMARKS, getRetrievalMetrics
from eval.src.metrics.safety import getHallucinationMetric
from eval.src.metrics.semantic import getSemanticMetric

# Flat sets for O(1) membership checks
_DETERMINISTIC: frozenset[str] = frozenset(METRIC_MAPPING["deterministic"])
_SEMANTIC: frozenset[str] = frozenset(METRIC_MAPPING["semantic"])
_HALLUCINATION: frozenset[str] = frozenset(METRIC_MAPPING["hallucination"])
_SAFETY_GEVAL: frozenset[str] = frozenset(METRIC_MAPPING["safety_geval"])


def getMetricsForBenchmark(
    benchmarkId: str, judgeModel: LiteLLMModel
) -> list[BaseMetric]:
    """Return the correct metrics list for the given benchmark ID.

    Routing:
      Deterministic (ER-001..006, ER-010, ER-015):
        [getDeterministicMetric(benchmarkId)]

      Semantic (ER-007..009, ER-011..014, ER-016, ER-017):
        [getSemanticMetric(benchmarkId, judgeModel)]
        + getRetrievalMetrics(judgeModel) for ER-009, ER-014, ER-017

      Hallucination (ER-018):
        [getHallucinationMetric(judgeModel)]   -- NO retrieval metrics

      Safety GEval (ER-019, ER-020):
        [getSemanticMetric(benchmarkId, judgeModel)]
    """
    if benchmarkId in _DETERMINISTIC:
        return [getDeterministicMetric(benchmarkId)]

    if benchmarkId in _HALLUCINATION:
        # ER-018: HallucinationMetric ONLY -- no retrieval metrics
        return [getHallucinationMetric(judgeModel)]

    if benchmarkId in _SEMANTIC:
        metrics: list[BaseMetric] = [getSemanticMetric(benchmarkId, judgeModel)]
        if benchmarkId in RETRIEVAL_BENCHMARKS:
            metrics.extend(getRetrievalMetrics(judgeModel))
        return metrics

    if benchmarkId in _SAFETY_GEVAL:
        return [getSemanticMetric(benchmarkId, judgeModel)]

    raise KeyError(
        f"Benchmark '{benchmarkId}' not found in any metric mapping tier. "
        f"Check METRIC_MAPPING in eval/src/dataset.py."
    )


def buildTestCase(capturedResult: dict, benchmark: dict) -> LLMTestCase:
    """Map a captured result dict + benchmark definition to a deepeval LLMTestCase.

    Field mapping:
      input            <- benchmark["question"]
      actual_output    <- capturedResult["transcript"] (joined) or capturedResult["agentDecision"]
      expected_output  <- benchmark["expectedDecision"] + " | " + benchmark["passCriteria"]
      context          <- benchmark["groundTruthFacts"] for ER-018 ONLY (HallucinationMetric)
                         None for all other benchmarks
      retrieval_context <- capturedResult["retrievedPolicyChunks"] for ER-009/014/017
                          None for ER-018 and all other non-retrieval benchmarks
      additional_metadata <- full capturedResult dict (for deterministic metrics)
    """
    benchmarkId: str = benchmark.get("benchmarkId", "")

    # actual_output: prefer conversation transcript, fall back to agentDecision
    transcript = capturedResult.get("transcript")
    if isinstance(transcript, list):
        actualOutput = "\n".join(str(t) for t in transcript)
    elif transcript:
        actualOutput = str(transcript)
    else:
        actualOutput = str(capturedResult.get("agentDecision", ""))

    expectedOutput = (
        f"{benchmark.get('expectedDecision', '')} | {benchmark.get('passCriteria', '')}"
    )

    # context: ER-018 ONLY -- HallucinationMetric reads context (list[str])
    # sourced from groundTruthFacts (the known facts about the receipt)
    if benchmarkId in _HALLUCINATION:
        groundTruthFacts = benchmark.get("groundTruthFacts")
        context = list(groundTruthFacts) if groundTruthFacts else None
    else:
        context = None

    # retrieval_context: ER-009, ER-014, ER-017 ONLY
    # ER-018 does NOT get retrieval_context
    if benchmarkId in RETRIEVAL_BENCHMARKS:
        retrievedChunks = capturedResult.get("retrievedPolicyChunks")
        retrievalContext = list(retrievedChunks) if retrievedChunks else None
    else:
        retrievalContext = None

    return LLMTestCase(
        input=benchmark.get("question", ""),
        actual_output=actualOutput,
        expected_output=expectedOutput,
        context=context,
        retrieval_context=retrievalContext,
        additional_metadata=capturedResult,
    )
