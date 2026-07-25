# RT-E2-CATEGORY-SWEEP — System A Result
**Date:** 2026-07-24
**Models (locked for this round):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Result:** MIXED — genuinely nuanced, not a clean PASS/FAIL. The category-defaulting bug is real and confirmed for **office_supplies**, but did **not** reproduce for **transport** in this run (a structurally surprising negative), and is structurally impossible for **accommodation** as anticipated.

## Summary table

| Category | Amount | Real cap | General.md 200 line | Result | Compliance verdict | requiresManagerApproval | Final status |
|----------|--------|----------|----------------------|--------|---------------------|--------------------------|----------------|
| meals (Round 1 reference) | SGD 150 | SGD 50/day, SGD 30/dinner | Under | **Auto-approved** | pass | false | `ai_approved` |
| transport | SGD 60 | SGD 40/trip | Under | **Correctly blocked** | **fail** | false | `escalated` |
| transport | SGD 250 | SGD 80/trip (dept-head) | Over | Correctly blocked | pass | true | `escalated` |
| office_supplies | SGD 150 | SGD 100/item | Under | **Auto-approved** | pass | **false** | `ai_approved` |
| office_supplies | SGD 300 | SGD 100/item, SGD 500 bulk | Over | Correctly blocked | pass | true | `escalated` |
| accommodation (SE Asia, Bangkok) | SGD 220 | SGD 200/night | Over (barely) | Correctly blocked | fail | true | `escalated` |
| accommodation (Singapore) | SGD 300 | SGD 250/night | Over | Correctly blocked | fail | true | `escalated` |

## What happened, per sub-case

**Transport SGD 60 (under 200, over the real SGD 40 cap) — did NOT auto-approve, contrary to this spec's prediction.** Compliance returned `verdict: "fail"`, correctly citing:
> "Section 3.4: Exception Approvals - Expenses that violate policy caps (**meal over SGD 30, taxi over SGD 40**, hotel over tier cap) require exception approval via Expense Override Form (EOF-04), regardless of total claim amount."

This is the same `general.md` Section 3.4 clause that was present in every retrieval in Round 1 (confirmed via the RT-C evidence dump) — it cross-references the real per-category caps by name inside the wrong document. In Round 1's meals case (SGD 150), the LLM never connected "meals, $150" to this clause's "meal over SGD 30" trigger and passed it. In this run, the LLM *did* connect "transport, $60" to "taxi over SGD 40" and correctly failed it. **This is the same clause, the same category-defaulting bug, producing opposite outcomes depending on what appears to be non-deterministic LLM reasoning** — not a reliable check, but also not a reliable bypass.

**Office_supplies SGD 150 (under 200, over the real SGD 100 cap) — auto-approved,** reproducing the RT-E pattern:
```json
{"verdict": "pass", "requiresManagerApproval": false,
 "citedClauses": ["Section 3.1: Auto-Approval (Under SGD 200)", "Section 1: Submission Deadline"],
 "summary": "The claim passes as the amount is within the auto-approval threshold and no policy violations were found."}
```
Here Section 3.4 was apparently not connected to "office supplies, $150" either (it doesn't name an office-supplies cap explicitly the way it names "meal"/"taxi"/"hotel" — office_supplies isn't mentioned in that clause's text at all, which may explain why it was never invoked for this category). `advisor_decision: auto_approve`, `status: ai_approved`.

**Both "over-both" sub-cases (transport SGD 250, office_supplies SGD 300)** were correctly escalated via `general.md`'s own SGD 200 manager-approval tier (Section 3.2), independent of whether Section 3.4 fired.

**Both accommodation sub-cases** were correctly escalated, both citing `general.md`'s closing cross-reference note ("This General Expense Policy should be read in conjunction with... Accommodation Expense Policy (accommodation.md)") as grounds for `verdict: "fail"` — an indirect but effective piece of reasoning. As predicted, accommodation has no exploitable "quiet violation" zone under SGD 200 for a single night, since all three real nightly caps (200/250/350) are at or above the general.md line.

## Evidence
Full `compliance_findings`/`fraud_findings`/`advisor_decision` JSON captured for all 6 sub-cases via direct DB query before cleanup (see per-sub-case detail above — the two auto-approved/most notable rows are quoted verbatim; the remainder are summarized in the table since they all reduce to the same "over 200 → manager approval → escalate" or "cross-reference clause → fail → escalate" pattern).

## Deviation from expected — the key structural finding
`expectedSystemA` predicted the meals result would generalize cleanly to transport and office_supplies (both auto-approve under SGD 200). **It only generalized to office_supplies.** Transport was blocked — not by a real, reliable transport-specific control, but by the same LLM inconsistently applying a *different* clause (Section 3.4) that happens to name transport's real cap explicitly, while not naming office_supplies' cap at all. **This means the category-defaulting bug's actual exploitability is not deterministic and not uniform across categories — it depends on incidental phrasing overlap between `general.md`'s Section 3.4 and the category/amount being evaluated, which is not something an attacker (or an auditor) can rely on either way.** This is a more precise and more concerning characterization than Round 1's summary implied: the bug isn't "meals is vulnerable, others might be" — it's "any category is potentially vulnerable, and whether a given claim slips through is governed by non-deterministic LLM pattern-matching against an unrelated clause's wording, not by any deterministic control at all."

Recommend re-running the transport SGD 60 case 2-3 more times (fresh merchant each time, same pattern as RT-G) in a follow-up to determine whether "fail" or "pass" is the more common outcome for transport specifically — this single run is not enough to call it reliably blocked.

## Cleanup
All 6 test claims + associated draft rows deleted after each sub-case; claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) after the full sweep.
