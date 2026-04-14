# 13-DEBUG — Tool Name Leak (Gap 6)

**Status:** Diagnosed — root cause isolated, no code written.
**Triggered by:** UAT Gap 6 — "askHuman" visible in thinking panel; user feedback: "askHuman is an internal thing, should not be exposed".
**Live evidence:** German session d6ab0ed2 — `docker compose logs app` @ 00:04:27 shows `tool.start toolName="askHuman"`; UI thinking panel rendered "Completed askHuman".
**Cross-reference:** 13-11 executor salvage note — suspicion that askHuman output may route to reasoning/thinking channel instead of `sse-swap="interrupt"`.

---

## 1. SSE Event Taxonomy

All events emitted by `runGraph()` in `src/agentic_claims/web/sseHelpers.py`. Event name constants live in `src/agentic_claims/web/sseEvents.py` (`SseEvent` class).

| Event (const) | Wire name | Emitted at (line, sseHelpers.py) | Payload | Template consumer | Consumer DOM id |
|---|---|---|---|---|---|
| `TOKEN` | `token` | 903 (on_chat_model_stream) | raw chunk | — (tokens appended directly) | `#tokenTarget` |
| `THINKING_START` | `thinking-start` | 782 (turn start) | `<!-- thinking -->` | — (trigger only, clears UI) | hidden div |
| `STEP_NAME` | `step-name` | **1114 (on_tool_start)**, 1040 (reasoning preview), 1064 (reasoning_b preview), 1073 ("Preparing response...") | **label string** — `TOOL_LABELS[toolName]` or `f"Running {toolName}..."` fallback | — (dispatched as `tool-step` CustomEvent → Alpine `activeToolName`) | `#thinkingStepName` (hidden), visible via `x-text="activeToolName"` |
| `STEP_CONTENT` | `step-content` | **1178 (on_tool_end)**, 1046/1070 (reasoning preview HTML) | **raw HTML** — `<div class="text-xs text-outline mt-1">{summary}</div>` where `summary = _summarizeToolOutput(toolName, toolOutput)` | — (appended via `hx-swap="beforeend"`) | `#thinkingContent` |
| `MESSAGE` | `message` | 991 (mid-stream prose), 1574 (hallucinated-submit error), 1591 (final reply) | rendered `partials/message_bubble.html` | `partials/message_bubble.html` | `#aiMessages` |
| `SUMMARY_UPDATE` | `summary-update` | 1330 (end of turn) | rendered `partials/summary_panel.html` | `partials/summary_panel.html` | (`#summary*`) |
| `PATHWAY_UPDATE` | `pathway-update` | 796, 1131 (tool start), 1210 (tool end) | rendered `partials/decision_pathway.html` | `partials/decision_pathway.html` | `#pathwayContent` |
| `TABLE_UPDATE` | `table-update` | 1265 (after extract/submit), 1456 (post-advisor) | rendered `partials/submission_table.html` | `partials/submission_table.html` | `#tableContent` |
| `INTERRUPT` | `interrupt` | **1507 (post-turn interrupt check)** | `payload["question"]` as plain text | — (raw text swap, default styling) | `#interruptTarget` |
| `DONE` | `done` | (end of stream) | sentinel | — | `#doneTarget` |
| `ERROR` | `error` | 1288 (stream exception) | exception str | — | `#errorTarget` |

**No separate `tool.start` / `tool.end` wire events exist.** Those names appear only in structured log records (`logEvent` calls at lines 1100 and 1153). The UI receives tool lifecycle solely via `step-name` + `step-content`.

**Thinking panel = STEP_NAME + STEP_CONTENT streams.** Both flow into visible UI: step-name into the `activeToolName` label (top of collapsed panel), step-content into the expanded entry list.

---

## 2. askHuman-specific Flow

When the LLM issues a tool_call for `askHuman`, LangGraph `astream_events(version="v2")` yields:

