"""HallucinationMetric configuration for ER-018 only.

CRITICAL: HallucinationMetric uses the `context` field on LLMTestCase (list[str]),
NOT `retrieval_context`. For ER-018, the `context` must be sourced from
benchmark["groundTruthFacts"] -- the known facts about the receipt. This ensures
the judge evaluates whether the agent invented values not grounded in these facts.

ER-018 does NOT receive retrieval metrics (ContextualPrecision/Recall/Faithfulness).
Those metrics require retrieval_context which is not applicable to hallucination testing.
"""

from deepeval.metrics import HallucinationMetric
from deepeval.models import LiteLLMModel


def getHallucinationMetric(judgeModel: LiteLLMModel) -> HallucinationMetric:
    """Return a HallucinationMetric configured for ER-018.

    Threshold 0.1: allows a very small hallucination score (practically zero tolerance).
    context field on LLMTestCase must be populated from benchmark["groundTruthFacts"].
    """
    return HallucinationMetric(
        threshold=0.1,
        model=judgeModel,
        include_reason=True,
    )
