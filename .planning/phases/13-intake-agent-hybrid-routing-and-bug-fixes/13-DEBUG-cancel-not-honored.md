---
status: diagnosed
trigger: "UAT Gap 5 — user types 'cancel' at policy-exception prompt; agent does NOT abandon; submitClaimGuard rewrites hallucinated submit to canonical retry"
created: 2026-04-13
---

# Debug: Cancel Keyword Not Honoured at Policy-Exception Prompt

## Symptom recap

VND session, claim `8ff626a3`, UAT Gap 5:

1. Agent enters policy-exception branch (lunch cap), calls `askHuman("A policy exception was flagged. Please provide a brief justification to proceed, or say 'cancel' to abandon the submission.")`.
2. `00:01:29` User: `cancel`.
3. `00:01:34` Agent next turn: **LLM emits a plain-text AIMessage claiming the claim was submitted**, without any `submitClaim` tool_call. `sse.hallucinated_submit_detected` fires.
4. `submitClaimGuard` correctly classifies this as a fabricated success → sets `validatorEscalate=True` OR the SSE layer rewrites the response to the canonical retry template ("I encountered an issue submitting your claim... please type 'submit' or 'yes'").
5. Net effect: user's explicit `cancel` is ignored; claim remains in draft / becomes stuck on a retry prompt; no abandonment path is ever taken.

## Current flow (code trace)

When the user types `cancel` in response to the Phase 2 askHuman interrupt, the current execution is:

- `chat.py` sends `Command(resume="cancel")` into the graph.
- `preIntakeValidator` runs (`node.py:363-396`):
  - increments `turnIndex`, resets `validatorRetryCount=0`.
  - calls `postToolFlagSetter(state)` — but on turn start there are no NEW ToolMessages yet (the askHuman ToolMessage with `"cancel"` is materialised inside the subgraph when `Command(resume=...)` is processed). So no flag changes here.
  - calls `submitClaimGuard(state)` — last AIMessage is the prior askHuman tool_call turn; no submission-success language yet; no-op.
- `intakeNode` → `buildIntakeSubgraph.ainvoke(...)` (`node.py:523`).
  - Inside subgraph, the askHuman tool returns `"cancel"`; a ToolMessage with `name="askHuman", content="cancel"` is appended to `messages`.
  - `preModelHook` runs (`preModelHook.py`):
    - `clarificationPending` is True (from the prior convertCurrency(VND)/policy turn — F1 clearing applies only when the postToolFlagSetter runs AFTER the askHuman ToolMessage, which happens in the outer wrapper, not here).
    - Injects ROUTING DIRECTIVE: "A clarification is pending. You must call askHuman to surface the question. Do NOT emit a plain-text question."
    - Does **NOT** know about the word "cancel". There is zero cancel-aware code in preModelHook.
  - LLM is invoked. The v5 system prompt Phase 2 step-6 (lines 171-174) instructs:
    > If the reply contains "cancel" (case-insensitive): do NOT submit. Call askHuman("Would you like to upload a different receipt or abandon this claim?"). Do not proceed to Phase 3.
  - **The LLM ignores this instruction.** Observed behaviour: it emits a plain-text AIMessage with submission-success phrasing (hallucinated submit). This is the same class of drift observed in Gap 4 (step 6 askHuman is inconsistently obeyed).
  - `postModelHook` runs on the hallucinated AIMessage:
    - `hasContent=True`, `hasToolCalls=False`, `clarificationPending=True` → drift triggers.
    - First drift: RemoveMessage + CORRECTION SystemMessage, `validatorRetryCount=1`. Subgraph loops.
    - On the retry, the LLM STILL does not call askHuman with the abandon prompt; re-emits similar text or a slight variant. Second drift → `validatorEscalate=True`.
  - Subgraph returns. Alternatively, on certain runs the hallucinated AIMessage survives the postModelHook (e.g. if `clarificationPending` was cleared by askHuman-resolution before the drift check — F1 semantics in `postToolFlagSetter.py:176-191` clear the flag when `askHuman` ToolMessage is present AND no new unsupported-currency event).
- Back in outer `intakeNode`:
  - `_mergeSubgraphResult` + `_scanToolMessages` produce the merged state.
  - `postToolFlagSetter(postSubgraphState)` runs (`node.py:554`). The askHuman ToolMessage for "cancel" clears `clarificationPending=False` (F1 fix).
  - `submitClaimGuard(postSubgraphState)` runs (`node.py:557`). The last AIMessage has submission-success language AND no matching `submitClaim` tool_call in the turn → sets `validatorEscalate=True`.