1. `on_chat_model_end` (line 918) — tool_call detected; `pendingToolCalls` increments.
2. **`on_tool_start`** (line 1093) with `event["name"] == "askHuman"`:
   - line 1114 → **yield STEP_NAME = `"Waiting for your input..."`** (via `TOOL_LABELS["askHuman"]`). This IS already user-friendly.
   - `toolName` not in `TOOL_TO_STEP` → no pathway update.
3. Inside the tool body (`askHuman.py:25`), `interrupt({"question": question})` fires. LangGraph treats this as a graceful pause.
4. **`on_tool_end`** — **does fire** for interrupt-based tools: LangGraph surfaces the interrupt by yielding an on_tool_end event whose `output` is the `Interrupt` marker (empty/sentinel). At line 1145:
   - `toolName = "askHuman"`, `toolOutput = ""` (or Interrupt sentinel).
   - line 1149 → `summary = _summarizeToolOutput("askHuman", "")`. `_summarizeToolOutput` has **NO branch for askHuman** → falls through to the final `return f"Completed {toolName}"` at line 163 or 166.
   - line 1178 → **yield STEP_CONTENT = `<div class="text-xs text-outline mt-1">Completed askHuman</div>`**.
   - This is the exact string the user saw.
5. `astream_events` generator exits (graph is paused at the interrupt checkpoint).
6. Post-loop: `finalState = graph.aget_state(...)` returns a snapshot with `finalState.next != ()` and `tasks[*].interrupts` populated.
7. Line 1492-1508 — interrupt check IS reached (the block is inside `else: # not shouldTerminateEarly`, which is the path askHuman takes because it's a non-submission flow).
   - line 1507 → **yield INTERRUPT = `question`** → swaps into `#interruptTarget` correctly.

**Conclusion re: 13-11 salvage claim.** The claim "askHuman output may be routing to reasoning/thinking channel instead of interrupt" is **partially correct but mis-attributed**:

- The `#interruptTarget` IS receiving the interrupt event (line 1507 confirms). The interrupt question reaches the correct channel.
- What ALSO happens is the `step-name` / `step-content` pair leaks tool lifecycle info into the thinking panel (`#thinkingStepName` + `#thinkingContent`) before the interrupt event fires.
- 13-11's DOM cleanup hook on `#interruptTarget` was not failing E2E because the interrupt never arrived — it was failing because the clarification prompt is ALSO pre-emptively visible in the thinking panel, confusing the mental model of which channel "owns" the prompt.

**Subtlety:** The interrupt event is emitted only when `shouldTerminateEarly == False`. Phase 13 introduced `shouldTerminateEarly` for the submit path (BUG-026/027/028/029). If a future regression enables `shouldTerminateEarly` for an askHuman path, the interrupt emission at 1507 would be skipped — that code path should be audited when touching that branch.

---

## 3. Tool-name Rendering

**Raw toolName touches the DOM from two code sites:**

| Site | File:line | What renders | Visible? |
|---|---|---|---|
| STEP_NAME fallback | sseHelpers.py:1113 — `label = TOOL_LABELS.get(toolName, f"Running {toolName}...")` | `f"Running {toolName}..."` if tool not in TOOL_LABELS | Yes — appears in `activeToolName` badge |
| STEP_CONTENT summary | sseHelpers.py:127, 163, 166 — `_summarizeToolOutput` returns `f"Completed {toolName}"` for any dict-parse failure, non-dict, or tools without a dedicated branch (including **askHuman** and **getClaimSchema** as default-else, though getClaimSchema has a branch at line 132) | Raw `Completed askHuman` string | Yes — appended into `#thinkingContent` |

**A label map already exists** (`TOOL_LABELS` at sseHelpers.py:38-45). It's **used for STEP_NAME but NOT for STEP_CONTENT**. The content-summary function (`_summarizeToolOutput`) reverts to raw `toolName` in its default branch.

No template partial references the raw toolName directly. All leakage is from `sseHelpers.py` composing the raw HTML string server-side and shipping it into `step-content`.

---

## 4. Design Options

### Option A — Label mapping in STEP_CONTENT

Add a completion-label dict (or reuse `TOOL_LABELS` with a second "completed" form) and thread it through `_summarizeToolOutput` so the fallback strings become:

- `"Asked for clarification"` (askHuman)
- `"Finished reading receipt"` (extractReceiptFields — already has dedicated branch, so unchanged)
- `"Policy check complete"` (searchPolicies — already has dedicated branch)
- `"Currency converted"` (convertCurrency — already has dedicated branch)
- `"Claim submitted"` (submitClaim — already has dedicated branch)
- `"Claim schema loaded"` (getClaimSchema — already has dedicated branch)
- Generic unknown: `"Step complete"` (never reveal toolName)

**Pros:** Minimal change; fixes leakage everywhere it occurs; preserves existing per-tool narrative summaries for tools with dedicated branches.
**Cons:** askHuman still appears in the thinking panel at all (as "Asked for clarification"). The UX concern is not just the raw name — it's also the *existence* of an askHuman entry in the reasoning trace, since the question is already visible as an interrupt bubble. Duplicates signal.

### Option B — Filter askHuman from thinking panel entirely

At the `on_tool_start` / `on_tool_end` sites (lines 1093-1142 and 1144-1276), skip STEP_NAME / STEP_CONTENT emission when `toolName == "askHuman"`. Rely solely on the INTERRUPT channel (already wired via line 1507 → `#interruptTarget`) to surface the question.

**Pros:** Addresses user's exact complaint (askHuman shouldn't be exposed). Clean separation: interrupts own the interrupt channel; thinking panel owns tool reasoning.
**Cons:** Only addresses askHuman. Other tools (if future additions land without a `_summarizeToolOutput` branch) will still leak `Completed <rawName>`. Doesn't fix the hygiene risk systemically.

