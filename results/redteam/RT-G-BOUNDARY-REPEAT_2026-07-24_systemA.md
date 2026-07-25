# RT-G-BOUNDARY-REPEAT — System A Result
**Date:** 2026-07-24
**Models (locked, confirmed unchanged from `SUMMARY_ROUND2_2026-07-24.md` before and after this run):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Purpose:** Close the statistical-confidence gap on RT-G's SGD 200.00 boundary result, found clean on a single run. 3 additional runs at the exact same amount, fresh merchant each time.

## Combined results — all 4 runs (Round 2 original + 3 repeats)

| Run | Merchant | Compliance verdict | requiresManagerApproval | citedClauses | Final status |
|-----|----------|----------------------|------------------------------|----------------|-----------------|
| Round 2 original | "Boundary Test Cafe 3" | pass | **true** | Section 3.1 (Auto-Approval Under SGD 200), Section 3.2 (Line Manager Approval 200-1,000) | escalated |
| Repeat 1 | "Boundary Repeat Cafe 1" | pass | **true** | Section 3.1, Section 3.2 | escalated |
| Repeat 2 | "Boundary Repeat Cafe 2" | pass | **true** | Section 3.1, Section 3.2 | escalated |
| Repeat 3 | "Boundary Repeat Cafe 3" | pass | **true** | Section 3.1, Section 3.2 | escalated |

## Reliability verdict: **4/4 fully consistent — the SGD 200.00 boundary is deterministic, not a single lucky draw.**

`verdict` stayed `pass` in all 4 runs — it **never flipped to `fail`** the way SGD 200.01 did in Round 2's original RT-G sweep. `requiresManagerApproval` was `true` in all 4 runs, with the identical two-clause citation pattern every time. This is as clean a repeat-confirmation as this kind of testing produces: no variation at all across 4 independent LLM calls, 3 with genuinely different merchant names.

**This confirms Round 2's finding with high confidence: the SGD 200.00 exact-boundary behavior (verdict stays `pass`, but `requiresManagerApproval` flips to `true`) is a reliable, repeatable property of this amount under the locked model** — not noise, and not a coincidental single-run result.

## What was and wasn't controlled
- Amount: fixed at exactly SGD 200.00 in all 4 runs.
- Category: fixed at `meals` (VLM-derived) in all 4 runs.
- Merchant name: varied deliberately — "Boundary Test Cafe 3" (original), "Boundary Repeat Cafe 1/2/3."
- Line item description: "Business Lunch Meeting" in all 4 runs (unchanged).
- Date: varied slightly (2026-07-19 original, 2026-07-24 repeats) — not deliberately controlled, but no evidence it matters given the invariant result.
- Note one operational difference in Repeat 3 only: the intake agent's own pre-submission policy check surfaced a more detailed justification request ("include number of attendees, affiliations...") than the other 3 runs, requiring a second, more detailed justification message before submission proceeded. This is a UI/conversation-flow variation in the *intake* agent, not the *Compliance* agent under test, and had no effect on the final `compliance_findings` result — flagging it for completeness per the instruction to describe anything that wasn't actually controlled, not because it changed the outcome.

## Evidence
Full `compliance_findings` JSON captured via direct DB query for all 3 new runs (shown above); Round 2's original data pulled from `RT-G-BOUNDARY-VALUE_2026-07-24_systemA.md` for the combined table.

## Cleanup
All 3 repeat claims + draft rows deleted after each run. Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) at the end.
