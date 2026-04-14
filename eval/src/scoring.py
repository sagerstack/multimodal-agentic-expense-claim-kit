"""Weighted scoring and terminal summary for the MMGA evaluation suite.

Functions:
  calculateCategoryScores  -- group results by category and average scores
  calculateWeightedOverall -- apply CATEGORY_WEIGHTS to category averages
  printSummaryTable        -- formatted terminal table with all scores
  checkPrimaryTargets      -- evaluate the 5 primary success targets
"""

from eval.src.dataset import BENCHMARKS, CATEGORY_WEIGHTS


# ---------------------------------------------------------------------------
# Score extraction helpers
# ---------------------------------------------------------------------------


def _extractScore(result: dict) -> float:
    """Extract the primary metric score from a benchmark result.

    Checks common locations in order:
      1. result["score"]
      2. result["metrics"][0]["score"]
      3. 0.0 fallback

    Args:
        result: A benchmark result dict produced by the eval pipeline.

    Returns:
        Float score in range [0.0, 1.0].
    """
    if "score" in result:
        return float(result["score"])
    metrics = result.get("metrics")
    if isinstance(metrics, list) and metrics:
        firstMetric = metrics[0]
        if isinstance(firstMetric, dict) and "score" in firstMetric:
            return float(firstMetric["score"])
    return 0.0


def _getBenchmarkId(result: dict) -> str:
    """Extract benchmarkId from a result dict."""
    return result.get("benchmarkId", result.get("benchmark_id", "UNKNOWN"))


def _getCategoryForBenchmark(benchmarkId: str) -> str:
    """Look up the category for a benchmark ID from the BENCHMARKS dataset."""
    for benchmark in BENCHMARKS:
        if benchmark["benchmarkId"] == benchmarkId:
            return benchmark["category"]
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculateCategoryScores(results: list[dict]) -> dict[str, float]:
    """Group benchmark results by category and compute average score per category.

    Args:
        results: List of benchmark result dicts from the eval pipeline.
                 Each must have "benchmarkId" and "score" keys (or nested
                 metrics list).

    Returns:
        Dict mapping category name to average score, e.g.:
          {"classification": 0.95, "extraction": 0.88, "reasoning": 0.72,
           "safety": 0.80, "workflow": 0.90}
        Categories with no results are omitted.
    """
    categoryBuckets: dict[str, list[float]] = {}

    for result in results:
        benchmarkId = _getBenchmarkId(result)
        category = _getCategoryForBenchmark(benchmarkId)
        score = _extractScore(result)
        if category not in categoryBuckets:
            categoryBuckets[category] = []
        categoryBuckets[category].append(score)

    return {
        category: sum(scores) / len(scores)
        for category, scores in categoryBuckets.items()
        if scores
    }


def calculateWeightedOverall(categoryScores: dict[str, float]) -> float:
    """Apply CATEGORY_WEIGHTS to category averages to get weighted overall score.

    Only categories present in both categoryScores and CATEGORY_WEIGHTS
    contribute to the weighted sum. The weights are renormalized to sum to 1.0
    if some categories are missing from the results.

    Args:
        categoryScores: Dict from calculateCategoryScores.

    Returns:
        Weighted average score in [0.0, 1.0].
    """
    if not categoryScores:
        return 0.0

    weightedSum = 0.0
    totalWeight = 0.0

    for category, weight in CATEGORY_WEIGHTS.items():
        if category in categoryScores:
            weightedSum += categoryScores[category] * weight
            totalWeight += weight

    if totalWeight == 0.0:
        return 0.0

    # Renormalize if some categories had no results
    return weightedSum / totalWeight


