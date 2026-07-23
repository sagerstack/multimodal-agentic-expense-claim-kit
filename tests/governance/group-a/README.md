# Group A governance acceptance suite (Expense AI)

## What this is

12 outcome-oriented acceptance cases (`GA-01` .. `GA-12`) proving that the Group A
action-time authorization controls (A1-A12, `agentic-governance` package at
`../agentic-governance`, wired into this app's composition root at
`src/agentic_claims/core/graph.py`) actually gate the live Expense AI app end to end.

This is **not** an exhaustive unit matrix. Exhaustive, deterministic control-level
coverage already exists in the governance package's own test suite
(`../agentic-governance/tests/test_slice0.py` .. `test_slice5.py`,
`test_patch_061.py`) and this app's `tests/test_governance_trusted_evidence.py` /
`tests/test_governance_escalation_handoff.py`. This suite references those files as
**supporting evidence** (see `suite.yaml`) rather than re-proving every threshold and
edge case as a separate acceptance case.

## Roles and responsibilities

- **Suite author** (this integrator): supplies `suite.yaml` and `cases/*.yaml` with
  every stable fact a case needs — exact URLs, a credential reference (never a raw
  secret), fixture references and their exact trusted facts, environment overrides
  named as exact `AGENTIC_GOV_*` variables, expected outcomes, and evidence sources.
  Does not execute anything, does not resolve secrets or runtime-only IDs, does not
  create `.qa` run artifacts, does not change application environment, and does not
  commit.
- **QA lead**: performs a lightweight completeness check on each case before
  execution — not schema validation. It confirms every case names a concrete login
  URL/default, a credential reference, concrete numbered steps, an expected outcome,
  an authoritative oracle (governance audit JSONL plus Postgres — never chat text
  alone), an isolation statement, a cleanup statement, and a timeout. If any of these
  is missing or vague, the QA lead returns `TEST PLAN NEEDS CLARIFICATION` naming the
  exact gap — it does not guess or silently repair a case. Once a case passes this
  check, the QA lead resolves only the dynamic-only values (the run's timestamped
  artifact path, the newest audit file name, the current DB claim id, the actual
  credential secret behind the credential reference) and sequences cases for
  execution, sending exactly one fully-resolved case at a time to the browser tester.
  After execution, the QA lead compares evidence against each case's expected outcome
  and assigns one verdict per case (pass / fail / inconclusive / blocked), then
  produces the one overall Group A report described below.
- **Browser tester**: executes exactly the one resolved case it is handed and
  captures exactly the evidence that case requires. It never changes inputs, expected
  outcomes, evidence requirements, or safety rules, and it never fills a gap with its
  own judgment — an unclear step is reported back, not improvised.

No independent review of this suite and no separate schema-compilation step are
required beyond the QA lead's own lightweight completeness check above and the user's
approval of the case list before any execution begins.

## Deterministic provider and oracle prerequisites

Every browser-level case in this suite names an exact fixture reference (for example
`GROUP_A_VALID_SGD_19_37`) carrying exact trusted facts (merchant/date/amount/
currency/confidence). These facts must be produced by a **deterministic
extraction-provider override** wired into the running app for this suite's execution
— never by a live VLM call, whose output is not reproducible and must never be used
as release evidence. Each such case's `setup` states `deterministicProvider:
required` and a `preflight` step: confirm the override is wired and returns exactly
the declared facts at the real extraction node before doing anything else. If the
override (or an oracle adapter — read access to the newest
`.agentic_governance/*.jsonl` file and to the Postgres claims table) is not available
when a case is due to run, that case's verdict is `BLOCKED`. Do not substitute live
model output, and do not skip the audit/DB check to force a pass.

## Executing this suite

1. Get user approval of the case list in `suite.yaml` before any execution begins.
2. Instantiate the `browser-qa-agentic-expense-claims` team/agent for browser
   execution.
3. Hand the QA lead the path to this directory's `suite.yaml`. The QA lead runs its
   lightweight completeness check first; only after that check passes does it begin
   resolving dynamic values and dispatching cases one at a time.
4. The QA lead's one overall Group A report (JSON, Markdown, HTML, and JUnit, per
   `suite.yaml`'s reporting section) is the final artifact of a run — per-case
   expected vs. actual, evidence level, audit ids/reasons/controlStates, DB effect,
   package/policy versions, artifact paths, duration, and the supporting-evidence
   results.

## Reading `suite.yaml` and a case file

`suite.yaml` carries everything stable and shared across cases: exact URLs, the
baseline governance environment, artifact layout, defaults (isolation, timeouts,
retries), stop rules, the correlation rule for reading a verdict, the ordered case
list, the A1-A12 coverage map, and the supporting lower-layer evidence commands.

Each `cases/GA-NN.yaml` is self-contained for execution and uses only plain,
human-readable fields — `id`, `title`, `covers`, `level`, `purpose`, `setup`,
`steps`, `expected`, `evidence`, `timeouts`, `retries`, `cleanup` — with no formal
schema or version field. Where a case reuses a stable suite-level detail (a URL, the
credential reference, the standard timeouts) it says "Use suite defaults" instead of
repeating it.

## Case index

| ID | Title | Covers | Level |
|----|-------|--------|-------|
| GA-01 | Baseline valid low-value claim Auto-Executes | A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A12 | browser |
| GA-02 | Envelope integrity denies an employeeId mismatch | A1,A2,A6,A12 | browser |
| GA-03 | Unverified/forced-unknown identity is denied | A3,A6,A12 | browser |
| GA-04 | Revoked per-identity mandate is denied | A4,A5,A6,A12 | browser |
| GA-05 | Deny-by-default allowlist denies a removed tool | A5,A6,A12 | browser |
| GA-06 | Per-action exposure escalates to human handoff | A6,A7,A12 | browser |
| GA-07 | Per-action exposure hard-denies above the ceiling | A6,A7,A12 | browser |
| GA-08 | Aggregate daily exposure escalates on the 5th attempt | A7,A8 | browser (stateful) |
| GA-09 | Hourly rate limit denies the 6th attempt | A7,A8 | browser (stateful) |
| GA-10 | Weak evidence escalates regardless of amount | A6,A9 | browser |
| GA-11 | Input-hardening boundary: rogue server + malformed args | A5,A6,A10 | integrated-boundary |
| GA-12 | Fail-closed floor + standalone action-authorization core | A11,A12,A6 | integrated-boundary + supporting structural |

## Scope boundaries

This suite does not execute anything itself (that is the QA lead/browser tester's
job at run time), does not modify the running app's environment, does not add any
test, schema, script, generator, or dependency to either repository, and does not
commit. It supersedes no source file it reads; where a fact could not be verified
without running the app, the affected case says so explicitly (`deterministicProvider:
required`, `preflight`, or a stated prerequisite) instead of guessing.
