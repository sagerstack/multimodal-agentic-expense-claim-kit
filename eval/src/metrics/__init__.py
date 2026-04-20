"""Metrics dispatcher and test case builder for the MMGA evaluation suite.

getMetricsForBenchmark: maps benchmark IDs to the correct metric list.
buildTestCase: maps captured result fields to deepeval LLMTestCase fields.

actual_output routing (by pipeline stage):
  Intake benchmarks (ER-001..012, ER-014, ER-015, ER-018, ER-019):
    actual_output = agentDecision (last AI message captured by Playwright).

  Post-submission benchmarks (ER-013, ER-016, ER-017, ER-020):
    actual_output = formatted string combining advisorDecision + complianceFindings
    + fraudFindings + intakeFindings from DB enrichment.
    Falls back to agentDecision if DB fields are all empty.

context / retrieval_context routing:
  ER-018 ONLY: context = benchmark["groundTruthFacts"] (for HallucinationMetric).
  ER-009, ER-014, ER-017: retrieval_context = capturedResult["retrievedPolicyChunks"].
  All others: both None.
"""

import json

from deepeval.metrics.base_metric import BaseMetric
from deepeval.models import LiteLLMModel
from deepeval.test_case import LLMTestCase

from eval.src.dataset import METRIC_MAPPING, getBenchmarkById
from eval.src.metrics.deterministic import getDeterministicMetric
from eval.src.metrics.retrieval import RETRIEVAL_BENCHMARKS, getRetrievalMetrics
from eval.src.metrics.safety import getHallucinationMetric
from eval.src.metrics.semantic import getSemanticMetric

# ---------------------------------------------------------------------------
# Benchmark set membership (O(1) lookups)
# ---------------------------------------------------------------------------

_DETERMINISTIC: frozenset[str] = frozenset(METRIC_MAPPING["deterministic"])
_SEMANTIC: frozenset[str] = frozenset(METRIC_MAPPING["semantic"])
_HALLUCINATION: frozenset[str] = frozenset(METRIC_MAPPING["hallucination"])
_SAFETY_GEVAL: frozenset[str] = frozenset(METRIC_MAPPING["safety_geval"])

# Benchmarks evaluated AFTER the full pipeline (compliance + fraud + advisor ran).
# actual_output for these is built from DB findings, not the intake chat message.
_POST_SUBMISSION: frozenset[str] = frozenset({"ER-013", "ER-016", "ER-017", "ER-020"})


