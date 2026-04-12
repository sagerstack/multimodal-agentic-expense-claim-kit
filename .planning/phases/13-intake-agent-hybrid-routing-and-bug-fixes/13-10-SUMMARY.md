---
phase: 13
plan: 10
subsystem: sse-streaming
tags: [sseHelpers, content-routing, bug-fix, tdd, UAT-gap-1, Fix-A]

dependency-graph:
  requires:
    - "13-DEBUG-display-regression.md (H1 CONFIRMED diagnosis)"
    - "Phase 7 (SSE infrastructure, SseEvent taxonomy)"
  provides:
    - "_isUserFacingProse helper: prose gate for mid-stream MESSAGE emission"
    - "Mid-stream MESSAGE bubble for AIMessage with content + tool_calls"
    - "sse.mid_stream_bubble_emitted and sse.content_suppressed_as_reasoning observability events"
  affects:
    - "13-11: stale interrupt target cleanup (companion fix, same UAT gap)"
    - "13-12: clarificationPending clear (companion fix, same UAT gap)"
    - "Phase 10: E2E Playwright tests — extraction table visible in #aiMessages"

tech-stack:
  added: []
  patterns:
    - "tokenBuffer-OR-output.content fallback: when tokenBuffer is empty (no stream events, model emits content only on end), fall back to output.content for the prose source"
    - "Prose gate: _isUserFacingProse gating emission — length>=40 OR markdown markers"
    - "Suppression telemetry: sse.content_suppressed_as_reasoning with contentLength+preview for post-ship false-negative tracking"

key-files:
  created:
    - tests/test_sse_content_routing.py
  modified:
    - src/agentic_claims/web/sseHelpers.py

decisions:
  - "tokenBuffer-first with output.content fallback: real streaming populates tokenBuffer; tests and non-streaming models only populate output.content. Both paths must work."
  - "Prose gate threshold 40 chars: preserves existing filler suppression (Ok., Sure.) while promoting tables and substantive prose"
  - "Mid-stream bubbles carry no confidenceScores/violations: metadata stays on terminal bubble only (end-of-stream MESSAGE path)"
  - "reasoningText source changed to reasoningBuffer.strip() only (removed cleanedBuffer fallback): content-as-reasoning was the bug; after fix, cleaned buffer either becomes a MESSAGE or goes to thinking-entry — never drives STEP_CONTENT as reasoning summary"

metrics:
  duration: "16 min"
  completed: "2026-04-13"
---

# Phase 13 Plan 10: SSE Content Routing Fix (Fix A) Summary

**One-liner:** Mid-stream MESSAGE bubble emission for AIMessage content+tool_calls via _isUserFacingProse gate (40-char threshold + markdown markers), with tokenBuffer-OR-output.content fallback and sse.content_suppressed_as_reasoning telemetry.

## Objective

Restore visibility of substantive agent content (extraction result tables, policy-check summaries) that collapsed into the "Thought for Xs" thinking panel whenever the v5-prompted LLM packed user-facing prose and a tool_call into the same AIMessage. Implements Fix A from `13-DEBUG-display-regression.md` H1 (CONFIRMED).

## TDD Cycle Evidence

| Phase | Commit | Description |
|-------|--------|-------------|
| RED | b6a8d57 | `test(13-10): add failing tests for content+tool_calls MESSAGE routing` |
| GREEN | ae891a3 | `fix(13-10): emit AIMessage content as MESSAGE bubble when tool_calls present` |
| REFACTOR | 9877a3d | `refactor(13-10): clean up content-routing helper` |

**RED pattern confirmed:** 4 of 6 tests failed (tests a, c, d, f); 2 passed (tests b, e — existing behaviour guards). Failure messages confirmed cause: "no MESSAGE event found" not import errors.

## Implementation Details

### New helper: `_isUserFacingProse(text: str) -> bool` (sseHelpers.py:80)

```
Gate: length >= 40 chars OR markdown markers (|, #, ##, -, *, \n)
False: empty, "Ok.", "Sure."
True: markdown tables, policy summaries, any text >= 40 chars
```

### Modified: `hasToolCalls` branch in `on_chat_model_end` (sseHelpers.py:963–1046)

Before (broken):
- `cleanedBuffer = _stripToolCallJson(tokenBuffer.strip())`
- if `cleanedBuffer`: `thinkingEntries.append({"type": "reasoning", ...})`
- Content NEVER emitted as `SseEvent.MESSAGE`

After (fixed):
1. Resolve `rawContent = tokenBuffer.strip() OR output.content` (fallback for non-streaming)
2. Strip: `_stripToolCallJson` then `_stripThinkingTags`
3. If `_isUserFacingProse(cleanedBuffer)`:
   - Render via `partials/message_bubble.html` (no confidenceScores/violations)
   - `yield ServerSentEvent(raw_data=midHtml, event=SseEvent.MESSAGE)`
   - `logEvent(..., "sse.mid_stream_bubble_emitted", ...)`
4. Else (filler or empty):
   - `thinkingEntries.append({"type": "reasoning", ...})` (existing path)
   - `logEvent(..., "sse.content_suppressed_as_reasoning", contentLength=..., preview=..., ...)`
5. `reasoningBuffer` → `thinkingEntries` + `STEP_CONTENT` (unchanged, private thinking path)
6. `tokenBuffer = ""`, `reasoningBuffer = ""` (unchanged)

