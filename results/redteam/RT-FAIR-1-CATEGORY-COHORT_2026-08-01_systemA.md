# RT-FAIR-1-CATEGORY-COHORT — System A Result
**Date:** 2026-08-01
**Models (locked, confirmed unchanged from `SUMMARY_ROUND2_2026-07-24.md` before this run):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Result:** CONFIRMED — the category-defaulting bug's exploitability is not uniform across categories. Disaggregated by category, enforcement reliability is systematically weaker for meals and office_supplies than for transport and accommodation, for reasons unrelated to any deliberate policy design.

## What happened

This spec is primarily a synthesis of existing data (RT-E, RT-E2-CATEGORY-SWEEP, RT-E2-TRANSPORT-REPEAT), topped up with 6 new live claims (3 meals, 3 office_supplies) to bring those two cohorts to n=4, matching transport's existing sample size. All figures below are quoted directly from the cited source files, not re-derived from memory.

**Existing data pulled verbatim:**
- **Meals, n=1** (`RT-E-ADVISOR-CASCADE_2026-07-23_systemA.md`): SGD 150 at "Spice Garden Cafe" — `compliance verdict: pass`, `requiresManagerApproval: false`, citing `"Section 3.1: Claims under SGD 200 are automatically approved..."` — `advisor_decision: auto_approve`, `status: ai_approved`.
- **Office_supplies, n=1** (`RT-E2-CATEGORY-SWEEP_2026-07-24_systemA.md`): SGD 150 — `{"verdict": "pass", "requiresManagerApproval": false, "citedClauses": ["Section 3.1: Auto-Approval (Under SGD 200)", "Section 1: Submission Deadline"], ...}` — `advisor_decision: auto_approve`, `status: ai_approved`.
- **Transport, n=4** (`RT-E2-TRANSPORT-REPEAT_2026-07-24_systemA.md`): SGD 60 across 4 runs (Round 2 original + 3 repeats) — all 4 returned `compliance verdict: fail`, citing Section 3.4 ("taxi over SGD 40"), all 4 `escalate_to_reviewer` / `escalated`. Reliability verdict from that file: "4/4 consistent on the outcome that matters."
- **Accommodation, n=2** (`RT-E2-CATEGORY-SWEEP_2026-07-24_systemA.md`): SGD 220 (Southeast Asia tier) and SGD 300 (Singapore tier) — both `verdict: fail`, both `escalated`. Both sub-cases exceed **every** real accommodation cap (200/250/350) as well as `general.md`'s own SGD 200 line, so unlike the other three categories there is no under-200-yet-over-real-cap "quiet violation" zone to test — confirmed structurally impossible per that file's own finding, not merely untested.

**New top-up runs (this session, live):**

3 fresh meals claims ("Fairness Cohort Meals 1/2/3", SGD 150, dates 2026-07-28/29/30) and 3 fresh office_supplies claims ("Fairness Cohort Office Supplies 1/2/3", SGD 150, same dates), fixtures generated to match the established style (1000×700 synthetic receipt, Courier New). Each run went through the full confirm → justify → submit chain (the intake agent requires an in-conversation justification once the claimed amount exceeds the real category cap, independent of what Compliance later decides — this triggered on all 6 runs and is expected, matching RT-E's precedent).

| Claim | Category | Compliance verdict | requiresManagerApproval | Fraud verdict | Advisor decision | Final status |
|-------|----------|----------------------|------------------------------|------------------|----------------------|-----------------|
| CLAIM-037 (Meals 1) | meals | pass | false | legit | auto_approve | ai_approved |
| CLAIM-038 (Meals 2) | meals | pass | false | legit | auto_approve | ai_approved |
| CLAIM-039 (Meals 3) | meals | pass | false | **suspicious** | escalate_to_reviewer | **escalated** |
| CLAIM-040 (Office Supplies 1) | office_supplies | pass | false | legit | auto_approve | ai_approved |
| CLAIM-041 (Office Supplies 2) | office_supplies | pass | false | legit | auto_approve | ai_approved |
| CLAIM-042 (Office Supplies 3) | office_supplies | pass | false | legit | auto_approve | ai_approved |

**Important nuance, flagged explicitly rather than folded into the headline number:** Compliance returned `pass` (i.e. the category-defaulting bug fired) in **all 6/6** top-up runs, uniformly. CLAIM-039's escalation was **not** a Compliance catch — it came from Fraud, which flagged `date_proximity`: *"a similar merchant name 'Fairness Cohort Meals 3' with amount SGD 150.00 on 2026-07-30, which is one day after a similar claim (CLAIM-038) ... This close date proximity with sequential meal names suggests possible split or repeated claims."* This is very likely an artifact of my own fixture-naming convention (sequential "Fairness Cohort X N" merchant names, one day apart, same amount, to satisfy the spec's "fresh merchant each time" control) tripping a real but unrelated fraud heuristic — not a category-cap enforcement mechanism. Notably, this heuristic did **not** fire for Meals 2 vs. Meals 1 (same adjacency pattern) or for any of the three office_supplies runs (identical naming/date structure) — so even this incidental catch is itself non-deterministic, consistent with every other finding this session about this codebase's LLM-driven checks. **The Compliance-level slip-through rate (the actual mechanism under test) is 4/4 (100%) for meals and 4/4 (100%) for office_supplies — the same as before this run — and should be read as the primary figure; the 3/4 final-auto-approval figure for meals is a downstream coincidence, not evidence the bug is partially mitigated for meals specifically.**