### Option C — Both (recommended)

1. **Label mapping everywhere** — defensive default in `_summarizeToolOutput` so no raw toolName can reach the DOM.
2. **Special-case askHuman** — skip STEP_NAME and STEP_CONTENT emission; also skip `thinkingEntries.append({...name: "askHuman"...})` so it doesn't contaminate downstream progress calculations that key off tool-name inspection (line 394 in `_calcProgressPct` already treats askHuman as 66% progress — this logic needs a replacement signal if askHuman disappears from thinkingEntries; see §5).

**Pros:** Addresses both the user complaint and the systemic hygiene gap.
**Cons:** More surface area to touch; need to preserve the `askHuman in completedTools → 66%` progress semantic via a substitute (e.g., check for `finalState.tasks[*].interrupts` or track a dedicated `askHumanSeen` local flag in `runGraph`).

---

## 5. Recommendation — Option C

**Files to change (3):**

### (1) `src/agentic_claims/web/sseHelpers.py`

- **Extend `TOOL_LABELS`** (or add sibling `TOOL_COMPLETION_LABELS`) with completion phrasing, e.g.:
  - `askHuman`: `"Asked for clarification"` — *not emitted; kept for defensive fallback only.*
  - `getClaimSchema`: `"Claim schema loaded"`
  - `extractReceiptFields`: `"Receipt read"`
  - `searchPolicies`: `"Policy check complete"`
  - `convertCurrency`: `"Currency converted"`
  - `submitClaim`: `"Claim submitted"`
