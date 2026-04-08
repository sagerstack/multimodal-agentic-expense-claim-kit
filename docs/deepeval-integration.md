# DeepEval Integration Plan

## Goal

Integrate `deepeval` into this repo so the project has a repeatable evaluation harness for:

- receipt extraction quality
- policy reasoning quality
- routing and workflow correctness
- safety and control behavior
- regression testing against future prompt, model, and logic changes

This plan uses the benchmark pack in [eval/MMGA_evaluation_v2.pdf](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/eval/MMGA_evaluation_v2.pdf) as the source of truth for test cases.

## Dashboard

- Confident AI dashboard: https://app.confident-ai.com
- Expected workflow: authenticate with `deepeval login`, run evals locally or in CI, then inspect run history, traces, datasets, and metric reports in the dashboard.

## Why Add DeepEval Here

The app already has strong implementation coverage for the agent graph, UI, and core flows, but the repo is still weak on formal rubric-facing evaluation. DeepEval closes that gap by giving this project:

- a standard way to evaluate the full agentic pipeline
- a standard way to compare agentic vs baseline systems
- repeatable failure analysis for low-quality, ambiguous, and unsafe cases
- CI-friendly regression tests for prompt and model changes

This directly supports the benchmark dimensions in the PDF:

- Tier 1: deterministic checks
- Tier 2: semantic reasoning checks
- Tier 3: verifier and safety checks

## Scope of Integration

DeepEval should be added as a dev-only evaluation layer. It should not be part of the request path for the production app.

Recommended scope:

- add `deepeval` as a Poetry dev dependency
- create eval datasets from the `ER-001` to `ER-020` cases in the PDF
- implement deterministic and LLM-judge metrics
- evaluate both component-level and end-to-end flows
- upload runs to Confident AI for dashboard reporting
- wire a small CI job for regression evaluation

## Proposed Repo Changes

Recommended new paths:

```text
docs/deepeval-integration.md
tests/evals/
tests/evals/conftest.py
tests/evals/data/
tests/evals/data/mmga_cases.yaml
tests/evals/fixtures/
tests/evals/fixtures/er_001.json
tests/evals/fixtures/er_002.json
...
tests/evals/metrics/
tests/evals/metrics/deterministic.py
tests/evals/metrics/semantic.py
tests/evals/metrics/safety.py
tests/evals/pipelines/
tests/evals/pipelines/agentic.py
tests/evals/pipelines/baseline_single_prompt.py
tests/evals/pipelines/baseline_handcrafted.py
tests/evals/test_mmga_tier1.py
tests/evals/test_mmga_tier2.py
tests/evals/test_mmga_tier3.py
tests/evals/test_mmga_baselines.py
scripts/run_deepeval.sh
```

Recommended `pyproject.toml` change:

```toml
[tool.poetry.group.dev.dependencies]
deepeval = ">=<pin after trial>"
```

Pin after first successful local run. Do not leave the version floating once the suite is stable.

## Test Case Source of Truth

The PDF defines 20 benchmark cases across five capability groups:

- Classification: `ER-001`, `ER-002`, `ER-003`, `ER-004`, `ER-007`, `ER-008`, `ER-009`
- Extraction: `ER-005`, `ER-006`, `ER-010`, `ER-011`
- Reasoning: `ER-012`, `ER-013`, `ER-014`, `ER-017`
- Workflow / Report-Level: `ER-015`, `ER-016`
- Safety / Control: `ER-018`, `ER-019`, `ER-020`

Each case should be represented in a machine-readable dataset file such as `tests/evals/data/mmga_cases.yaml` with:

- `case_id`
- `benchmark_id`
- `benchmark_name`
- `file_path`
- `scenario`
- `question`
- `expected_decision`
- `scoring_type`
- `pass_criteria`
- `companion_metadata`
- `gold_fields`
- `gold_reasoning_points`
- `gold_safety_expectation`

## Important Asset Gap

The benchmark PDF references `ER-018` as `18.pdf`, but the repo currently does not contain `eval/invoices/18.pdf`.

Current invoice assets present:

- `1.pdf` through `17.jpg` with gaps only at `18.pdf`
- `19.pdf`
- `20.png`

This should be resolved before the safety suite is considered complete.

## Mapping the PDF Benchmarks to DeepEval Suites

### Suite A: Classification

Use the following cases:

- `ER-001` E1 Document Type Identification
- `ER-002` E1 Document Type Identification
- `ER-003` E1 Document Type Identification
- `ER-004` E2 Receipt Completeness
- `ER-007` E4 Expense Category Classification
- `ER-008` E4 Expense Category Classification
- `ER-009` E5 Reimbursable vs Non-Reimbursable

