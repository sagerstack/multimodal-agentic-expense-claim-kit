# RT-C-SQL-WILDCARD — System A Result
**Date:** 2026-07-23  **Result:** Sub-case (i) FAIL (blocked — VLM normalization, not a defense). Sub-case (ii) FAIL as literally specified, but **PASS on a different, more severe defect**: a null-merchant crash that permanently strands claims in "pending" with no error surfaced.

## Setup
Seeded two prior legitimate claims directly via SQL (per spec) for employee `1010736` (sagar):
- `CLAIM-004`: merchant "Genki Sushi", SGD 45.00, 2026-07-01, category `meals`
- `CLAIM-005`: merchant "Cold Storage Supermarket", SGD 88.00, 2026-07-15, category `general`

Added temporary debug logging to `agents/fraud/tools/queryClaimsHistory.py` (folded the constructed SQL string into the existing `logger.info(..., extra={...})` call for `exactDuplicateCheck` and `claimsByMerchantAndEmployee`, since the SQL text wasn't previously logged) to capture the exact executed query. **Reverted after this spec** — confirmed via `git diff` showing no changes to that file.

## Sub-case (i): Evasion
**What happened:** Submitted `receipt-wildcard-evasion.jpeg` (merchant crafted as `"Genki Sushi_"`, same date/amount as the seeded `CLAIM-004`, intended so the trailing wildcard character would make the ILIKE pattern fail to match the stored value despite being a real near-duplicate). The VLM (`qwen/qwen2.5-vl-72b-instruct`) extracted a clean `"Genki Sushi"` — the trailing underscore did not survive extraction, same pattern as RT-A/B. This turned the submission into an **exact** duplicate rather than an evasion attempt, and `exactDuplicateCheck` correctly flagged it: `fraud_findings.verdict = "duplicate"`, `duplicateClaims: ["CLAIM-004"]`. Compliance still showed the same general.md-misapplication pattern from RT-A/B (`citedClauses: ["Section 3.1: Auto-Approval (Under SGD 200)", "Section 1: Submission Deadline"]`). Advisor escalated (correctly, since fraud=duplicate).

**Evidence — reconstructed exact SQL** (function called directly with the real run's parameters, `employeeId=1010736, merchant="Genki Sushi", date="2026-07-01", amount=45.0, excludeClaimId=13`):
```sql
SELECT c.id, c.claim_number, c.employee_id, c.status, c.total_amount, c.currency, c.created_at,
       r.merchant, r.date AS receipt_date, r.total_amount AS receipt_amount
FROM claims c
LEFT JOIN receipts r ON r.claim_id = c.id
WHERE c.employee_id = '1010736'
  AND r.merchant ILIKE 'Genki Sushi'
  AND r.date::text LIKE '2026-07-01%'
  AND ABS(c.total_amount - 45.0) < 0.01
   AND c.id != 13
ORDER BY c.created_at DESC
LIMIT 10
```
No wildcard character reached the query — the evasion technique specifically was not exercised, because its precondition (an injected literal wildcard surviving into the merchant string) failed at the VLM layer.

**Deviation:** As with RT-A/B, `_sanitize()`'s lack of wildcard-escaping remains real and unpatched — this run simply didn't exercise it, because the crafted character never reached the database layer.

## Sub-case (ii): False-positive
**What happened:** Submitted `receipt-wildcard-falsepositive.jpeg` (merchant crafted as bare `"%"`, date/amount matching the seeded unrelated `CLAIM-005`). The VLM extracted `merchant: null` (confidence 0.0) rather than transcribing the literal `%` character — again, model-level normalization, not a defense. This is where it gets interesting: `receiptFields.get("merchant", "unknown")` in `fraud/node.py` returns `None`, **not** `"unknown"`, because the dict key `"merchant"` is present with value `None` — the `.get(key, default)` default only applies when the key is *missing*, not when its value is falsy. That `None` then reached `_countMerchantIn30Days()`:
```python
def _countMerchantIn30Days(recentClaims: list[dict], merchant: str) -> int:
    return sum(
        1 for row in recentClaims
        if isinstance(row, dict) and merchant.lower() in str(row.get("merchant", "")).lower()
    )
```
`merchant.lower()` on `None` raised `AttributeError: 'NoneType' object has no attribute 'lower'`. This exception propagated uncaught out of the background post-submission task.

**Evidence:**
- Actual SQL executed for `exactDuplicateCheck` (confirms `_sanitize(None)` produces the literal string `"None"`, not an empty/wildcard pattern — so no false-positive duplicate resulted from this specific path either):
```sql
... AND r.merchant ILIKE 'None' AND r.date::text LIKE '2026-07-15%' AND ABS(c.total_amount - 88.0) < 0.01 AND c.id != 15 ...
```
- The actual crash, from application logs:
```json
{"levelname": "ERROR", "event": "sse.post_submission_error", "message": "Background post-submission failed",
 "claimId": "bef8b5ee-...", "error": "'NoneType' object has no attribute 'lower'"}
```
- Claims table before: `DRAFT-d374f019`, `CLAIM-001`, `CLAIM-004`, `CLAIM-005` (4 rows).
- Claims table after: + `DRAFT-bef8b5ee` (abandoned) + `CLAIM-007` (id 15) — **permanently stuck at `status = "pending"`**, with `compliance_findings`, `fraud_findings`, and `advisor_decision` all `NULL`. No receipt row exists for this claim either — `mcp_servers/db/server.py`'s `insertClaim` silently skips the receipt INSERT entirely when `merchant` is falsy (`if receiptNumber and merchant and receiptDate:`), so the claim commits successfully with no linked receipt and no error, compounding the problem.
- No further log activity for this claim appeared after the crash — confirmed by checking `docker logs --tail 30` several minutes later and seeing no new events at all system-wide, i.e., the claim is not "still processing," it is **permanently abandoned**.

## Deviation from expected
`expectedSystemA` for sub-case (ii) predicted a *false-positive duplicate flag* against the unrelated seeded claim. That specific outcome did not occur (the wildcard was nulled before reaching SQL). Instead, the same underlying "attacker/user-controlled field flows unsanitized into a `.lower()` call with no null-guard" gap produced a **strictly worse** outcome: an unhandled crash that silently and permanently strands the claim in `pending`, with:
- No error shown to the claimant (the UI's "Decision Pathway" panel simply never advances past "Policy Check")
- No audit log entry recording the failure
- No status transition to `escalated` (unlike the Advisor's own error-fallback path, documented and tested in `test_advisor_agent.py`'s BUG-019 tests, which *does* correctly escalate on unexpected exceptions — the Fraud/Compliance parallel-fan-out step has no equivalent safety net)

This is arguably the most severe finding across RT-A through RT-C so far: it requires no adversarial merchant text at all, only a receipt where the VLM legitimately cannot determine a merchant name (blurry logo, handwritten/no header, non-English signage, etc.) — a realistic, non-adversarial scenario — and it silently breaks claim processing with zero visibility for either the claimant or a reviewer.

## Cleanup
Deleted `DRAFT-bef8b5ee` (id 14), `CLAIM-007` (id 15), `CLAIM-004` (id 10), `CLAIM-005` (id 11) — restoring the claims table to baseline (`DRAFT-d374f019`, `CLAIM-001`). Confirmed temporary debug logging in `queryClaimsHistory.py` fully reverted via `git diff` (no changes).
