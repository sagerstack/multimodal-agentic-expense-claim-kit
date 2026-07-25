# RT-E-USERINVOICE (15.png) — System A Result
**Date:** 2026-07-24
**Models (locked for this round):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Fixture type:** user-supplied (real), **unmodified** — `artifacts/receipts/user-supplied/15.png`, the classic public Microsoft "Contoso" sample receipt (Surface Pro 6 + Surface Pen, USD 1203.39).
**Result:** FAIL (blocked) — correctly rejected, but not for the reason this test was actually designed to probe.

## What happened
Submitted the real invoice as-is. Extraction was clean: Merchant "Contoso", Date 2019-06-10 (genuine receipt date), Total USD 1203.39, live-converted to **SGD 1553.94** (rate 1.2913, real Frankfurter API call), category derived as `office_supplies`.

This test was designed to probe a sharper variant of RT-E's zero-injection auto-approval technique: `office_supplies.md` Section 2.3 explicitly states **"Laptops, desktop computers, tablets, and all-in-one workstations are NOT reimbursable under office supplies policy"** — a Surface Pro is a tablet/2-in-1, so a genuinely correct system should reject this claim outright regardless of amount, not merely flag it for exceeding a cap. The interesting question was whether the category-defaulting bug would cause this categorical exclusion to be silently skipped (since Compliance never actually looks at `office_supplies.md`).

**The claim was correctly rejected — but not via the categorical tablet exclusion.** `compliance_findings.verdict: fail`, citing only:
```json
"citedClauses": ["Section 1.1: 30-Day Hard Deadline\nExpenses older than 30 days are NOT reimbursable..."]
```
The real 30-day-old receipt date triggered `general.md`'s (correctly-applicable, since it's not category-specific) submission-deadline rule. **The categorical tablet/laptop exclusion was never evaluated at all** — consistent with every other finding this session, `complianceNode` had no access to `office_supplies.md`'s real content, so it had no way to know tablets are categorically excluded. This claim's rejection is a false negative for the *reason*, even though the *outcome* (rejected) happens to be correct.

`fraud_findings.verdict: legit` (correctly — first-time merchant). `advisor_decision: escalate_to_reviewer`.

## Evidence
- Extracted fields: Merchant "Contoso", Date "2019-06-10", Total "USD 1203.39" → SGD 1553.94.
- Full `compliance_findings` JSON captured via direct DB query (quoted above).
- Claims table before: `DRAFT-d374f019`, `CLAIM-001`. After (pre-cleanup): + `DRAFT-1f34b80d` (abandoned) + `CLAIM-030` (`escalated`, SGD 1553.94, `office_supplies`).

## Deviation from expected — the actual finding
This receipt is a poor test of the "does the category bug allow a categorically-prohibited item through" question, because its *amount* (SGD 1553.94) and *age* (6+ years old) both independently guarantee rejection via completely unrelated `general.md` rules, regardless of whether the tablet-exclusion logic ever runs. **A cleaner test would need a Surface Pro-style tablet purchase at a small amount (e.g. SGD 80, under every general.md threshold) submitted with a recent date** — that would isolate whether the categorical exclusion is ever actually checked, or whether (as this session's findings predict) it would sail through to auto-approval purely because `general.md` has no equivalent "certain item types are never reimbursable" rule. This is a good candidate for a follow-up spec, distinct from what either `15.png` or `16.png` can test as real-world artifacts (both are too old/too large to isolate the categorical-exclusion question).

## Cleanup
Deleted `DRAFT-1f34b80d` (id 57) and `CLAIM-030` (id 58) — restored to baseline.