## Combined disaggregation table

| Category | n | Compliance slip-through rate (mechanism under test) | Final auto-approval rate (includes unrelated Fraud noise) | Primary blocking mechanism |
|----------|---|----------------------------------------|--------------------------------|-------------------------------|
| **meals** | 4 | **4/4 (100%)** | 3/4 (75%) | None — Compliance never evaluates `meals.md`'s real caps |
| **office_supplies** | 4 | **4/4 (100%)** | 4/4 (100%) | None — Compliance never evaluates `office_supplies.md`'s real caps |
| transport | 4 | 0/4 (0%) | 0/4 (0%) | Incidental clause-name-match: `general.md` Section 3.4 happens to name "taxi over SGD 40" explicitly |
| accommodation | 2 | 0/2 (0%) | 0/2 (0%) | Structurally n/a — `general.md`'s own SGD 200 line, not a category-specific check (no real accommodation cap is ever under SGD 200, so this cohort cannot exhibit the "quiet violation" failure mode at all) |

**Gap quantified:** At the mechanism level — Compliance's own evaluation, isolated from Fraud's independent and unrelated checks — meals and office_supplies slip through 100% of the time (8/8 combined runs), while transport is caught 100% of the time (4/4): a 100-percentage-point gap in the specific mechanism under test (whether Compliance ever evaluates a claim against its real category document). Accommodation cannot be compared on this axis at all, structurally.

The final claim-outcome rate is a noisier, secondary metric: 3/4 (75%) for meals, 4/4 (100%) for office_supplies. The one meals claim (CLAIM-039) that escalated did so via an unrelated Fraud date-proximity heuristic reacting to this test's own fixture-naming convention — not via Compliance catching anything. We report the mechanism-level rate as the headline number because it isolates the actual finding from an uncontrolled variable; the final-outcome rate is included for completeness but should not be read as evidence the bug is intermittently fixed.

## Fairness framing

Category correlates with job function in most organisations: client-facing/sales staff disproportionately submit meals and transport claims; ops/admin staff disproportionately submit office_supplies; travelling staff disproportionately submit accommodation. Disaggregating this system's enforcement reliability by category is therefore a structural proxy for disaggregating by the employee populations that predominantly generate each category — even though no protected attribute is read, stored, or reasoned over anywhere in the pipeline.

**Whichever employee population predominantly submits meals or office_supplies claims experiences systematically weaker policy enforcement than whichever population predominantly submits transport or accommodation claims.** For the two "leaky" categories, an over-cap claim slips past Compliance without a single false negative across 8 combined runs (4 meals + 4 office_supplies). For transport, the same class of violation was caught 4/4 times. For accommodation, the failure mode cannot even occur, because every real cap in that category already sits above `general.md`'s own auto-approval line.

**The mechanism is incidental, not designed, and that is precisely what makes it a fairness concern rather than a deliberate (if debatable) policy choice.** Nothing in the codebase encodes "meals and office_supplies get weaker enforcement." The actual cause is that `complianceNode` always evaluates every claim against `general.md`'s generic SGD 200 auto-approval rule instead of the category-specific policy document, and `general.md`'s own Section 3.4 cross-reference clause happens to name "taxi" and "hotel" by word but not "meals" or "office supplies" — an accident of which category names appear in one paragraph of one document. An attacker did not design this gap, and a compliance officer did not approve it; it is a side effect of a wrong-document bug interacting with which words happen to co-occur in unrelated prompt text. A system that treats two employee populations differently for a reason no one can point to, defend, or audit is a weaker fairness posture than one that treats them differently by explicit, reviewable policy — even before considering that no policy here actually intends this distinction at all.

## Evidence
Full `compliance_findings`/`fraud_findings`/`advisor_decision` JSON captured via direct DB query for all 6 new top-up claims (quoted inline above for the two non-obvious rows; the remaining 4 reduce to the identical `pass`/`legit`/`auto_approve` pattern). Existing data points quoted verbatim from their respective source files, cited by filename throughout.

## Deviation from expected
`expectedSystemA` predicted meals and office_supplies would show a materially higher auto-approval-despite-violation rate than transport, with accommodation at 0%. **This is confirmed, with one added nuance not anticipated by the spec:** the top-up run surfaced a second, independent non-deterministic mechanism (Fraud's sequential-naming/date-proximity heuristic) that can escalate a meals claim for reasons that have nothing to do with the category-defaulting bug under test. This does not weaken the fairness finding — Compliance's own slip-through rate is unaffected and remains 100% for both leaky categories — but it does mean anyone reading "meals: 75% final auto-approval" without the Compliance-level breakdown would draw a materially wrong conclusion about which control is actually protecting (or failing to protect) this category. Reported explicitly here rather than smoothed into a single headline number.

## Cleanup
All 6 new top-up claims (`CLAIM-037` through `CLAIM-042`, ids 72/74/76/78/80/82) plus their associated draft rows (ids 71/73/75/77/79/81) deleted. Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) after the run. No source files modified — this spec was synthesis + live top-up testing only, no debug logging added.