Recommended metrics:

- exact-match label accuracy
- JSON/schema correctness for structured output
- semantic rubric score for justification text where category or workflow reasoning is required

Implementation note:

These cases can be run against:

- the full intake flow
- a single-step classifier helper
- the single-prompt baseline

### Suite B: Extraction

Use the following cases:

- `ER-005` E3 Core Field Extraction
- `ER-006` E3 Core Field Extraction
- `ER-010` E6 Currency and Tax Extraction
- `ER-011` E7 Itemization Readiness

Recommended metrics:

- exact-match field accuracy
- normalized amount/date/currency accuracy
- JSON correctness
- itemization readiness rubric score

Implementation note:

This suite should call the actual receipt extraction path used by the app, centered on the Intake agent and [extractReceiptFields.py](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/src/agentic_claims/agents/intake/tools/extractReceiptFields.py).

### Suite C: Reasoning

Use the following cases:

- `ER-012` E8 Receipt to Expense Entry Matching
- `ER-013` E9 Duplicate Receipt Detection
- `ER-014` E10 Date Window Compliance
- `ER-017` E13 Out of Policy Spend

Recommended metrics:

- semantic correctness of final decision
- groundedness against policy or historical evidence
- tool correctness for DB-backed duplicate checks
- argument correctness for tool calls

Implementation note:

These cases should target:

- Compliance agent behavior
- Fraud agent behavior
- evidence-based decision quality

This is where DeepEval can show whether the agentic system is actually better than simpler alternatives.

### Suite D: Workflow / Report-Level

Use the following cases:

- `ER-015` E11 Report-Level Total Reconciliation
- `ER-016` E12 Approval Routing

Recommended metrics:

- deterministic reconciliation accuracy
- semantic routing correctness
- plan adherence for multi-step output
- task completion score

Implementation note:

`ER-016` should specifically validate the Advisor routing outcome against amount and approval-threshold policy expectations.

### Suite E: Safety / Control

Use the following cases:

- `ER-018` E14 Hallucination Avoidance
- `ER-019` E15 Low-Quality Receipt Escalation
- `ER-020` E16 Cross-Receipt Report Consistency

Recommended metrics:

- hallucination / unsupported-claim detection
- abstention correctness
- escalation correctness
- verifier-style support checking

Implementation note:

This suite should validate that the app behaves conservatively under ambiguity and poor evidence, which matches the project rubric and the app’s current design.

## Systems to Evaluate

The PDF defines three systems. DeepEval should be used to compare all three on the same dataset.

### 1. Agentic System

This is the current app:

- Intake
- Compliance
- Fraud
- Advisor

Evaluation target:

- end-to-end correctness
- per-agent correctness
- safety under uncertainty

### 2. Baseline A: Single-Prompt Pipeline

Implement a minimal baseline in `tests/evals/pipelines/baseline_single_prompt.py`:

- one multimodal model call
- direct output of extraction plus workflow decision
- no graph decomposition
- no explicit policy search loop
- no explicit fraud stage

Purpose:

- satisfy the course rubric requirement for a single-prompt or single-model baseline
- measure whether agent decomposition improves quality

### 3. Baseline B: Hand-Designed Workflow

Implement a simple deterministic baseline in `tests/evals/pipelines/baseline_handcrafted.py`:

- OCR or extraction helper
- regex and heuristic field parsing
- deterministic category mapping
- deterministic threshold checks
- no agent reasoning loop

Purpose:

- satisfy the rubric requirement for a non-agentic baseline
- quantify what the multi-agent system adds beyond rules and heuristics

## Suggested DeepEval Metric Design

### Tier 1: Deterministic

Use for:

- document type labels
- required field presence
- extracted amounts
- extracted dates
- reconciliation checks

Metric style:

- custom exact-match metric
- normalized exact-match metric
- JSON/schema correctness metric

### Tier 2: Semantic

Use for:

- category assignment
- duplicate-risk judgment
- approval routing
- policy reasoning
- receipt-to-entry matching

Metric style:

- rubric-based LLM judge
- answer relevancy
- task completion
- tool correctness and argument correctness where tools are involved

### Tier 3: Verifier and Safety

Use for:

- hallucination avoidance
- abstention under ambiguity
- low-quality receipt escalation
- cross-receipt consistency

Metric style:

- faithfulness / groundedness
- custom safety metric
- custom abstention metric
- unsupported-claim detector

## Dataset Design

Create `tests/evals/data/mmga_cases.yaml` from the PDF first. This should be a normalized registry of all benchmark cases.

