"""HTML report generator for the MMGA evaluation suite.

Renders a standalone HTML file that mirrors the main app's design system
(dark theme, Manrope/Inter, Material 3 tokens). The output is a single
self-contained file that can be opened locally or emailed — no external
build artifacts required beyond Google Fonts.

Public API:
    generateHtmlReport(results, categoryScores, overallScore, outputPath, judgeModel)

Consumed by:
    eval/run_eval.py (STEP 6)
    eval/scripts/generate_report.py (standalone CLI)
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from eval.src.dataset import BENCHMARKS, CATEGORY_WEIGHTS
from eval.src.scoring import checkPrimaryTargets


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_PASS_THRESHOLD = 0.7


def _judgeModelLabel(judgeModel) -> str:
    """Return a short, human-readable label for the judge LLM.

    DeepEval model classes (e.g. LiteLLMModel) expose the underlying model
    string via ``.get_model_name()`` or ``.model``. Strings are passed through.

    ``LiteLLMModel.get_model_name()`` returns
    ``"openrouter/openai/gpt-4o (('openai/gpt-4o', 'openrouter', None, None))"``
    so we strip everything after the first " (" and then take the trailing
    slash-separated segment as the model slug.
    """
    if isinstance(judgeModel, str):
        name = judgeModel
    else:
        try:
            name = judgeModel.get_model_name()
        except Exception:
            name = getattr(judgeModel, "model", None) or type(judgeModel).__name__

    name = str(name or "unknown").strip()
    # Strip LiteLLM's trailing debug tuple, e.g. " (('openai/gpt-4o', ...))".
    name = name.split(" (", 1)[0].strip()
    # Trim the "provider/sub-provider/" prefix commonly used by LiteLLM/OpenRouter.
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return f"Powered by DeepEval ({name})"


def _scoreClass(score: float) -> str:
    """Return CSS class keyed to score band (low/mid/high)."""
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "mid"
    return "low"


def _benchmarkRowData(result: dict, benchmarkMeta: dict) -> dict:
    """Build a single row's worth of data for the benchmarks table."""
    benchmarkId = result.get("benchmarkId", "UNKNOWN")
    meta = benchmarkMeta.get(benchmarkId, {})

    score = result.get("score")
    if score is None:
        metrics = result.get("metrics") or []
        score = metrics[0].get("score", 0.0) if metrics else 0.0
    score = float(score)

    capture = result.get("capture") or {}
    expected = result.get("expected") or {}

    return {
        "benchmarkId": benchmarkId,
        "benchmark": meta.get("benchmark", benchmarkId),
        "category": meta.get("category", "unknown"),
        "score": score,
        "scoreClass": _scoreClass(score),
        "passed": score >= _PASS_THRESHOLD,
        "metrics": result.get("metrics") or [],
        "expectedDecision": expected.get("expectedDecision") or meta.get("expectedDecision"),
        "passCriteria": expected.get("passCriteria") or meta.get("passCriteria"),
        "expectedFields": meta.get("expectedFields"),
        "agentDecision": capture.get("agentDecision"),
        "extractedFields": capture.get("extractedFields"),
        "transcript": capture.get("conversationTranscript") or [],
    }


def _buildContext(
    results: list[dict],
    categoryScores: dict[str, float],
    overallScore: float,
    judgeModel: str,
) -> dict:
    """Assemble the Jinja rendering context."""
    benchmarkMeta = {b["benchmarkId"]: b for b in BENCHMARKS}

    benchmarkRows = [_benchmarkRowData(r, benchmarkMeta) for r in results]
    # Preserve BENCHMARKS canonical order
    orderIndex = {b["benchmarkId"]: i for i, b in enumerate(BENCHMARKS)}
    benchmarkRows.sort(key=lambda row: orderIndex.get(row["benchmarkId"], 999))

    passedCount = sum(1 for row in benchmarkRows if row["passed"])
    failedCount = len(benchmarkRows) - passedCount

    categoryRows = []
    for category, weight in CATEGORY_WEIGHTS.items():
        score = categoryScores.get(category)
        if score is None:
            continue
        categoryRows.append({
            "name": category,
            "score": score,
            "weight": weight,
        })

    targets = checkPrimaryTargets(results)
    targetsMet = sum(1 for t in targets if t["passed"])

    generatedAt = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M UTC")

    return {
        "overallScore": overallScore,
        "categoryRows": categoryRows,
        "targets": targets,
        "targetsMet": targetsMet,
        "targetsTotal": len(targets),
        "benchmarkRows": benchmarkRows,
        "totalBenchmarks": len(benchmarkRows),
        "passedCount": passedCount,
        "failedCount": failedCount,
        "judgeModel": _judgeModelLabel(judgeModel),
        "generatedAt": generatedAt,
    }


def generateHtmlReport(
    results: list[dict],
    categoryScores: dict[str, float],
    overallScore: float,
    outputPath: Path,
    judgeModel: str = "unknown",
) -> Path:
    """Render the MMGA eval report HTML and write to disk.

    Args:
        results: Benchmark result dicts (with score and metrics persisted).
        categoryScores: Output of calculateCategoryScores.
        overallScore: Output of calculateWeightedOverall.
        outputPath: Where to write the HTML file.
        judgeModel: Name of the judge LLM (shown in the header chip).

    Returns:
        Path to the written file.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "jinja"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.jinja")

    context = _buildContext(results, categoryScores, overallScore, judgeModel)
    html = template.render(**context)

    outputPath.parent.mkdir(parents=True, exist_ok=True)
    outputPath.write_text(html, encoding="utf-8")
    return outputPath
