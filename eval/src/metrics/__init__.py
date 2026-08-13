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

# ---------------------------------------------------------------------------
# Post-submission visibility (added 2026-08-05)
# ---------------------------------------------------------------------------
# Some benchmarks ask a question that this system answers AFTER submission, in
# the compliance / fraud / advisor agents -- never in the intake conversation.
# actual_output is the chat transcript, so those answers were invisible to the
# judge and the benchmarks scored near zero for work the system had actually
# done. ER-013 is the proof: the fraud agent returned verdict "duplicate" with
# "Exact duplicate of: CLAIM-279" and the advisor escalated, yet the judge
# scored 15.9% reasoning "the agent failed to identify the submission as a
# duplicate".
#
# This is deliberately a PER-BENCHMARK allowlist, not a blanket append. Every
# post-submission capture in this suite carries fraudVerdict "duplicate"
# (the fixture set reuses three receipts across eleven benchmarks), so appending
# findings everywhere would hand ER-015 (reconciliation) and ER-020 (report
# consistency) a duplicate flag as if it answered their question. It does not.
#
# Include a benchmark here only when a post-submission agent OWNS the question:
#   ER-013 duplicate detection    -> the fraud agent's entire purpose
#   ER-016 approval routing       -> compliance approval flags + advisor routing
#   ER-019 escalate vs auto-process -> the advisor's decision IS the answer
# Excluded on purpose: ER-012 (receipt/entry matching), ER-015 (total
# reconciliation), ER-020 (cross-receipt consistency) -- no agent performs those,
# so there is nothing legitimate to surface.
_POST_SUBMISSION_SECTIONS: dict[str, tuple[str, ...]] = {
    "ER-013": ("fraud", "advisor"),
    "ER-016": ("compliance", "advisor"),
    "ER-019": ("advisor",),
}


def _formatPostSubmission(capture: dict, sections: tuple[str, ...]) -> str:
    """Render the requested post-submission findings as labelled plain text.

    Labelled explicitly as pipeline output so the judge can tell it apart from
    what the agent said in chat, and can weigh WHY a decision was reached --
    e.g. ER-019 escalates, but for duplicate detection rather than scan quality.
    """
    lines: list[str] = []

    if "compliance" in sections:
        compliance = capture.get("complianceFindings") or {}
        if compliance:
            lines.append(f"Compliance verdict: {compliance.get('verdict')}")
            if compliance.get("summary"):
                lines.append(f"Compliance summary: {compliance['summary']}")
            lines.append(
                f"Requires manager approval: {compliance.get('requiresManagerApproval')}; "
                f"requires director approval: {compliance.get('requiresDirectorApproval')}"
            )

    if "fraud" in sections:
        fraud = capture.get("fraudFindings") or {}
        if fraud:
            lines.append(f"Fraud verdict: {fraud.get('verdict')}")
            if fraud.get("summary"):
                lines.append(f"Fraud summary: {fraud['summary']}")
            for flag in fraud.get("flags") or []:
                lines.append(
                    f"Fraud flag: {flag.get('type')} "
                    f"(confidence {flag.get('confidence')}) -- {flag.get('description')}"
                )

    if "advisor" in sections:
        decision = capture.get("agentDecision")
        reasoning = capture.get("advisorReasoning")
        if decision:
            lines.append(f"Advisor decision: {decision}")
        if reasoning:
            lines.append(f"Advisor reasoning: {reasoning}")

    if not lines:
        return ""
    return "\n\n[Post-submission pipeline output]\n" + "\n".join(lines)


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
      additional_metadata <- benchmark merged with capturedResult

    The deterministic metrics read BOTH observed values (extractedFields,
    agentDecision -- from the capture) and ground truth (expectedDecision,
    expectedFields, companionMetadata -- from the benchmark) out of
    additional_metadata. Passing the capture alone silently starved every
    deterministic metric of its ground truth: DocumentTypeMetric compared
    against an empty string and passed regardless of the agent's decision, and
    AmountReconciliationMetric reported "Missing values" and scored 0.0.
    Capture keys win on collision -- observed data must never be shadowed by
    the benchmark definition.
    """
    benchmarkId: str = benchmark.get("benchmarkId", "")

    # actual_output: prefer conversation transcript, fall back to agentDecision.
    # The capture schema stores this under "conversationTranscript"; reading only
    # "transcript" always missed, so every semantic benchmark was judged against
    # a single token (the advisor decision, e.g. "escalate_to_reviewer") instead
    # of the conversation the rubric describes.
    transcript = capturedResult.get("conversationTranscript") or capturedResult.get("transcript")
    if isinstance(transcript, list) and transcript and isinstance(transcript[0], dict):
        transcript = [f"{t.get('role', '')}: {t.get('content', '')}" for t in transcript]
    if isinstance(transcript, list):
        actualOutput = "\n".join(str(t) for t in transcript)
    elif transcript:
        actualOutput = str(transcript)
    else:
        actualOutput = str(capturedResult.get("agentDecision", ""))

    # Surface post-submission agent output for the benchmarks those agents own.
    # Without this the judge scores the intake chat alone and cannot see work
    # the system genuinely performed. See _POST_SUBMISSION_SECTIONS.
    sections = _POST_SUBMISSION_SECTIONS.get(benchmarkId)
    if sections:
        actualOutput += _formatPostSubmission(capturedResult, sections)

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
        additional_metadata={**benchmark, **capturedResult},
    )
