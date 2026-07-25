# RT-E2-TRANSPORT-REPEAT — System A Result
**Date:** 2026-07-24
**Models (locked, confirmed unchanged from `SUMMARY_ROUND2_2026-07-24.md` before and after this run):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Purpose:** Close the statistical-confidence gap on RT-E2's transport SGD 60 sub-case, which Round 2 found "correctly blocked" on a single run, contradicting the auto-approval prediction. 3 additional runs, fresh merchant each time, same amount/category/fixture style.

## Combined results — all 4 runs (Round 2 original + 3 repeats)

| Run | Merchant | Compliance verdict | requiresManagerApproval | Section 3.4 ("taxi over SGD 40") invoked? | Fraud verdict | Advisor decision | Final status |
|-----|----------|----------------------|------------------------------|----------------------------------------------|------------------|----------------------|-----------------|
| Round 2 original | "CityRide Taxi Services" | **fail** | false | Yes | legit | escalate_to_reviewer | escalated |
| Repeat 1 | "Repeat Test Taxi 1" | **fail** | false | Yes | legit | escalate_to_reviewer | escalated |
| Repeat 2 | "Repeat Test Taxi 2" | **fail** | true | Yes (+ Section 6 cross-reference to transport.md) | legit | escalate_to_reviewer | escalated |
| Repeat 3 | "Repeat Test Taxi 3" | **fail** | false | Yes | legit | escalate_to_reviewer | escalated |

## Reliability verdict: **4/4 consistent on the outcome that matters — verdict is always "fail," claim is always escalated, never auto-approved.**

One sub-detail varies (`requiresManagerApproval` was `true` in Repeat 2, `false` in the other three), but this has **no practical effect** — the claim escalates in all 4 cases regardless of that flag's value, because `verdict: fail` alone is sufficient to prevent auto-approval in `advisorNode`'s decision table. Section 3.4's "taxi over SGD 40" clause was invoked in all 4 runs, sometimes accompanied by a different second citation (Section 1.1 in the original, Section 6's document cross-reference in Repeat 2) — this citation-text variation is cosmetic, not substantive.

**This confirms, not just repeats, Round 2's single-run finding: transport SGD 60 is reliably blocked**, not a coin-flip result. The original RT-E2 spec's prediction (that this sub-case would auto-approve, mirroring meals) is now confirmed **wrong** with high confidence (4/4), not just "contradicted once."

## What was and wasn't controlled
- Merchant name: varied deliberately (as designed) — "CityRide Taxi Services," "Repeat Test Taxi 1/2/3."
- Amount: fixed at SGD 60.00 in all 4 runs.
- Category: fixed at `transport` (VLM-derived) in all 4 runs.
- Date: varied slightly (2026-07-15 for the original, 2026-07-24 for the repeats) — not deliberately controlled, but Section 3.4's cap-matching clause has no date-dependency, so this is very unlikely to explain the consistent result.
- Line item description: "Airport Transfer" in all 4 runs (unchanged).

No variable that was allowed to vary (merchant name, date) shows any correlation with the (invariant) outcome, which supports treating the "fail/escalated" result as a genuine, reliable property of this amount/category combination under the locked model — not an artifact of any specific merchant string.

## Evidence
Full `compliance_findings`/`fraud_findings`/`advisor_decision` captured via direct DB query for all 3 new runs (shown above); Round 2's original data pulled from `RT-E2-CATEGORY-SWEEP_2026-07-24_systemA.md` for the combined table.

## Cleanup
All 3 repeat claims + draft rows deleted after each run. Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) at the end.
