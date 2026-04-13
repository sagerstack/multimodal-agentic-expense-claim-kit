---
status: diagnosed
trigger: "Pervasive UI display regression (UAT tests 1, 4, 6): substantive agent content collapses into 'Thought for Xs' thinking panel; only visible bubble is red-italic askHuman question; stale interrupt text persists across turns"
created: 2026-04-13
updated: 2026-04-13
scope: diagnosis-only (no fix applied)
---

## Symptoms (user-reported)

- Expected: after receipt upload, agent displays extracted-fields markdown table AND asks confirmation question.
- Actual: extracted-fields table never appears as a visible chat bubble; it is hidden inside the collapsed "Thought for Xs · N tools" panel.
- Only visible AI-side content: a red-italic box containing the askHuman question (e.g. "Do the details above look correct?" or "A policy exception was flagged. Please provide a brief justification…").
- Stale behaviour: that red-italic box persists across later turns, sometimes displaying a prior turn's question alongside the new turn's UI.
- Affected UAT: tests 1, 4, 6 (extraction turn, post-resume chat turn, post-resume after-askHuman turn).

## Root-cause summary (one sentence)

The v5 prompt tells the LLM to put the user-visible markdown table in the SAME AIMessage as the `askHuman` tool_call, but `runGraph` routes any AIMessage with `content + tool_calls` into the thinking panel as "reasoning" — never emitting it as a chat bubble — while the askHuman question itself is emitted as an `interrupt` event into a persistent DOM container (`#interruptTarget`) whose red-italic/tertiary styling is hardcoded and never cleared between turns.

## Hypothesis Tree (ranked by likelihood, highest first)

### H1 — CONFIRMED — "Content + tool_calls" AIMessages are classified as thinking

- **Location:** `src/agentic_claims/web/sseHelpers.py:940-976`
- **Mechanism:** In `runGraph`, the `on_chat_model_end` handler branches on whether the just-completed model output `hasToolCalls`. When True (line 943), the model's text content is appended to `thinkingEntries` as `{"type": "reasoning", ...}` (line 946-951) and a truncated 120-char preview is emitted as `STEP_CONTENT` (line 971). The content is NEVER emitted as an `SseEvent.MESSAGE`. Only the non-tool-calls path (line 977) sets `finalResponse = _stripToolCallJson(tokenBuffer)` (line 1008).
- **Why it fires for symptom 1:** `agentSystemPrompt_v5.py:130-143` (Phase 1, steps 6-9) instructs the LLM to (step 6) "Present extraction results as a markdown table", (step 7) optionally state the conversion line, (step 8) note missing fields, THEN (step 9) "Call askHuman(...)". A competent LLM packs steps 6-8 as AIMessage.content and step 9 as a tool_call on the SAME AIMessage. That message hits the `hasToolCalls` branch, so the table vanishes into thinking.
- **Why it fires for symptoms 4/6 (post-resume):** After the user confirms and the graph resumes, Phase 2 kicks in with the same structural pattern: (step 3) "Present the policy result in plain text", (step 4) "Show the finalized claim summary table", then (step 5 violation sub-case) "call askHuman(…justification…)". Same content+tool_call packing → same disappearance.
- **Evidence quality:** strong. Direct code inspection shows the branch exists and is unconditional for any AIMessage with tool_calls. Matches all three failure modes described in the UAT.
- **Falsifiable prediction:** If you inject a benign print of `endOutput.content` and `endOutput.tool_calls` inside the `on_chat_model_end` handler, you will observe the user-visible table in `content` every time `tool_calls` contains `askHuman`.

### H2 — CONFIRMED — `#interruptTarget` has fixed red-italic styling and is never cleared

- **Location:** `templates/chat.html:90-92`
- **Code (verbatim):**
  ```html
  <div id="interruptTarget" sse-swap="interrupt" hx-swap="innerHTML"
       hx-on::after-swap="window.dispatchEvent(new CustomEvent('stream-done'))"
       class="max-w-2xl text-sm text-tertiary italic p-4 bg-tertiary/5 rounded-2xl border border-tertiary/10 empty:hidden"></div>
  ```