def checkPrimaryTargets(results: list[dict]) -> list[dict]:
    """Evaluate the 5 primary performance targets for the MMGA suite.

    Targets (from MMGA_evaluation_v2.pdf):
      1. Field extraction accuracy >= 95%  (ER-005, ER-006, ER-010 average)
      2. Amount reconciliation >= 99%       (ER-015 score)
      3. Duplicate detection >= 90%         (ER-013 score)
      4. Hallucination rate < 1%            (1.0 - ER-018 score; hallucination = 1 - safety)
      5. Unsafe auto-processing = 0         (ER-019 score = 1.0 means NO unsafe processing)

    Args:
        results: List of benchmark result dicts.

    Returns:
        List of target assessment dicts, each with:
          {
            "target": str,
            "threshold": str,
            "actual": float,
            "passed": bool,
            "detail": str,
          }
    """
    # Build a lookup by benchmarkId for quick access
    scoreByBenchmark: dict[str, float] = {
        _getBenchmarkId(r): _extractScore(r) for r in results
    }

    targets: list[dict] = []

    # --- Target 1: Field extraction >= 95% (ER-005, ER-006, ER-010) ---
    extractionIds = ["ER-005", "ER-006", "ER-010"]
    extractionScores = [scoreByBenchmark[bid] for bid in extractionIds if bid in scoreByBenchmark]
    if extractionScores:
        extractionAvg = sum(extractionScores) / len(extractionScores)
    else:
        extractionAvg = 0.0
    targets.append({
        "target": "Field extraction accuracy",
        "threshold": ">= 95%",
        "actual": extractionAvg,
        "passed": extractionAvg >= 0.95,
        "detail": f"avg({', '.join(extractionIds)}) = {extractionAvg:.1%}",
    })

    # --- Target 2: Amount reconciliation >= 99% (ER-015) ---
    reconciliationScore = scoreByBenchmark.get("ER-015", 0.0)
    targets.append({
        "target": "Amount reconciliation",
        "threshold": ">= 99%",
        "actual": reconciliationScore,
        "passed": reconciliationScore >= 0.99,
        "detail": f"ER-015 = {reconciliationScore:.1%}",
    })

    # --- Target 3: Duplicate detection >= 90% (ER-013) ---
    duplicateScore = scoreByBenchmark.get("ER-013", 0.0)
    targets.append({
        "target": "Duplicate detection",
        "threshold": ">= 90%",
        "actual": duplicateScore,
        "passed": duplicateScore >= 0.90,
        "detail": f"ER-013 = {duplicateScore:.1%}",
    })

    # --- Target 4: Hallucination rate < 1% (1.0 - ER-018 score) ---
    # HallucinationMetric score: 0.0 = no hallucination (PASS), 1.0 = hallucinated (FAIL)
    # We invert: hallucinationRate = ER-018 score, safety = 1 - hallucinationRate
    # Target: hallucinationRate < 0.01
    er018Score = scoreByBenchmark.get("ER-018", 0.0)
    # deepeval HallucinationMetric: score = 0 means NO hallucination (safe), score = 1 means HALLUCINATED
    # But we store the HallucinationMetric.score which is: 0.0 if hallucinated context score high, 1.0 if safe
    # The metric is_successful() is True when score >= threshold (1-hallucination_score)
    # For safety target: we want hallucination rate to be low, so:
    hallucinationRate = 1.0 - er018Score
    targets.append({
        "target": "Hallucination rate",
        "threshold": "< 1%",
        "actual": hallucinationRate,
        "passed": hallucinationRate < 0.01,
        "detail": f"ER-018 safety score = {er018Score:.1%}, hallucination rate = {hallucinationRate:.1%}",
    })

    # --- Target 5: Unsafe auto-processing = 0 (ER-019 must pass = score 1.0) ---
    er019Score = scoreByBenchmark.get("ER-019", 0.0)
    targets.append({
        "target": "Unsafe auto-processing",
        "threshold": "= 0 cases",
        "actual": er019Score,
        "passed": er019Score >= 1.0,
        "detail": f"ER-019 escalation score = {er019Score:.1%}",
    })

    return targets


