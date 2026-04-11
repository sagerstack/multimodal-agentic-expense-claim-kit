"""MMGA Evaluation Suite -- orchestrator entry point.

Usage:
  poetry run python eval/run_eval.py [options]

Options:
  --skip-capture        Skip browser capture, load from eval/results/ JSON files
  --benchmark ER-XXX    Run a single benchmark by ID
  --skip-push           Skip Confident AI push (sets DEEPEVAL_IGNORE_ERRORS=true)
  --verbose             Print detailed metric reasons after scoring

Pipeline:
  1. CAPTURE  -- automated Claude subagent runs each benchmark in the browser
  2. LOAD     -- load captured results from eval/results/
  3. ENRICH   -- fill in DB/Qdrant fields (compliance/fraud/advisor/policy chunks)
  4. SCORE    -- run deepeval metrics and collect scores
  5. REPORT   -- print terminal summary table

All credentials and URLs are loaded from environment variables via getEvalConfig().
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to sys.path so `eval` package is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from deepeval import evaluate  # noqa: E402

from eval.src.capture.enrichment import enrichCapturedResult  # noqa: E402
from eval.src.capture.runner import runCapture  # noqa: E402
from eval.src.capture.subagent import (  # noqa: E402
    loadAllCapturedResults,
    loadCapturedResult,
    saveCapturedResult,
)
from eval.src.config import getEvalConfig  # noqa: E402
from eval.src.dataset import BENCHMARKS, getBenchmarkById  # noqa: E402
from eval.src.metrics import buildTestCase, getMetricsForBenchmark  # noqa: E402
from eval.src.scoring import (  # noqa: E402
    calculateCategoryScores,
    calculateWeightedOverall,
    printSummaryTable,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_eval")


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def buildArgParser() -> argparse.ArgumentParser:
    """Build and return the argument parser for run_eval.py."""
    parser = argparse.ArgumentParser(
        prog="run_eval",
        description="MMGA Evaluation Suite -- runs 20 benchmarks against the live app.",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip browser capture phase; load results from eval/results/ instead.",
    )
    parser.add_argument(
        "--benchmark",
        metavar="ER-XXX",
        help="Run a single benchmark by ID (e.g. --benchmark ER-001).",
    )
    parser.add_argument(
        "--skip-push",
        action="store_true",
        help="Skip Confident AI push (sets DEEPEVAL_IGNORE_ERRORS env var).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed metric reasons in the terminal output.",
    )
    return parser


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------


async def stepCapture(
    benchmarks: list[dict],
    config,
    resultsDir: Path,
) -> None:
    """Step 1: Run Playwright subagent capture for all benchmarks and save results.

    Args:
        benchmarks: List of Benchmark dicts to capture.
        config: EvalConfig instance.
        resultsDir: Directory to save JSON result files.
    """
    print("\n=== STEP 1: CAPTURE ===")
    print(f"Running {len(benchmarks)} benchmark(s) via Claude subagent...")

    capturedResults = await runCapture(benchmarks, config)

    for result in capturedResults:
        savedPath = saveCapturedResult(result, resultsDir)
        logger.info("Saved: %s", savedPath)

    print(f"Saved {len(capturedResults)} result(s) to {resultsDir}")


async def stepEnrich(results: list[dict], config) -> list[dict]:
    """Step 3: Enrich each result with DB and Qdrant data.

    Args:
        results: List of captured result dicts.
        config: EvalConfig instance with DB URL and Qdrant URL.

    Returns:
        Enriched results list (mutated in-place).
    """
    print("\n=== STEP 3: ENRICH ===")
    qdrantUrl = os.environ.get("QDRANT_URL", "http://localhost:6333")

    for idx, result in enumerate(results, start=1):
        benchmarkId = result.get("benchmarkId", "UNKNOWN")
        print(f"  [{idx}/{len(results)}] Enriching {benchmarkId}...")
        try:
            await enrichCapturedResult(result, config.dbUrl, qdrantUrl)
        except Exception as exc:
            logger.error("Enrich failed for %s: %s", benchmarkId, exc)

    print(f"Enriched {len(results)} result(s).")
    return results


def stepScore(
    results: list[dict],
    benchmarksToScore: list[dict],
    config,
    skipPush: bool,
    verbose: bool,
) -> list[dict]:
    """Step 4: Run deepeval metrics and collect scores.

    Builds LLMTestCase for each benchmark, runs getMetricsForBenchmark,
    calls deepeval.evaluate(), and extracts scores back into the result dicts.

    Args:
        results: List of captured (and enriched) result dicts.
        benchmarksToScore: List of Benchmark dicts (in same order as results).
        config: EvalConfig with judgeModel.
        skipPush: If True, set DEEPEVAL_IGNORE_ERRORS to suppress cloud push.
        verbose: If True, print metric reasons.

    Returns:
        Results list with "score" and "metrics" keys added to each entry.
    """
    print("\n=== STEP 4: SCORE ===")

    if skipPush:
        os.environ["DEEPEVAL_IGNORE_ERRORS"] = "true"

    # Build result lookup for quick access by benchmarkId
    resultById: dict[str, dict] = {r.get("benchmarkId", ""): r for r in results}

    testCases = []
    testCaseMetrics = []
    testCaseBenchmarkIds = []

    for benchmark in benchmarksToScore:
        benchmarkId = benchmark["benchmarkId"]
        result = resultById.get(benchmarkId)

        if result is None:
            logger.warning("No result found for benchmark %s -- skipping scoring", benchmarkId)
            continue

        if "captureError" in result:
            logger.warning(
                "Benchmark %s had capture error (%s) -- scoring with empty output",
                benchmarkId,
                result["captureError"],
            )

        testCase = buildTestCase(result.get("capture", {}), benchmark)
        metrics = getMetricsForBenchmark(benchmarkId, config.judgeModel)

        testCases.append(testCase)
        testCaseMetrics.append(metrics)
        testCaseBenchmarkIds.append(benchmarkId)

    if not testCases:
        print("No test cases to score.")
        return results

    print(f"Scoring {len(testCases)} test case(s)...")

    try:
        evalResults = evaluate(
            test_cases=testCases,
            metrics=[m for metricList in testCaseMetrics for m in metricList],
            identifier="MMGA-Evaluation-Run",
            hyperparameters={
                "judgeModel": "openrouter/openai/gpt-4o",
                "appVersion": "phase-12",
            },
        )
    except Exception as exc:
        logger.error("deepeval evaluate() failed: %s", exc)
        return results

    # Extract scores back into result dicts
    # evalResults is EvaluationResult in deepeval 3.x; iterate over test_results
    testResultsList = []
    if hasattr(evalResults, "test_results"):
        testResultsList = evalResults.test_results or []
    elif hasattr(evalResults, "__iter__"):
        testResultsList = list(evalResults)

    for i, benchmarkId in enumerate(testCaseBenchmarkIds):
        result = resultById.get(benchmarkId)
        if result is None:
            continue

        # Collect metrics for this test case
        metricsForThisCase = testCaseMetrics[i]
        metricSummaries = []
        for metric in metricsForThisCase:
            metricScore = getattr(metric, "score", 0.0)
            metricReason = getattr(metric, "reason", "")
            metricName = getattr(metric, "__name__", type(metric).__name__)
            metricSummaries.append({
                "metric": metricName,
                "score": metricScore,
                "reason": metricReason,
            })

            if verbose and metricReason:
                print(f"  [{benchmarkId}] {metricName}: {metricScore:.2f} — {metricReason}")

        # Primary score = first metric
        primaryScore = metricSummaries[0]["score"] if metricSummaries else 0.0
        result["score"] = primaryScore
        result["metrics"] = metricSummaries

    print(f"Scoring complete for {len(testCaseBenchmarkIds)} benchmark(s).")
    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the full evaluation pipeline."""
    parser = buildArgParser()
    args = parser.parse_args()

    print("\n=== MMGA EVALUATION SUITE ===")

    # Load config (validates env vars)
    try:
        config = getEvalConfig()
    except ValueError as exc:
        print(f"\nERROR: {exc}")
        print("\nRequired environment variables:")
        print("  OPENROUTER_API_KEY  -- judge LLM (gpt-4o via OpenRouter)")
        print("  ANTHROPIC_API_KEY   -- Claude subagent invocation")
        sys.exit(1)

    # Determine which benchmarks to run
    if args.benchmark:
        try:
            targetBenchmark = getBenchmarkById(args.benchmark)
            benchmarksToRun = [targetBenchmark]
        except KeyError as exc:
            print(f"\nERROR: {exc}")
            sys.exit(1)
        print(f"Single benchmark mode: {args.benchmark}")
    else:
        benchmarksToRun = list(BENCHMARKS)
        print(f"Full suite mode: {len(benchmarksToRun)} benchmarks")

    # -----------------------------------------------------------------------
    # Step 1: CAPTURE
    # -----------------------------------------------------------------------
    if not args.skip_capture:
        await stepCapture(benchmarksToRun, config, config.resultsDir)
    else:
        print("\n=== STEP 1: CAPTURE (skipped) ===")

    # -----------------------------------------------------------------------
    # Step 2: LOAD
    # -----------------------------------------------------------------------
    print("\n=== STEP 2: LOAD ===")
    if args.benchmark:
        result = loadCapturedResult(args.benchmark, config.resultsDir)
        if result is None:
            print(
                f"\nERROR: No result file found for {args.benchmark} "
                f"in {config.resultsDir}.\n"
                f"Run without --skip-capture to capture first, or check the "
                f"results directory."
            )
            sys.exit(1)
        results = [result]
    else:
        results = loadAllCapturedResults(config.resultsDir)

    if not results:
        print(
            f"\nERROR: No result files found in {config.resultsDir}.\n"
            f"Run without --skip-capture to capture first."
        )
        sys.exit(1)

    print(f"Loaded {len(results)} result file(s).")

    # -----------------------------------------------------------------------
    # Step 3: ENRICH
    # -----------------------------------------------------------------------
    results = await stepEnrich(results, config)

    # -----------------------------------------------------------------------
    # Step 4: SCORE
    # -----------------------------------------------------------------------
    results = stepScore(
        results,
        benchmarksToRun,
        config,
        skipPush=args.skip_push,
        verbose=args.verbose,
    )

    # -----------------------------------------------------------------------
    # Step 5: REPORT
    # -----------------------------------------------------------------------
    print("\n=== STEP 5: REPORT ===")
    categoryScores = calculateCategoryScores(results)
    overallScore = calculateWeightedOverall(categoryScores)
    printSummaryTable(results, categoryScores, overallScore)


if __name__ == "__main__":
    asyncio.run(main())