- **Mechanism:**
  1. The container itself carries `text-tertiary italic bg-tertiary/5 border-tertiary/10` — the tertiary palette is the project's "escalated / warning" colour (cross-referenced in `templates/analytics.html:86`, `templates/partials/claims_table_rows.html:39-40`, etc.). This explains the "red-italic styled message" in symptom reports.
  2. HTMX `sse-swap="interrupt" hx-swap="innerHTML"` only overwrites the container's content when a NEW `interrupt` SSE event arrives. If the next turn does not emit an interrupt (e.g., user confirms and pipeline proceeds to submission), nothing clears the old question. `empty:hidden` only suppresses the element when its content is literally empty — once populated, the old text remains visible.
  3. Contrast with the chat bubble accumulator `#aiMessages` (chat.html:81-83) which IS cleared every turn via `moveAiMessages()` / `freezeTurn()` in Alpine logic (chat.html:302-366). And contrast with the thinking panel, which IS cleared on every `thinking-start` event via the hidden handler at chat.html:76-78.
- **Why it matches symptom 3 ("stale red messages persist across turns"):** exactly the mechanism the user describes.
- **Evidence quality:** strong. Direct template inspection; no code clears `#interruptTarget` anywhere in the repo.
- **Falsifiable prediction:** In DOM devtools, inspect `#interruptTarget` at the START of turn N+1 after an interrupt in turn N. Its `innerHTML` will still contain turn N's question text. The `empty:hidden` pseudo-class will NOT engage because the element is non-empty.

### H3 — CONFIRMED — `clarificationPending` is set but never cleared (latent time-bomb)

- **Locations:**
  - Written (True only): `src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py:148-149`
  - Read: `src/agentic_claims/agents/intake/hooks/preModelHook.py:61-71` (injects directive), `src/agentic_claims/agents/intake/hooks/postModelHook.py:52-66` (drift-trigger predicate)
  - ClaimState declaration: `src/agentic_claims/core/state.py:64`
- **Mechanism:** `postToolFlagSetter` sets `clarificationPending = True` when `convertCurrency` returns `{"supported": false}`. The value is `last-write-wins bool` (not a reducer), and no code path ever writes it back to `False`. Once flipped for a claim, every subsequent turn:
  - `preModelHook` injects a "You must call askHuman. Do NOT emit a plain-text question" directive.
  - `postModelHook` evaluates `hasContent AND not hasToolCalls AND clarificationPending` — any plain-text reply will be stripped via `RemoveMessage(id=bad_ai.id)` on the first drift and will trigger `validatorEscalate = True` on the second drift.
- **Impact on UAT tests 1, 4, 6:** the reported receipt images are likely SGD (no convertCurrency triggered), so H3 does NOT CAUSE these specific symptoms. However, for any claim where convertCurrency reports `supported=False`, this creates a hard lock-in: all future plain-text replies (including legitimate acknowledgements) get stripped, which would produce EXACTLY the "content disappears" symptom via a different pathway (RemoveMessage rather than the thinking-panel classifier). Treat this as a latent bug that will reproduce the same visible symptom under a different trigger.
- **Evidence quality:** strong. Grep for `clarificationPending.*False` returns only the default-read (no writes to False).
- **Falsifiable prediction:** Upload a receipt in an unsupported currency (e.g., MYR, IDR, a currency Frankfurter rejects). After the manual-rate turn resolves, the next turn's plain-text reply will be stripped and the model will be forced into a rewrite / escalation loop.

### H4 — PARTIAL — `finalResponse` is first-write-wins, masking later content