# ---------------------------------------------------------------------------
# Metric dispatcher
# ---------------------------------------------------------------------------


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
        [getHallucinationMetric(judgeModel)]

      Safety GEval (ER-019, ER-020):
        [getSemanticMetric(benchmarkId, judgeModel)]
    """
    if benchmarkId in _DETERMINISTIC:
        return [getDeterministicMetric(benchmarkId)]

    if benchmarkId in _HALLUCINATION:
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


# ---------------------------------------------------------------------------
# actual_output builder (stage-aware)
# ---------------------------------------------------------------------------


def _buildPostSubmissionOutput(capturedResult: dict) -> str:
    """Build actual_output from DB findings for post-submission benchmarks.

    Uses advisorDecision, complianceFindings, fraudFindings, intakeFindings.
    Falls back to agentDecision if all DB fields are empty (e.g. pipeline incomplete).
    """
    parts = []

    advisorDecision = capturedResult.get("advisorDecision")
    if advisorDecision:
        parts.append(f"Advisor Decision: {advisorDecision}")

    advisorReasoning = capturedResult.get("advisorReasoning")
    if advisorReasoning:
        parts.append(f"Advisor Reasoning: {advisorReasoning}")

    complianceFindings = capturedResult.get("complianceFindings")
    if complianceFindings:
        text = json.dumps(complianceFindings) if isinstance(complianceFindings, dict) else str(complianceFindings)
        parts.append(f"Compliance Findings: {text}")

    fraudFindings = capturedResult.get("fraudFindings")
    if fraudFindings:
        text = json.dumps(fraudFindings) if isinstance(fraudFindings, dict) else str(fraudFindings)
        parts.append(f"Fraud Findings: {text}")

    intakeFindings = capturedResult.get("intakeFindings")
    if intakeFindings:
        text = json.dumps(intakeFindings) if isinstance(intakeFindings, dict) else str(intakeFindings)
        parts.append(f"Intake Findings: {text}")

    if not parts:
        # Pipeline hasn't completed post-submission yet — fall back to intake output
        return str(capturedResult.get("agentDecision", ""))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Test case builder
# ---------------------------------------------------------------------------


def buildTestCase(capturedResult: dict, benchmark: dict) -> LLMTestCase:
    """Map a captured result dict + benchmark definition to a deepeval LLMTestCase.

    Field mapping:
      input             <- benchmark["question"]
      actual_output     <- stage-routed (see module docstring)
      expected_output   <- benchmark["expectedDecision"] + " | " + benchmark["passCriteria"]
      context           <- benchmark["groundTruthFacts"] for ER-018 ONLY
      retrieval_context <- capturedResult["retrievedPolicyChunks"] for ER-009/014/017
      additional_metadata <- capturedResult merged with benchmark fields needed by
                             deterministic metrics (expectedDecision, companionMetadata,
                             expectedFields, extractedFields from DB)
    """
    benchmarkId: str = benchmark.get("benchmarkId", "")

    # actual_output = full conversation transcript for all intake benchmarks.
    # This gives GEval and deterministic metrics the complete agent behaviour
    # across all turns, not just the final message.
    transcript = capturedResult.get("conversationTranscript") or []
    if isinstance(transcript, list) and transcript:
        fullConversation = "\n\n".join(
            turn["content"] for turn in transcript if turn.get("content")
        )
    else:
        fullConversation = str(capturedResult.get("agentDecision", ""))

    # Post-submission benchmarks additionally prepend DB findings so the judge
    # sees the compliance/fraud/advisor outputs that the chat UI doesn't show.
    if benchmarkId in _POST_SUBMISSION:
        dbOutput = _buildPostSubmissionOutput(capturedResult)
        actualOutput = f"{dbOutput}\n\n--- Conversation ---\n{fullConversation}" if dbOutput else fullConversation
    else:
        actualOutput = fullConversation

    expectedOutput = (
        f"{benchmark.get('expectedDecision', '')} | {benchmark.get('passCriteria', '')}"
    )

    # context: ER-018 ONLY (HallucinationMetric reads context as list[str])
    if benchmarkId in _HALLUCINATION:
        groundTruthFacts = benchmark.get("groundTruthFacts")
        context = list(groundTruthFacts) if groundTruthFacts else None
    else:
        context = None

    # retrieval_context: ER-009, ER-014, ER-017 ONLY
    if benchmarkId in RETRIEVAL_BENCHMARKS:
        retrievedChunks = capturedResult.get("retrievedPolicyChunks")
        retrievalContext = list(retrievedChunks) if retrievedChunks else None
    else:
        retrievalContext = None

    # Merge benchmark spec fields that deterministic metrics need.
    # Override agentDecision with the full conversation so keyword-based metrics
    # search across all turns (classification may happen in turn 1, not turn N).
    # capturedResult["extractedFields"] is populated by enrichment from the receipts table.
    additionalMetadata = {
        **capturedResult,
        "agentDecision": fullConversation,
        "expectedDecision": benchmark.get("expectedDecision", ""),
        "companionMetadata": benchmark.get("companionMetadata"),
        "expectedFields": benchmark.get("expectedFields"),
    }

    return LLMTestCase(
        input=benchmark.get("question", ""),
        actual_output=actualOutput,
        expected_output=expectedOutput,
        context=context,
        retrieval_context=retrievalContext,
        additional_metadata=additionalMetadata,
    )
