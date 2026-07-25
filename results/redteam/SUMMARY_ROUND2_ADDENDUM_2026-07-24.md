# SUMMARY_ROUND2_ADDENDUM — Statistical Confidence Follow-up
**Date:** 2026-07-24
**Models (locked throughout, confirmed unchanged from `SUMMARY_ROUND2_2026-07-24.md` before starting and again at completion):** `OPENROUTER_MODEL_VLM=qwen/qwen2.5-vl-72b-instruct`, `OPENROUTER_MODEL_LLM=qwen/qwen3-235b-a22b-2507`
**Purpose:** Round 2 drew two conclusions from single-run data — this addendum adds 3 repeat runs to each and states plainly whether those conclusions hold.

## Confidence update

### RT-E2 transport SGD 60 — **CONFIRMED** (revised from "single contradictory data point" to "reliable")
Round 2 reported this sub-case as a "structurally surprising negative" — it was blocked once, contradicting the spec's prediction that it would auto-approve like meals did. Three additional runs, full detail in [RT-E2-TRANSPORT-REPEAT_2026-07-24_systemA.md](RT-E2-TRANSPORT-REPEAT_2026-07-24_systemA.md), all four runs total show `verdict: fail`, all four escalate. **This should now be reported as a confirmed, reliable finding, not a single-run curiosity**: transport at SGD 60 is consistently blocked under the locked model, via `general.md`'s Section 3.4 clause correctly naming "taxi over SGD 40" every time. The original SUMMARY_ROUND2 recommendation to treat this as needing more runs before drawing conclusions was correct to flag — and having done those runs, the conclusion is now solid: **the category-defaulting bug's exploitability genuinely differs by category, and transport is (reliably, not by chance) on the non-exploitable side, for the specific reason that Section 3.4 happens to name its cap explicitly.**

### RT-G SGD 200.00 boundary — **CONFIRMED** (revised from "one clean run" to "deterministic across 4 runs")
Round 2 reported a clean flip to `requiresManagerApproval: true` at exactly SGD 200.00, based on one run, and explicitly flagged this needed confirmation before being reported as reliable. Three additional runs, full detail in [RT-G-BOUNDARY-REPEAT_2026-07-24_systemA.md](RT-G-BOUNDARY-REPEAT_2026-07-24_systemA.md), all four runs show identical results: `verdict: pass`, `requiresManagerApproval: true`, identical two-clause citation, escalated. Zero variation across 4 independent LLM calls with 3 different merchant names. **This should now be reported as a confirmed, deterministic boundary, not a single lucky draw.** The corrected framing from Round 2 — that the SGD 200 line itself is reliable while Section 3.4's per-category matching is the actual source of noise — is strengthened, not weakened, by this repeat: the *reliable* mechanism (amount-tier comparison) repeated cleanly 4/4, consistent with it being a genuinely different (and more trustworthy) code path than the *unreliable* mechanism (Section 3.4 category-matching) tested in the other repeat.

## No unexplained contradictions
Per the instructions: neither repeat produced a run that contradicted the others in a way requiring justification or flagging as its own finding. The one sub-variation observed (RT-E2 Repeat 2's `requiresManagerApproval: true` vs. `false` elsewhere, and RT-G Repeat 3's extra justification round-trip in the intake conversation) are both documented in their respective results files as cosmetic/operational differences with no effect on the substantive outcome (escalation in both cases, in all runs) — not averaged away silently, but also not elevated to standalone findings since they don't change what should be reported.

## What this means for the final report
Both of Round 2's flagged single-run results can now be cited in the final report **without the "needs more runs" caveat**:
- Transport SGD 60 being blocked is a reliable finding (4/4).
- The SGD 200.00 boundary being deterministic is a reliable finding (4/4).

The broader Round 2 conclusion these two repeats were meant to support — that the category-defaulting bug is category-dependent and non-uniform, and that the SGD 200 boundary itself is a separate, more reliable mechanism than Section 3.4's category-matching — is now on solid statistical footing rather than resting on single data points.

## Verification
- Model lock confirmed matching `SUMMARY_ROUND2_2026-07-24.md` before starting (`qwen/qwen2.5-vl-72b-instruct` / `qwen/qwen3-235b-a22b-2507`) and re-confirmed unchanged after all 6 new claims completed.
- `git diff --stat` empty at the end of this session — no source files modified.
- Claims table confirmed back to baseline (`DRAFT-d374f019`, `CLAIM-001`) after all 6 repeat claims were created and cleaned up.