- **Location:** `src/agentic_claims/web/sseHelpers.py:1003-1008`
- **Mechanism:** The "BUG-016" guard `if not finalResponse: finalResponse = _stripToolCallJson(tokenBuffer)` intentionally keeps the first non-empty terminal AIMessage (intake's confirmation text) and ignores later post-submission agents' LLM outputs. However, when the FIRST non-tool-calls AIMessage has empty content (e.g. the ReAct loop's minimal closer after many tool calls), `finalResponse` gets set to `""` and subsequent substantive AIMessages cannot overwrite it. The `if not finalResponse` check treats `""` as falsy so this specific regression likely doesn't fire — but the guard is fragile.
- **Evidence quality:** medium. Real path is H1 + H2; this is a latent risk surface adjacent to it.

### H5 — RULED OUT — Post-model hook strips the extraction message

- **Considered:** could `postModelHook.RemoveMessage` be deleting the extraction AIMessage?
- **Disproven by:** the drift predicate requires `clarificationPending = True`. For the receipt-upload turn (test 1), convertCurrency hasn't been called, so clarificationPending is False. Additionally, the extraction AIMessage has `tool_calls = [askHuman]`, so the predicate's `not hasToolCalls` clause is False. Two independent reasons the hook does not fire on turn 1.
- **For turn 4/6 (post-resume):** by the time the LLM emits the policy table, it is accompanied by a tool_call (searchPolicies or submitClaim or askHuman). Same `not hasToolCalls` blocker.

### H6 — RULED OUT — DOM swap collision between `#tokenTarget` and `#aiMessages`

- **Considered:** could streaming tokens into `#tokenTarget` and the MESSAGE event into `#aiMessages` race?
- **Disproven by:** `onMessageSwapped()` (chat.html:379-391) explicitly clears `#tokenTarget.innerHTML = ''` before rendering. Standard flow is well-tested.

## Minimal reproduction path

### Repro 1 — Symptom 1 (extraction content collapses into thinking)

1. Start the app: `docker compose up -d --build && docker compose exec app poetry run alembic upgrade head`.
2. Log in, navigate to `/chat`.
3. Upload any clean SGD-currency receipt (e.g., `artifacts/receipts/*.jpg`) with a short description.
4. Observe: during streaming, the thinking panel shows `Reasoning...` followed by the first 120 chars of the extraction table. The expanded panel contains the full markdown table. The main chat area shows NO bubble containing the table.
5. After thinking completes, the only visible element between the user bubble and the input is the red-italic `#interruptTarget` containing "Do the details above look correct?".

### Repro 2 — Symptom 3 (stale red-italic box persists)

1. Complete Repro 1 steps 1-5.
2. Type "yes" and submit.
3. After the next turn completes, note that `#interruptTarget` still displays "Do the details above look correct?" — this is the PREVIOUS turn's question, still mounted, still red-italic.
4. DOM proof: open devtools, select `#interruptTarget`, confirm `innerHTML` is non-empty and matches the prior turn.

### Repro 3 — Symptom 2 (policy violation justification turn also collapses)

1. Upload a receipt that will trigger a policy violation (e.g. a meal > SGD 50).
2. Confirm details when asked.
3. Observe the turn in which the LLM summarises the violation and calls `askHuman(justification)`. The "Policy check: This exceeds…" narrative goes into thinking; only the red-italic askHuman question is visible.

## Recommended fix direction (no code written)

The diagnosis implicates three independent defects. Fix them separately — each is small and targeted.

### Fix A — Emit pre-askHuman content as a visible chat bubble (primary)

**File:** `src/agentic_claims/web/sseHelpers.py`
**Lines:** 943-976 (the `if hasToolCalls:` branch inside `on_chat_model_end`)

**Change:** when the model output has tool_calls AND has non-empty content, emit the content as a `SseEvent.MESSAGE` (rendering it through `partials/message_bubble.html`) BEFORE appending the tail to thinking. Do NOT short-circuit into reasoning. Reasoning should be reserved for `additional_kwargs.reasoning_content` / `response_metadata.reasoning_content` (the buffer already tracked at lines 886-896), not for user-addressed prose.

**Rationale:** Per v5 prompt, user-visible text BEFORE a tool call is the norm, not an edge case (extraction table, policy summary, conversion statement). Reasoning models' private thinking already flows through the separate `reasoningBuffer`; the cleaned `tokenBuffer` at line 944 is user-facing prose by construction.

**Caveats:**
- Preserve the existing stripping via `_stripToolCallJson` and `_stripThinkingTags`.
- Guard against duplicate emission if `askHuman` is the SOLE tool_call on the message (avoid a bubble that is just "thinking out loud" then a question appears right below). Likely rule: emit the content-as-message when `content.strip()` length > a threshold (say 40 chars) OR when content contains markdown structure (`|`, `##`, newlines).
- The `confidenceScores` and `violations` injection logic at lines 1505-1514 is tied to `MESSAGE` emission at the END of the stream. Decide whether the new mid-stream message should also carry those metadata, or leave them only on the end-of-stream bubble.

### Fix B — Clear `#interruptTarget` when a new turn starts

**File:** `templates/chat.html`
**Lines:** ~75-78 (the hidden `thinking-start` handler) OR ~283-300 (`onStreamDone`)

**Change:** on `thinking-start` (or on user-message submit), clear `#interruptTarget.innerHTML`. The simplest fix is to append to the existing hidden thinking-start handler:
```html
document.getElementById('interruptTarget').innerHTML = ''
```
Or, better, clear it inside `submitForm()` (chat.html:253-278) when the user sends a new message — this ensures clearing happens even if the server-side flow fails to emit `thinking-start`.

**Rationale:** the `#interruptTarget` is semantically "the current pending interrupt". Once the user responds (by submitting a message), the interrupt is consumed; showing its stale text is misleading.

**Alternative:** have `freezeTurn()` (chat.html:302-349) move the interrupt question into the chat flow as a historical AI message (clone its innerHTML, wrap in message_bubble markup with isAi=True, insert before thinkingPanel) — then clear `#interruptTarget`. This preserves history in a consistent bubble form instead of letting it hang in a side channel.

### Fix C — Clear `clarificationPending` when the clarification is answered

**File:** `src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py`
**Lines:** 95-111 (where `clarificationPending = True` is set)

**Change:** in the same loop, when an `askHuman` ToolMessage is seen (line 114), set `clarificationPending = False` in the updates dict. The semantics: pending clarification is cleared when the user has supplied an answer (i.e. the askHuman tool returned, which is exactly when we increment askHumanCount).

**Rationale:** matches the state machine the hooks imply. The current implementation sets True on convertCurrency-unsupported and never clears, which will eventually strip legitimate AIMessages. This fix is independent of A and B but should ship in the same change to prevent future regressions.

**Edge case:** convertCurrency may be called AGAIN after manual rate — make sure the new flag write still flows. Since both directions are driven off the trailing ToolMessage run scan, the natural behaviour is correct: whichever tool ran last in the turn wins.

### Sequencing

1. Fix B (template-only, lowest risk, immediately clears stale red text).
2. Fix A (SSE classification — restores visibility of extraction/policy content).
3. Fix C (state hygiene — prevents the latent form of the same symptom under unsupported-currency flows).

Each fix is independently testable and independently revertable.

## Related issues discovered (noted, not in scope)

- `templates/chat.html:92` uses `text-tertiary italic` unconditionally for ALL interrupts. The askHuman questions are not errors or warnings — they are routine conversational turns. Consider restyling to match the normal AI bubble (`bg-surface-container-low`, `text-on-surface`, non-italic) so the UI does not imply "something is wrong" every time the agent asks a question.
- `sseHelpers.py:1007` ("BUG-016 guard") `if not finalResponse: finalResponse = _stripToolCallJson(tokenBuffer)` is first-write-wins. If a future change lets an earlier non-tool-call AIMessage slip through with empty content, subsequent substantive content would be masked. Consider making this explicit: `if not finalResponse.strip()`.
- `humanEscalationNode` emits its AIMessage outside the LLM-stream path, so the existing `on_chat_model_end` → `finalResponse` capture never sees it. The fallback in `_getFallbackMessage` (sseHelpers.py:327-349) rescues this via `graph.aget_state`, so it is likely fine — but this code path has no explicit UAT coverage for askHumanCount > 3 or validator-escalate flows.
- No integration test currently asserts that the extraction table appears as a visible bubble. Add a Playwright assertion: after upload+extraction, `#aiMessages` (or an already-frozen bubble ancestor of `chatHistory`) must contain a `<table>` element AND the table must be visible (not inside a `<details>` element).

## Files examined

- `src/agentic_claims/web/sseHelpers.py` (1533 lines, full read)
- `src/agentic_claims/web/sseEvents.py`
- `src/agentic_claims/web/routers/chat.py`
- `src/agentic_claims/web/interruptDetection.py`
- `src/agentic_claims/agents/intake/node.py`
- `src/agentic_claims/agents/intake/hooks/preModelHook.py`
- `src/agentic_claims/agents/intake/hooks/postModelHook.py`
- `src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py`
- `src/agentic_claims/agents/intake/hooks/submitClaimGuard.py`
- `src/agentic_claims/agents/intake/nodes/humanEscalation.py`
- `src/agentic_claims/agents/intake/tools/askHuman.py`
- `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py`
- `src/agentic_claims/core/graph.py`
- `templates/chat.html`
- `templates/partials/message_bubble.html`