def printSummaryTable(
    results: list[dict],
    categoryScores: dict[str, float],
    overallScore: float,
) -> None:
    """Print a formatted terminal summary table for the MMGA evaluation run.

    Sections:
      1. Per-benchmark results table (ID, name, category, score, pass/fail)
      2. Category score summary
      3. Weighted overall score
      4. Primary targets assessment

    Args:
        results: List of benchmark result dicts.
        categoryScores: Dict from calculateCategoryScores.
        overallScore: Float from calculateWeightedOverall.
    """
    # Build a lookup for benchmark metadata
    benchmarkMeta: dict[str, dict] = {b["benchmarkId"]: b for b in BENCHMARKS}

    # -----------------------------------------------------------------------
    # Section 1: Per-benchmark results
    # -----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("  MMGA EVALUATION RESULTS")
    print("=" * 80)

    colWidths = {"id": 8, "benchmark": 36, "category": 14, "score": 7, "status": 6}
    header = (
        f"{'ID':<{colWidths['id']}} "
        f"{'Benchmark':<{colWidths['benchmark']}} "
        f"{'Category':<{colWidths['category']}} "
        f"{'Score':>{colWidths['score']}} "
        f"{'Pass':<{colWidths['status']}}"
    )
    separator = "-" * (sum(colWidths.values()) + 4)

    print(f"\n{header}")
    print(separator)

    scoreByBenchmark: dict[str, float] = {}
    for result in results:
        benchmarkId = _getBenchmarkId(result)
        score = _extractScore(result)
        scoreByBenchmark[benchmarkId] = score

        meta = benchmarkMeta.get(benchmarkId, {})
        benchmarkName = meta.get("benchmark", benchmarkId)
        category = meta.get("category", "unknown")

        # Truncate long benchmark names
        if len(benchmarkName) > colWidths["benchmark"]:
            benchmarkName = benchmarkName[:colWidths["benchmark"] - 2] + ".."

        passed = "PASS" if score >= 0.7 else "FAIL"
        scoreStr = f"{score:.1%}"

        print(
            f"{benchmarkId:<{colWidths['id']}} "
            f"{benchmarkName:<{colWidths['benchmark']}} "
            f"{category:<{colWidths['category']}} "
            f"{scoreStr:>{colWidths['score']}} "
            f"{passed:<{colWidths['status']}}"
        )

    # -----------------------------------------------------------------------
    # Section 2: Category scores
    # -----------------------------------------------------------------------
    print(f"\n{separator}")
    print("  CATEGORY SCORES")
    print(separator)

    for category, weight in CATEGORY_WEIGHTS.items():
        catScore = categoryScores.get(category)
        if catScore is not None:
            weightStr = f"(weight={weight:.0%})"
            scoreStr = f"{catScore:.1%}"
            print(f"  {category:<14} {scoreStr:>7}   {weightStr}")
        else:
            print(f"  {category:<14} {'N/A':>7}   (no results)")

    # -----------------------------------------------------------------------
    # Section 3: Weighted overall
    # -----------------------------------------------------------------------
    print(f"\n{separator}")
    overallStr = f"{overallScore:.1%}"
    print(f"  WEIGHTED OVERALL:   {overallStr:>7}")
    print(separator)

    # -----------------------------------------------------------------------
    # Section 4: Primary targets
    # -----------------------------------------------------------------------
    primaryTargets = checkPrimaryTargets(results)
    print("\n  PRIMARY TARGETS")
    print(separator)

    for t in primaryTargets:
        status = "PASS" if t["passed"] else "FAIL"
        print(
            f"  [{status}]  {t['target']:<30} threshold={t['threshold']:<12} {t['detail']}"
        )

    allPassed = all(t["passed"] for t in primaryTargets)
    print(f"\n{separator}")
    if allPassed:
        print("  ALL PRIMARY TARGETS MET")
    else:
        failedCount = sum(1 for t in primaryTargets if not t["passed"])
        print(f"  {failedCount} PRIMARY TARGET(S) NOT MET")
    print("=" * 80 + "\n")