**Preserved unchanged:**
- Non-tool-calls branch (L997–1030): `finalResponse` first-write-wins guard (BUG-016) intact
- End-of-stream terminal bubble (L1504–1518): `confidenceScores` + `violations` metadata stays on terminal bubble
- Token streaming path (L883): `on_chat_model_stream` → `SseEvent.TOKEN` unchanged
- All other `logEvent` calls

## Line-count diff on sseHelpers.py

- Lines added: ~73 (helper function + new branch logic)
- Lines removed: ~16 (replaced existing hasToolCalls block)
- Net: ~57 lines added (within the ≤ ~60 line target for narrow change)

## Final pytest output

```
324 passed, 7 failed, 4 skipped, 35 warnings in 237.36s
```

7 failures are all pre-existing on baseline (verified by stash check):
1. `test_e2e_intake_narrative::test_intake_narrative_restaurant_receipt` — pre-existing
2. `test_extract_receipt_fields::testBlurryImageReturnsError` — pre-existing
3. `test_intake_e2e_vnd::test_vndReceiptTriggersManualRateViaHookDrivenFlow` — pre-existing
4. `test_plan_001_bug_fixes::testFetchClaimsForTableUsesClaimCategoryAndEmployeeFilter` — pre-existing
5. `test_plan_001_bug_fixes::testCurrencyToolErrorProducesCorrectionMessage` — pre-existing
6. `test_sse_helpers_integration::testRunGraphDetectsInterruptAndYieldsInterruptEvent` — pre-existing
7. `test_web_pages::testActivePageIndicatorDashboard` — pre-existing

**6 new tests in `tests/test_sse_content_routing.py` — all green.**

## UAT Gap 1 Sub-item Mapping

| Sub-item | Status |
|----------|--------|
| Route extraction-result table to main chat channel (not thinking panel) | **COVERED by this plan** — AIMessage with markdown table + askHuman tool_call now emits SseEvent.MESSAGE before thinkingEntries |
| Route policy-summary narrative to chat channel | **COVERED by this plan** — same mechanism, any prose >= 40 chars passes the gate |
| Clear stale interrupt text between turns | NOT this plan → 13-11 (Fix B) |
| Neutral styling for interrupt/askHuman container | NOT this plan → 13-11 (Fix B) |

## Residual Gap 1 Sub-items (not covered here)

Per plan's `<output>` section:

1. **Stale `#interruptTarget` bubble** — not cleared between turns (H2). Fixed in plan 13-11 (Fix B).
2. **Red-italic styling on `#interruptTarget`** — tertiary palette implies "error" for routine questions. Fixed in plan 13-11 (Fix B).
3. **`clarificationPending` never cleared** (H3) — latent bug that causes the same symptom under unsupported-currency flows. Fixed in plan 13-12 (Fix C).

## TODO markers for follow-up

- `TODO(13-11)`: verify `#interruptTarget` shows neutral styling after 13-11 lands
- `TODO(13-12)`: verify clarificationPending is cleared after askHuman resolves (post-justification flow)

## Deviations from Plan

### Deviation 1 — tokenBuffer-OR-output.content fallback (auto-fix, Rule 1)

**Found during:** Task 2 implementation

**Issue:** The plan assumed `tokenBuffer` would contain the AIMessage content when `on_chat_model_end` fires. In real streaming this is correct (chunks accumulate in `tokenBuffer`). But tests only emit a single `on_chat_model_end` event with no preceding `on_chat_model_stream`, so `tokenBuffer = ""`. The fix is also needed for any model that emits content only in the end event rather than streaming.

**Fix:** `rawContent = tokenBuffer.strip() or (getattr(output, "content", "") if output is not None else "")` — tokenBuffer-first with output.content as fallback.

**Files modified:** `src/agentic_claims/web/sseHelpers.py`

### Deviation 2 — test_reasoningContentStillRoutesToThinkingPanel: added stream chunk for reasoningBuffer

**Found during:** Task 1 → Task 2 integration

**Issue:** Original test sent only `on_chat_model_end` event. The `reasoningBuffer` is populated in `on_chat_model_stream` handler (L905-916), not from `on_chat_model_end.output.additional_kwargs`. The test's STEP_CONTENT assertion failed because `reasoningBuffer` was empty.

**Fix:** Added a `on_chat_model_stream` chunk event with `additional_kwargs={"reasoning_content": reasoning}` before the end event. This accurately reflects the real streaming flow and exercises the existing reasoning accumulation path.

**Files modified:** `tests/test_sse_content_routing.py`

### Deviation 3 — reasoningText source: removed cleanedBuffer fallback

**Found during:** Task 2 implementation review

**Issue:** Original code set `reasoningText = reasoningBuffer.strip() or cleanedBuffer or ""` — using cleaned buffer as a fallback source for the STEP_CONTENT reasoning preview. After Fix A, `cleanedBuffer` is either promoted to a MESSAGE bubble or appended to thinking entries — it should NOT also drive the STEP_CONTENT event, as that would double-display content as reasoning summary.

**Fix:** Changed to `reasoningText = reasoningBuffer.strip() or ""` — only private reasoning (from `reasoning_content` metadata) drives STEP_CONTENT.

**Files modified:** `src/agentic_claims/web/sseHelpers.py`
