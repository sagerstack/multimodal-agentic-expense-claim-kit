"""Native deepeval retrieval metrics for ER-009, ER-014, ER-017.

Uses ContextualPrecisionMetric, ContextualRecallMetric, FaithfulnessMetric
from deepeval.metrics (NOT deepeval.metrics.ragas -- ragas wrappers are hardcoded
to OpenAI model string format and do not accept LiteLLMModel).

These metrics require `retrieval_context` on LLMTestCase (list[str]).

IMPORTANT: ER-018 does NOT receive retrieval metrics. It uses HallucinationMetric
with `context` (not `retrieval_context`) sourced from groundTruthFacts.
"""

from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.metrics.base_metric import BaseMetric
from deepeval.models import LiteLLMModel

# Benchmarks that get retrieval metrics in ADDITION to their primary semantic metric
RETRIEVAL_BENCHMARKS = frozenset({"ER-009", "ER-014", "ER-017"})


def getRetrievalMetrics(judgeModel: LiteLLMModel) -> list[BaseMetric]:
    """Return the 3 native deepeval retrieval metrics.

    These are added on top of the primary GEval metric for ER-009, ER-014, ER-017.
    Threshold: 0.7 for all three (same as semantic metrics).
    """
    return [
        ContextualPrecisionMetric(threshold=0.7, model=judgeModel),
        ContextualRecallMetric(threshold=0.7, model=judgeModel),
        FaithfulnessMetric(threshold=0.7, model=judgeModel),
    ]
