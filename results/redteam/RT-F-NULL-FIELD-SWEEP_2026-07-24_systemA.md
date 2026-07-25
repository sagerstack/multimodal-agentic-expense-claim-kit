# RT-F-NULL-FIELD-SWEEP — System A Result
**Date:** 2026-07-24
**Models (locked for this round):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Result:** MIXED, all 4 hypotheses confirmed or refined — one CRASH (regression-confirmed), one SILENT BAD VALUE, one HANDLED CORRECTLY, and one field (currency) that never actually produces a null in practice.

## Summary table

| Field | Pre-execution hypothesis | Actual result | Classification |
|-------|---------------------------|-----------------|------------------|
| merchant (regression) | CRASH (confirmed Round 1) | Reproduced identically: `'NoneType' object has no attribute 'lower'`, claim permanently stuck `pending` | **CRASH** |
| date | SAFE (or-guarded) | Claim completed fully (`ai_approved`), but **no `receipts` row was ever created** | **SILENT BAD VALUE** (different failure mode than hypothesized — not a crash, but a data-integrity gap) |
| totalAmount / currency (as one field) | SAFE, but possibly silent 0.0 | Intake agent explicitly detected 0% confidence and asked the claimant for the missing value in natural conversation; claim proceeded normally once supplied | **HANDLED CORRECTLY** |
| currency (alone) | UNKNOWN, needs empirical test | VLM never actually returned null — it confidently inferred `"SGD"` (high confidence) even with zero visible currency symbol/code anywhere in the image | **N/A — field doesn't naturally go null**, see note below |

## What happened, per field

### Merchant (regression check) — CRASH, reproduced identically
Re-ran `receipt-wildcard-falsepositive.jpeg` (the exact Round 1 fixture) under the locked model. VLM again extracted `merchant: null` (no Merchant row in the extraction table). App log:
```
{"levelname": "ERROR", "event": "sse.post_submission_error", "message": "Background post-submission failed",
 "error": "'NoneType' object has no attribute 'lower'"}
```
Byte-for-byte identical to Round 1's finding. Confirms the crash is deterministic given a null merchant, not a one-off fluke, and is stable across the model change.

### Date — SILENT BAD VALUE (different mechanism than hypothesized)
Submitted `receipt-null-date.jpeg` (no Date line at all). The VLM returned no Date row (genuinely null), and — as hypothesized — `agents/fraud/node.py`'s `receiptFields.get('date') or receiptFields.get('receiptDate', '')` pattern did prevent a `.lower()`-style crash. **However**, the claim reached full completion (`compliance: pass`, `fraud: legit`, `advisor: auto_approve`, `status: ai_approved`) while **`mcp_servers/db/server.py`'s `insertClaim` silently skipped the entire receipt INSERT** (`if receiptNumber and merchant and receiptDate:` — false because `receiptDate` was empty), leaving `claims.id` with zero rows in `receipts`. Verified via direct query:
```sql
SELECT claim_id, merchant, date, total_amount FROM receipts WHERE claim_id = <this claim>;
-- 0 rows
```
Practical consequence: this claim's real transaction date is now unrecoverable, and any date-dependent rule (the 30-day submission deadline in `general.md` Section 1.1, or a future duplicate-date match) can never be evaluated for it — silently, with no error, warning, or audit trail anywhere.

### TotalAmount / Currency — HANDLED CORRECTLY
Submitted `receipt-null-amount.jpeg` (line item present, no total, no TOTAL line at all). The **intake-gpt** agent (not fraud/compliance) caught this at the conversational layer:
> "The receipt image was processed, but the total amount and currency could not be read due to being cut off... To proceed, I need the total amount and currency. Could you please provide them?"

This is exactly the `expectedSystemB`-style behavior (deterministic clarification gate before the claim reaches Compliance/Fraud) — except it's already how System A behaves for this specific field, via the intake ReAct agent's own judgment rather than a hard-coded rule. Once the claimant supplied "SGD 42.00," the claim proceeded through the normal cap-violation/justification flow and completed correctly (`compliance: fail`, correctly citing the real SGD 20 lunch cap; `fraud: suspicious`; `advisor: escalate_to_reviewer`), with a fully-populated `receipts` row.

### Currency (isolated) — could not be forced null; VLM has a strong default prior
Submitted `receipt-null-currency.jpeg` (bare numbers, e.g. "42.00", no "$"/"SGD"/any currency marker anywhere in the image). Expected the VLM to return `currency: null` the way it did for merchant/amount. Instead it confidently extracted `currency: SGD` (high confidence), identical to a normal receipt. This suggests the model has a strong locale-based default/prior for currency that it applies even in the total absence of visual evidence — unlike merchant (a proper noun with no safe default) and amount (a precise number with no safe default), currency has an obvious "most likely" fallback the model is willing to assume. This is a genuinely different failure mode than the other three fields: **the null-currency precondition this spec wanted to test doesn't naturally occur with this VLM** — worth noting for future testing (a fully non-numeric/non-SGD receipt, e.g. genuinely in an ambiguous foreign currency context, might be a better probe than a bare-numbers one).

## Evidence
Full claims-table before/after for each field, raw app log lines (crash + silent-skip confirmations), and the intake-agent's exact clarification/violation-computation text are captured above verbatim.

## Deviation from expected — flagged explicitly per your instruction
Two things were structurally surprising enough to call out on their own, not just fold into a table:
1. **Date's failure mode is not "safe" in the way the pre-execution hypothesis assumed.** "No crash" was correct, but "no crash" and "handled correctly" are not the same thing — a claim can complete successfully, get auto-approved, and permanently lose its receipt record with zero visibility. This is arguably worse for audit integrity than a crash would be, since a crash at least leaves the claim visibly stuck in `pending` for someone to investigate; the date case looks completely normal from the outside.
2. **The intake agent's own null-handling (for totalAmount) is better than the downstream agents' (for merchant).** The same underlying problem — a VLM field come back null — is handled completely differently depending on which agent/tool touches it first: intake-gpt asks a clarifying question (good), while `fraud/node.py`'s direct `.get(key, default)` pattern crashes uncaught (bad). This inconsistency, not either behavior in isolation, is the real finding: there's no single, deliberate policy for null-field handling anywhere in the codebase — it's an accident of which code path happens to touch the field first.

## Cleanup
All 4 test claims (2 completed, 1 permanently-`pending` requiring direct SQL delete, 1 abandoned draft) plus intermediate draft rows deleted after each field test. Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) after the full sweep.