- `postIntakeRouter` sees `validatorEscalate=True` → routes to `humanEscalationNode`.
- OR, in the SSE path (if the LLM output streams before the guard writes state), the SSE layer emits `sse.hallucinated_submit_detected` and rewrites the displayed text to the canonical retry ("please type 'submit' or 'yes'").

Either way: the user's `cancel` does not cause the intended abandon/offer-alternative path. The system treats the LLM's hallucinated submit as the primary event and reacts to that.

## Root cause

**Prompt-only enforcement of the `cancel` keyword.** The entire cancel-handling contract lives in `agentSystemPrompt_v5.py` step-6 (descriptive English). There is:

- **No code-level detection** of the `cancel` keyword on the incoming resume payload.
- **No state flag** representing "user has requested abandonment".
- **No router branch** that maps a cancel resume to a terminal node.
- **No guardrail** preventing the LLM from inventing a submission after the user says cancel.

The LLM reliably violates step-6 (same failure mode as Gap 4 "askHuman inconsistency"). `submitClaimGuard` catches the downstream hallucination correctly, but its canonical-retry rewrite is tuned for the "retry submit" case and is the wrong semantic for the "user explicitly cancelled" case. The user ends up in a retry loop on a claim they asked to abandon.

This is the same failure class as Plan 13-12 Gap 3 (clarificationPending never cleared) and Gap 4 (askHuman not called): **prompt-based instructions on critical routing paths are not reliable; they must become code.**

## Design options

### Option A — preModelHook cancel short-circuit (directive-only)

`preModelHook` inspects the last HumanMessage (or the last askHuman ToolMessage content, since `Command(resume=...)` populates the ToolMessage). If it matches `^\s*(cancel|abandon|stop|quit)\b` AND `violations` is non-empty (scope: only during policy-exception prompt) AND `clarificationPending` is True:

- Set `cancelRequested=True` in state (reducer-safe bool).
- Inject ROUTING DIRECTIVE: "User cancelled. Acknowledge politely and do NOT call submitClaim. Call askHuman to offer upload-different-receipt vs. abandon."

Files: `preModelHook.py`, `state.py` (+`cancelRequested: bool`). Router unchanged.

**Pros:** minimal; reuses directive pattern already in place.
**Cons:** Still prompt-trusted at the final step — the directive tells the LLM what to do but cannot force it (same class of failure we are trying to fix). Observed Gap 4 proves directives alone are insufficient when the model is non-compliant. Rejected.

### Option B — new `claimAbandonedNode` terminal, routed via conditional edge

1. Add `cancelRequested: bool` to `ClaimState`.
2. In `postToolFlagSetter` (or a new `cancelDetector` function invoked alongside it), scan the most-recent `askHuman` ToolMessage content. If it matches the cancel regex AND the preceding askHuman question is the policy-exception prompt (heuristic: `violations` non-empty OR pending clarification), set `cancelRequested=True`.
3. Extend `postIntakeRouter` with a new branch: if `cancelRequested=True` → return `"claimAbandoned"`.
4. Add `claimAbandonedNode` (new file `src/agentic_claims/agents/intake/nodes/claimAbandoned.py`) that:
   - Emits `AIMessage(content="Got it — I've abandoned this claim. Would you like to upload a different receipt or end the session?")` (or similar).
   - Writes `status="cancelled"` and `claimSubmitted=False`.
   - Optionally persists via `updateClaimStatus` if `dbClaimId` exists (unlikely at this phase — no submit happened).
   - Clears `cancelRequested=False`.
5. `graph.py` adds `builder.add_node("claimAbandoned", claimAbandonedNode)`, maps `"claimAbandoned"` branch → `claimAbandonedNode` → END.

**Pros:** The cancel path becomes fully deterministic. LLM is bypassed entirely after cancel detection. Mirrors existing `humanEscalationNode` pattern (terminal, status-updating, template message). Extensible to other explicit-intent keywords.
**Cons:** More surface area (one new node, one new edge, one new state field, one new detection function). Requires a graph-shape change.

### Option C — extend `submitClaimGuard` to branch on cancel

When `submitClaimGuard` detects a hallucinated submission-success AIMessage, AND the most recent `askHuman` ToolMessage content matches the cancel regex, route to a cancel-acknowledgment path instead of the canonical retry rewrite.

**Pros:** Tiniest code change; lives in the already-correct guard.
**Cons:**
- Only fires when the LLM hallucinates a submit. If the LLM says something else plain-text (e.g. "OK, let me help you…" with no submit language), the guard never fires and the cancel is still missed. This couples cancel-handling to the specific failure mode of hallucinated-submit, which is fragile.
- Conflates two unrelated concerns (submit hallucination detection vs. explicit user cancel). Violates separation-of-concerns; the guard is a safety net, not a router.
- The SSE-layer canonical-retry rewrite and the state-layer guard update race; fixing both consistently is more invasive than Option B.

