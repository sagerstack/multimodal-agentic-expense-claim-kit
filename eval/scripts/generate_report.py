"""Regenerate the MMGA HTML report from existing scored results.

Useful when you want to refresh the report without re-running the eval
(e.g., after tweaking the template).

Assumes each eval/results/ER-XXX.json already has a "score" key — which
run_eval.py persists during STEP 4 scoring. If scores are missing, the
report renders them as 0%.

Usage:
    poetry run python eval/scripts/generate_report.py [--output PATH]
"""

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.src.capture.subagent import loadAllCapturedResults  # noqa: E402
from eval.src.config import getEvalConfig  # noqa: E402
from eval.src.report import generateHtmlReport  # noqa: E402
from eval.src.scoring import calculateCategoryScores, calculateWeightedOverall  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="generate_report")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML file path (default: <resultsDir>/expense-ai-deepeval-report.html)",
    )
    args = parser.parse_args()

    try:
        config = getEvalConfig()
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    results = loadAllCapturedResults(config.resultsDir)
    if not results:
        print(f"ERROR: No result files found in {config.resultsDir}")
        sys.exit(1)

    missingScores = [r for r in results if "score" not in r]
    if missingScores:
        print(
            f"Warning: {len(missingScores)} of {len(results)} results have no "
            "score persisted. Run `poetry run python eval/run_eval.py "
            "--skip-capture` first to score them."
        )

    categoryScores = calculateCategoryScores(results)
    overallScore = calculateWeightedOverall(categoryScores)

    outputPath = args.output or (config.resultsDir / "expense-ai-deepeval-report.html")
    generateHtmlReport(
        results=results,
        categoryScores=categoryScores,
        overallScore=overallScore,
        outputPath=outputPath,
        judgeModel=config.judgeModel,
    )

    print(f"Report written to {outputPath}")
    print(f"Open with: open {outputPath}")


if __name__ == "__main__":
    main()