- **`_summarizeToolOutput` fallback** (lines 127, 163, 166) — replace `f"Completed {toolName}"` with `TOOL_COMPLETION_LABELS.get(toolName, "Step complete")`.
- **`on_tool_start` block** (around line 1093) — wrap STEP_NAME yield + pathway update in `if toolName != "askHuman":`. For askHuman, skip STEP_NAME entirely (the interrupt bubble will appear shortly; meanwhile Alpine's default `activeToolName = "Analyzing..."` stays).
- **`on_tool_end` block** (around line 1144) — wrap STEP_CONTENT yield and `thinkingEntries.append` in `if toolName != "askHuman":`. Also skip `pendingToolCalls` decrement? No — keep bookkeeping intact; just suppress the UI emission.
- **`_calcProgressPct`** (line 394) — the `"askHuman" in completedTools` branch becomes unreachable if askHuman is filtered out of thinkingEntries. Replace with an alternate signal: add a local `askHumanFired` bool set inside `runGraph` at the askHuman on_tool_start site, and pass through to `_calcProgressPct`. (Or: accept losing the 66% progress bump for askHuman — the existing `convertCurrency` or `searchPolicies` completions already drive to 50%+, and the subsequent resume turn will push past.)

### (2) `src/agentic_claims/agents/intake/tools/askHuman.py`

- No changes required. Current implementation is correct. (Keep as reference for Option-B scope bound.)

### (3) `templates/chat.html`

- No template changes required. The fix is entirely server-side. `#interruptTarget` already has correct styling from 13-11 (line 92-94).

**Tests to add / update (tests dir):**

- `tests/test_sse_helpers_integration.py` — add case: given an askHuman tool event stream, assert NO STEP_NAME / STEP_CONTENT events are yielded for toolName=askHuman, AND an INTERRUPT event IS yielded.
- Unit test for `_summarizeToolOutput` — assert no return value contains a raw toolName (regex `r"(askHuman|extractReceiptFields|searchPolicies|convertCurrency|submitClaim|getClaimSchema)"` must not appear).

---

## 6. Verification

### Does askHuman content today actually reach `sse-swap="interrupt"`?

**YES.** Traced via `runGraph()`:

- Line 1492-1508 executes in the else-branch of `shouldTerminateEarly`. For askHuman flows, `shouldTerminateEarly` remains False (only submitClaim sets it at line 1246).
- `finalState = graph.aget_state(config)` (line 1310) returns a snapshot where `finalState.next` is truthy (graph is paused) and `finalState.tasks[*].interrupts` contains the askHuman payload.
- Line 1494 `if finalState and finalState.next:` → True → loops tasks → line 1496 `if hasattr(task, "interrupts") and task.interrupts:` → True → extracts `payload["question"]` → **line 1507 `yield ServerSentEvent(raw_data=question, event=SseEvent.INTERRUPT)`** → hits `#interruptTarget` via `sse-swap="interrupt"` (chat.html:92).

**Supporting log evidence** (UAT Gap 6 note, line 121 of 13-UAT.md): German session d6ab0ed2 logged `taskCount=1, tasksWithInterrupts=[{name:intake, interruptCount:1}]` from the `debug.interrupt_check` probe at line 1470. That probe only fires on the same code path that yields the INTERRUPT event.

### Conclusion on 13-11 executor's suspicion

**Not a Phase-13 regression from 13-09's interruptDetection.py refactor.** The `isPausedAtInterrupt` helper (interruptDetection.py) is only used on the NEXT HTTP request (to decide whether to build `Command(resume=...)`) — it doesn't affect SSE emission on the askHuman-emitting turn. The interrupt event is correctly emitted today.

The 13-11 executor's inability to exercise the `#interruptTarget` cleanup hook E2E was likely due to:

1. **Dev-loop observation bias**: the "Completed askHuman" leak in the thinking panel made it feel like the interrupt channel wasn't firing, even though it was.
2. **`thinking-start` clear-out hook** (chat.html:77) clears `#interruptTarget.innerHTML` at the START of the NEXT turn, which is the correct behavior — but if the next turn doesn't arrive (user doesn't reply), the hook never runs and 13-11's cleanup appears untested.

**Therefore:** The fix scope is display-layer only (Option C applied to `sseHelpers.py`). No rework of `interruptDetection.py` or the resume contract is required.

---

## Summary of Root Cause

**Two independent leakage sites in `sseHelpers.py`, both rooted in missing label coverage:**

1. **STEP_CONTENT** (line 1178): `_summarizeToolOutput` falls through to `f"Completed {toolName}"` for askHuman (no branch) and any future tool lacking a dedicated branch. Directly renders raw internal name into `#thinkingContent`.
2. **STEP_NAME** (line 1114): `TOOL_LABELS.get(toolName, f"Running {toolName}...")` — the fallback leaks raw name for tools not in the dict. (Currently all 6 tools are mapped, so no immediate leak; hygiene risk for future tools.)

Fix = Option C: defensive labels everywhere + suppress askHuman from thinking panel (interrupt channel is its proper home, already correctly wired).