Rejected.

## Recommendation — Option B (deterministic code-level detection + dedicated terminal node)

Rationale:
1. **Matches the Phase 13 architectural principle** established in Gap 3 and 13-12 F1/F2: critical routing decisions move from prompt to code. Cancel is a critical routing decision.
2. **Deterministic.** The regex match + flag + conditional edge cannot be bypassed by LLM non-compliance. We observed in the live log that the LLM cannot be trusted on step-6.
3. **Orthogonal to existing hooks.** Does not change `preModelHook`, `postModelHook`, or `submitClaimGuard` semantics — each keeps its single responsibility.
4. **Mirrors `humanEscalationNode`.** We already have the terminal-node pattern (status update, template message, graph.add_edge to END). A `claimAbandonedNode` is the same shape with a different status and message.
5. **Removes the broken prompt contract.** Once Option B is in, agentSystemPrompt_v5 step-6 can be deleted (or reduced to a single line: "If the user cancels, the system will handle it — you will not be asked"). This reduces LLM confusion and aligns the prompt with what the code actually does.

### Minimal change set

| File | Change |
|------|--------|
| `src/agentic_claims/core/state.py` | Add `cancelRequested: bool` field (last-write-wins, no reducer). |
| `src/agentic_claims/agents/intake/node.py` | Add `cancelRequested` to `IntakeSubgraphState` and `_SUBGRAPH_PROPAGATE_KEYS`. |
| `src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py` | Add cancel-keyword scan on `askHuman` ToolMessages. If match, set `cancelRequested=True`. Regex: `^\s*(cancel|abandon|stop|quit)\b` (case-insensitive). Gate on `clarificationPending=True OR violations non-empty` to avoid false positives when the user says "cancel" in an unrelated context. |
| `src/agentic_claims/agents/intake/node.py` (`postIntakeRouter`) | Add new branch: if `state.get("cancelRequested")` → return `"claimAbandoned"`. Precedence: cancel > validatorEscalate > askHumanCount loop-bound. |
| `src/agentic_claims/agents/intake/nodes/claimAbandoned.py` | NEW. Emits terminal message, sets `status="cancelled"`, `claimSubmitted=False`, clears `cancelRequested=False`. |
| `src/agentic_claims/core/graph.py` | Register `claimAbandoned` node, add to conditional-edge mapping, add `builder.add_edge("claimAbandoned", END)`. |
| `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py` | Delete step-6 (lines 171-179) or reduce to a single informational sentence. Prevents the LLM from believing it still owns the cancel contract. |
| `tests/test_cancel_handling.py` | NEW. Unit tests: cancel regex variants, flag-setter gating, router precedence, node message + status + claimSubmitted=False. |

### State field

One new field in `ClaimState`:

```
cancelRequested: bool
```

- Default: `False` (falsy when absent).
- Reducer: none (last-write-wins boolean, same as `clarificationPending`, `validatorEscalate`).
- Write sites: `postToolFlagSetter` sets True on cancel-keyword detection; `claimAbandonedNode` sets False after handling.
- Read sites: `postIntakeRouter` only.

### Precedence ordering in `postIntakeRouter`

Explicit user-intent (cancel) takes priority over all other escalation signals:

```
if state.get("cancelRequested"):          return "claimAbandoned"
if state.get("validatorEscalate"):         return "humanEscalation"
if int(state.get("askHumanCount", 0)) > 3: return "humanEscalation"
return "continue"
```

Rationale: when the user explicitly asks to abandon, we must honour that even if the LLM simultaneously triggered a different escalation class (e.g. `validatorEscalate` from the very hallucinated submit this fix eliminates). The cancel is the user's semantic intent; the escalation is an ML artefact of the same turn.

### Out of scope for this fix

- Extending cancel detection to non-policy-exception contexts (e.g. cancel during field confirmation). That is a separate scope; current UAT gap is narrow to the policy-exception prompt.
- Confirming abandon with a second askHuman ("Are you sure?"). Current prompt already promises `cancel` is terminal; adding a confirmation step changes UX contract.
- i18n / localisation of cancel keyword. English-only per existing prompt contract.

## Summary

Cancel is currently a prompt instruction that the LLM ignores. The guard that catches the downstream hallucination cannot tell "user cancelled" apart from "LLM fabricated a submit". Fix: lift cancel handling from prompt to code via a new `cancelRequested` state field, a detection rule in `postToolFlagSetter`, a dedicated terminal `claimAbandonedNode`, and a router branch with highest precedence. Delete step-6 from the v5 prompt. Aligns with the Phase 13 pattern of moving critical routing from prompt to code (same as 13-12 F1 `clarificationPending` clearing).