Example shape:

```yaml
- case_id: ER-005
  benchmark_id: E3
  benchmark_name: Core Field Extraction
  file_path: eval/invoices/5.png
  scenario: Standard retail receipt
  question: Extract merchant, date, subtotal, tax, total, currency.
  expected_decision: Correct extracted fields
  scoring_type: deterministic
  pass_criteria: Exact or normalized field match
  companion_metadata: null
  gold_fields:
    merchant: ...
    date: ...
    subtotal: ...
    tax: ...
    total: ...
    currency: ...
```

The first implementation pass should build this dataset manually from the PDF.

## How the Eval Runner Should Work

### Component-Level Mode

Run a narrow target:

- extraction only
- compliance only
- fraud only
- advisor only

Purpose:

- isolate weak stages
- shorten iteration time for prompts and tools

### End-to-End Mode

Run the full app path:

- receipt input
- claim state progression
- final routing result

Purpose:

- measure user-visible correctness
- compare against baselines

## CI and Local Workflow

### Local

Recommended commands:

```bash
poetry run pytest tests/evals/test_mmga_tier1.py -v
poetry run pytest tests/evals/test_mmga_tier2.py -v
poetry run pytest tests/evals/test_mmga_tier3.py -v
poetry run pytest tests/evals/test_mmga_baselines.py -v
```

Optional wrapper:

```bash
./scripts/run_deepeval.sh
```

### CI

Recommended policy:

- run Tier 1 on every PR
- run Tier 2 on main and on prompt/model changes
- run Tier 3 nightly or before release/demo
- upload all CI runs to Confident AI

This keeps cost and latency manageable while still preserving regression coverage.

## Recommended Rollout Plan

### Phase 1: Install and Scaffold

- add `deepeval` to Poetry dev dependencies
- add `tests/evals/` layout
- create `mmga_cases.yaml`
- verify dashboard login and reporting

Definition of done:

- one sample eval run appears in the Confident AI dashboard

### Phase 2: Deterministic Tier

- implement `ER-001` to `ER-006`, `ER-010`, `ER-015`
- build exact-match and normalization metrics
- make extraction regressions visible in CI

Definition of done:

- deterministic suite is green and reproducible

### Phase 3: Semantic Tier

- implement `ER-007`, `ER-008`, `ER-009`, `ER-012`, `ER-013`, `ER-014`, `ER-016`, `ER-017`
- add rubric-based judging
- create both agentic and baseline runners

Definition of done:

- the repo can compare agentic vs baseline A vs baseline B on the same semantic cases

### Phase 4: Safety Tier

- implement `ER-018`, `ER-019`, `ER-020`
- add abstention, escalation, and hallucination checks
- block unsafe regressions in CI

Definition of done:

- safety regressions are visible and dashboarded

### Phase 5: Reporting

- export summary charts for report and demo
- summarize:
  - extraction accuracy
  - reconciliation accuracy
  - duplicate detection recall
  - hallucination rate
  - low-quality escalation correctness
  - baseline comparison

Definition of done:

- evaluation results are ready to cite in the final report and presentation

## Repo-Specific Notes

### Existing strengths to reuse

This repo already has useful seams for evaluation:

- graph-level orchestration in [graph.py](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/src/agentic_claims/core/graph.py)
- intake E2E narrative test in [test_e2e_intake_narrative.py](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/tests/test_e2e_intake_narrative.py)
- image quality gate in [extractReceiptFields.py](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/src/agentic_claims/agents/intake/tools/extractReceiptFields.py)
- graph routing tests in [test_graph.py](/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims/tests/test_graph.py)

These should be treated as anchors, not replaced.

### What should not be done

- do not couple DeepEval execution to normal web requests
- do not mix benchmark gold data into production code paths
- do not rely only on LLM-as-judge metrics; pair them with deterministic checks wherever possible
- do not start with all 20 cases at once; get Tier 1 stable first

## Expected Outcome

If this plan is implemented, the repo will gain:

- a formal benchmark suite aligned to `MMGA_evaluation_v2.pdf`
- measurable comparison against the two required baselines
- reproducible evidence for the course rubric’s evaluation section
- dashboard-visible run history for demo and report screenshots
- a defensible story for failure analysis and safety

## Immediate Next Steps

1. Add `deepeval` as a dev dependency.
2. Create `tests/evals/data/mmga_cases.yaml` from `ER-001` to `ER-020`.
3. Resolve the missing `eval/invoices/18.pdf` asset.
4. Implement Tier 1 deterministic evals first.
5. Connect CI and dashboard reporting after the first local green run.
