---
phase: 12-deepeval-ragas-evaluation-suite
plan: 01
subsystem: testing
tags: [deepeval, litellm, openrouter, gpt-4o, benchmarks, evaluation, hallucination, golden-dataset]

# Dependency graph
requires:
  - phase: 11-intake-multi-turn-fix
    provides: stable intake agent and submission flow to evaluate

provides:
  - eval/src/config.py with EvalConfig and getEvalConfig() factory (LiteLLMModel judge)
  - eval/src/dataset.py with all 20 MMGA benchmark Goldens
  - eval package structure (src/, src/capture/, src/metrics/, results/)
  - deepeval + litellm installed as dev dependencies

affects:
  - 12-02 (capture module needs EvalConfig and BENCHMARKS)
  - 12-03 (metrics module needs BENCHMARKS and METRIC_MAPPING)
  - 12-04 (runner needs all of the above)

# Tech tracking
tech-stack:
  added:
    - deepeval 3.9.6 (evaluation framework: GEval, HallucinationMetric, LiteLLMModel)
    - litellm 1.83.0 (multi-provider LLM proxy used by deepeval judge)
  patterns:
    - "Eval suite fully decoupled from app -- no imports from agentic_claims"
    - "LiteLLMModel with openrouter/openai/gpt-4o as judge model"
    - "Benchmark TypedDict with companionMetadata dict for flexible per-benchmark context"
    - "scoringType field drives metric selection: deterministic | semantic | safety"

key-files:
  created:
    - eval/src/__init__.py
    - eval/src/capture/__init__.py
    - eval/src/metrics/__init__.py
    - eval/src/config.py
    - eval/src/dataset.py
    - eval/results/.gitkeep
  modified:
    - pyproject.toml (added deepeval, litellm to dev group)
    - .gitignore (added eval/results/*.json)

key-decisions:
  - "EvalConfig uses plain dataclass, not pydantic-settings (eval suite is standalone)"
  - "LiteLLMModel model string is openrouter/openai/gpt-4o (not gpt-4o directly)"
  - "scoringType uses safety (not verifier) for ER-018/019/020 per plan spec"
  - "ER-018 groundTruthFacts derived from 1.pdf/19.pdf content -- 18.pdf is missing from invoices"
  - "Installed deepeval/litellm via pip --trusted-host due to SSL cert issue with poetry"

patterns-established:
  - "Benchmark TypedDict: benchmarkId, benchmark, category, file, scenario, question, scoringType, expectedDecision, passCriteria, companionMetadata, groundTruthFacts"
  - "CATEGORY_WEIGHTS dict for weighted scoring across 5 categories"
  - "METRIC_MAPPING groups benchmarks by metric type for dispatch in later plans"

# Metrics
duration: 11min
completed: 2026-04-11
---

# Phase 12 Plan 01: Eval Foundation -- Dependencies and Dataset Summary

**deepeval 3.9.6 + litellm 1.83.0 installed, LiteLLMModel judge configured for openrouter/gpt-4o, all 20 MMGA benchmark Goldens defined with groundTruthFacts for ER-018 and safety scoringType for ER-018/019/020**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-11T14:49:58Z
- **Completed:** 2026-04-11T15:01:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- deepeval and litellm installed as dev dependencies (via pip --trusted-host due to SSL cert issue)
- eval package structure created: eval/src/, capture/, metrics/, results/
- EvalConfig dataclass with LiteLLMModel judge (openrouter/openai/gpt-4o), DB URL, app URL, credentials
- All 20 MMGA benchmarks defined in dataset.py with correct categories, scoringTypes, companionMetadata, and groundTruthFacts for ER-018

## Task Commits

1. **Task 1: Install dependencies and create eval package structure** - `65dbc9b` (feat)
2. **Task 2: Define 20 benchmark Goldens from PDF ground truth** - `cb25be8` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `eval/src/__init__.py` - Package marker
- `eval/src/capture/__init__.py` - Capture subpackage marker
- `eval/src/metrics/__init__.py` - Metrics subpackage marker
- `eval/src/config.py` - EvalConfig dataclass + getEvalConfig() factory; LiteLLMModel with openrouter/openai/gpt-4o
- `eval/src/dataset.py` - 20 Benchmark definitions with CATEGORY_WEIGHTS, METRIC_MAPPING, helpers
- `eval/results/.gitkeep` - Results directory placeholder
- `pyproject.toml` - Added deepeval>=3.9 and litellm>=1.83 to dev group
- `.gitignore` - Added eval/results/*.json

## Decisions Made

- **EvalConfig as plain dataclass**: eval suite is standalone -- no need to couple to pydantic-settings
- **LiteLLMModel model string**: `openrouter/openai/gpt-4o` (litellm provider/model format, not bare `gpt-4o`)
- **scoringType = "safety"** for ER-018/019/020 per plan spec (not "verifier" as shown in PDF tier table)
- **ER-018 file reference**: kept as `18.pdf` per PDF ground truth even though file is absent from invoices/

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used pip --trusted-host instead of poetry add for package installation**

- **Found during:** Task 1 (Install dependencies)
- **Issue:** `poetry add deepeval litellm` failed with SSL certificate verification error (`[SSL: CERTIFICATE_VERIFY_FAILED]`). Network is reachable but pypi.org TLS cert chain cannot be verified in this environment.
- **Fix:** Installed via `.venv/bin/pip install deepeval litellm --trusted-host pypi.org --trusted-host files.pythonhosted.org`. Then manually added `deepeval = ">=3.9"` and `litellm = ">=1.83"` to pyproject.toml dev group to keep Poetry's dependency manifest accurate.
- **Files modified:** pyproject.toml
- **Verification:** `poetry run python -c "from deepeval.models import LiteLLMModel; print('OK')"` prints OK
- **Committed in:** 65dbc9b (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Packages installed and functional. pyproject.toml updated to reflect declared dependencies. No scope creep.

## Issues Encountered

- **18.pdf missing from eval/invoices/**: The ground truth PDF references `18.pdf` for ER-018 but the file does not exist in the invoices directory (only 1-17, 19-20 are present). The PDF preview for ER-018 shows a GoRails/Example LLC receipt identical to 1.pdf/19.pdf. The benchmark is kept with `file="18.pdf"` per ground truth. The groundTruthFacts for ER-018 were derived from the actual content of 1.pdf (same receipt). The capture module (plan 12-02) will need to handle this missing file gracefully.

## Next Phase Readiness

- Plan 12-02 (capture module) can now import `EvalConfig` and `BENCHMARKS` from eval/src/
- Plan 12-03 (metrics module) can use `METRIC_MAPPING` for metric dispatch
- **Blocker for capture**: `18.pdf` is missing -- the capture runner must handle FileNotFoundError for ER-018 or the file must be added to eval/invoices/ before running
- All 241 existing passing tests continue to pass; 3 pre-existing failures are unrelated to this plan

---
*Phase: 12-deepeval-ragas-evaluation-suite*
*Completed: 2026-04-11*
