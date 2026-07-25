# RT-G-BOUNDARY-VALUE — System A Result
**Date:** 2026-07-24
**Models (locked for this round):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Result:** DIAGNOSTIC — clean, deterministic boundary at exactly SGD 200.00. **This refines, rather than confirms, the "LLM arithmetic is unreliable" conclusion from `SUMMARY_2026-07-23.md`.**

## Summary table

| Amount | Compliance verdict | requiresManagerApproval | citedClauses | Final status |
|--------|----------------------|----------------------------|----------------|----------------|
| SGD 199.00 | pass | **false** | Section 3.1 (Auto-Approval Under SGD 200), Section 1.1 | `ai_approved` |
| SGD 199.99 | pass | **false** | Section 3.1, Section 1.1 | `ai_approved` |
| SGD 200.00 | pass | **true** | Section 3.1, Section 3.2 (Line Manager Approval 200-1,000) | `escalated` |
| SGD 200.01 | **fail** | true | Section 3.1, Section 3.2 | `escalated` |
| SGD 201.00 | **fail** | true | Section 3.1, Section 3.2 | `escalated` |

All 5 claims used the same category (meals), a distinct fresh merchant each time ("Boundary Test Cafe 1"-"5"), and the same line-item description ("Business Lunch Meeting") to control for variance, per the spec.

## What this means

**The SGD 200 boundary itself is reliably and correctly respected** — `requiresManagerApproval` flips cleanly from `false` to `true` at exactly SGD 200.00 (inclusive), across all 5 amounts, with no off-by-one or inconsistent behavior. This is a genuinely deterministic-looking result for this specific numeric comparison, run once.

**This means Round 1's "compliance's own arithmetic is unreliable" finding needs correction, not confirmation.** Round 1 observed `requiresManagerApproval: true` for a SGD 180 meals claim and `false` for other under-200 amounts, and concluded the SGD 200 threshold comparison itself was noisy. This run shows that comparison is actually clean. The real explanation for Round 1's SGD 180 case (and this round's RT-E2 transport SGD 60 case, which failed for a different reason) is more likely **Section 3.4's separate, inconsistently-applied per-category cap cross-reference** ("meal over SGD 30, taxi over SGD 40, hotel over tier cap") — a completely different clause from Section 3.1/3.2's amount-tier logic. The SGD 200 boundary and the Section 3.4 cap-matching are two independent checks living in the same document, and only the second one is unreliable.

Note also that `compliance_findings.verdict` itself flips from `pass` to `fail` exactly at SGD 200.01 (not at SGD 200.00, where it's still `pass` but with `requiresManagerApproval: true`) — a second, consistent transition one cent later, suggesting the LLM is treating "exactly 200" as still within the auto-approval band's docstring wording ("claims under SGD 200") while nonetheless flagging manager approval — internally consistent, if slightly redundant with the two-tier structure in `general.md` itself (Section 3.1 says "under 200", Section 3.2 says "200 to 1,000" — 200.00 exactly belongs to Section 3.2 by the document's own text, which the model got right for `requiresManagerApproval` but arguably should have failed the `pass` verdict for too, since it's not actually "under" 200).

## Evidence
Full `compliance_findings` captured via direct DB query for each of the 5 submissions, shown in the table above (see individual JSON blobs in the raw session evidence — the four distinct cited-clause combinations are quoted in full).

## Deviation from expected
The spec was diagnostic by design (no fixed expectation). The actual finding — a clean, reliable boundary at exactly SGD 200, in contrast to the noisy per-category Section 3.4 matching — is itself the useful, structurally important result, and should replace the vaguer "arithmetic is unreliable" framing in future summaries with the more precise "the SGD 200 tier boundary is reliable; the per-category cap cross-reference in Section 3.4 is not."

## Cleanup
All 5 test claims + draft rows deleted after each submission. Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) after the full sweep.
