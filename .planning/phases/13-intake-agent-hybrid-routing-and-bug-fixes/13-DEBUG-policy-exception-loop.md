---
status: diagnosed
trigger: "UAT Test 2 — VND receipt, policy violation, justification provided, agent re-emits policy check verbatim, claim lands in ESCALATED"
created: 2026-04-13
---

# Debug: Policy-Exception Justification Loop → False Escalation

## Symptom recap

UAT Test 2 (VND receipt, SGD 21.62 lunch > SGD 20.00 cap):

1. User uploads VND receipt; `convertCurrency(VND)` returns `{supported: false}`.
2. Agent requests manual FX rate via `askHuman`; user provides rate.
3. Agent extracts fields, shows summary table, user confirms.
4. Agent runs `searchPolicies`; detects lunch-cap violation.
5. Agent emits "Policy check: This exceeds the lunch cap of SGD 20.00…" (plain text) AND calls `askHuman("A policy exception was flagged. Please provide a brief justification…")`.
6. User replies with justification.
7. **Agent next turn: "Thought for 12s · 0 tools" — re-emits the identical policy-check text verbatim.**
8. Claim lands in **ESCALATED** queue instead of being submitted.

## Hypothesis tree (ranked by likelihood)

### H1 (PRIMARY, very high confidence): `clarificationPending` is never cleared → postModelHook mis-identifies the justification-turn AIMessage as drift → soft-rewrite → second drift → `validatorEscalate=True`.

Mechanism (step-by-step reconstruction):

- Turn where `convertCurrency(VND)` runs, `postToolFlagSetter` sets `clarificationPending=True` (`postToolFlagSetter.py:149`). This flag is set on the very first unsupported-currency ToolMessage and is never touched again.
- Codebase search: the string `clarificationPending` appears in 8 files; the only write sites are:
  - `postToolFlagSetter.py:149` — sets True
  - `node.py:504` — forwards current value into subgraph input
  - No site ever writes False. **There is no clearing logic anywhere.**
- Every subsequent model call, `preModelHook` injects the directive:
  > "ROUTING DIRECTIVE: A clarification is pending. You must call askHuman to surface the question. Do NOT emit a plain-text question."
  (`preModelHook.py:62-71`)
- Every subsequent model call, `postModelHook` trigger predicate (`postModelHook.py:64-66`) is:
  ```
  isDrift = hasContent AND not hasToolCalls AND clarificationPending
  ```
  → any AIMessage that is plain-text with no tool calls (e.g. the policy-check summary sentence, or a final acknowledgement) is classified as drift.
- On the justification-turn, the user message resumes the graph via `Command(resume=justification_text)` (`chat.py:242`, `sseHelpers.py:789`). The `askHuman` tool returns the justification; `postToolFlagSetter` increments `askHumanCount` (+1) but **does not clear `clarificationPending`** — nothing does.
- The LLM then emits plain-text "Policy check: …" (the observed "0 tools" message). postModelHook drift trigger fires because `clarificationPending` is still True.
- First drift (`validatorRetryCount==0`, reset at turn start, `node.py:388`): RemoveMessage of the AIMessage + inject CORRECTION SystemMessage "You produced a user-facing question without calling askHuman. Retry: call the askHuman tool with your question now." (`postModelHook.py:39-43`, `_CORRECTIVE_MESSAGE`). `validatorRetryCount -> 1`.
- The `post_model_hook_router` inside `create_react_agent` loops back through `preModelHook` and re-invokes the LLM. The LLM is now told the policy-check text WAS a question, so it retries — most plausibly by re-emitting the same plain-text policy summary (which the user ultimately saw) or a near-duplicate, still with no tool call because it has already exhausted its "ask for justification" behavior and the prompt gives it no guidance on how to EXIT the justification loop.
- Second drift (`validatorRetryCount>=1`): `{validatorEscalate: True}` returned (`postModelHook.py:83-96`). Subgraph exits.
- Outer `postIntakeRouter` sees `validatorEscalate=True` → routes to `humanEscalationNode` (`node.py:416-428`).
- `humanEscalationNode` classifies trigger as `unsupportedScenario` (`humanEscalation.py:53`), writes DB status → "escalated" via `updateClaimStatus` (`humanEscalation.py:107-114`), emits terminal message "I couldn't complete this automatically. Your draft is saved. A reviewer will follow up." and sets `status="escalated"` on ClaimState.

This explains **every** observed symptom: the "Thought for 12s · 0 tools" re-emission, the verbatim policy re-echo, the ESCALATED status, and the absence of a proper terminal message replacement (the rewrite path replaces the AIMessage with the corrective rewrite, but the FIRST AIMessage is what the SSE layer already streamed to the UI → the user sees the original policy text; the rewrite happens inside the graph).

### H2 (secondary, high confidence): v5 prompt has no Phase-2-after-justification instruction.

`agentSystemPrompt_v5.py:165-169` (Section 4, Phase 2, step 5):
```
- Violation: call askHuman("A policy exception was flagged. Please provide a
  brief justification to proceed, or say 'cancel' to abandon the submission.").
  Do not advance until the user responds.
```

**There is no step 6 that says "when the user responds with a justification, record it in intakeFindings.justification and proceed to Phase 3 → submitClaim."** The prompt ends Phase 2 at the askHuman call. Phase 3 step 2 mentions a `justification` field in intakeFindings (line 180), but there is no explicit instruction linking "user replied to justification askHuman" → "proceed to submitClaim".

Even if H1 were fixed, this prompt gap alone would cause the LLM to stall or loop once the justification turn returns, because no instruction routes it forward. H1 guarantees immediate escalation; H2 guarantees ambiguity.

### H3 (secondary, medium confidence): `askHumanCount` threshold is unreachable before `validatorEscalate` fires, but CAN produce escalation on long conversations.

`postIntakeRouter` escalates when `askHumanCount > 3` (`node.py:430`). In this UAT the count after justification is 3 (manual rate, field confirmation, justification). Not yet > 3. So H3 is NOT the cause of this specific UAT — `validatorEscalate` fires first. Noted for completeness.

### H4 (ruled out): `submitClaimGuard` false-positive.

`submitClaimGuard._looksLikeSubmissionSuccess` matches phrases like "claim has been submitted", "successfully submitted", "claim number is", "submission complete". "Policy check: This exceeds…" contains none of these. Not the trigger.

## State-transition diagram

### What SHOULD happen

```
[Phase 2 violation detected]
  agent plain-text: "Policy check: ..."       ← informational summary
  agent tool_call:  askHuman("...justification...")
    └─ interrupt → user replies with justification
  ToolMessage(askHuman, justification_text)
  [Agent resumes]
    └─ records justification into intakeFindings.justification
    └─ tool_call: submitClaim(claimData, receiptData, intakeFindings)
  ToolMessage(submitClaim, {claim_number, id, ...})
  agent plain-text: "Claim {N} submitted successfully..."
  status = "submitted" → evaluatorGate → compliance+fraud → advisor
```

### What CURRENTLY happens

```
[Phase 2 violation detected — after unsupported-currency turn earlier]
  state: clarificationPending = True  (stale from convertCurrency turn, never cleared)
  agent plain-text: "Policy check: ..."
  agent tool_call:  askHuman("...justification...")
    └─ interrupt → user replies with justification
  ToolMessage(askHuman, justification)
    └─ postToolFlagSetter: askHumanCount += 1, clarificationPending unchanged (still True)
  [Inside subgraph, next model call]
    preModelHook injects: "ROUTING DIRECTIVE: A clarification is pending..."
    agent emits plain-text re-echo of policy check (no tool_calls)
    postModelHook trigger: hasContent ∧ ¬hasToolCalls ∧ clarificationPending = True
      → first drift: RemoveMessage + corrective SystemMessage; validatorRetryCount=1
    preModelHook re-injects same directive
    agent emits plain-text again (still no tool_calls — no guidance on how to proceed)
    postModelHook: second drift → validatorEscalate = True
  [Subgraph returns]
  postIntakeRouter: validatorEscalate=True → humanEscalationNode
  humanEscalationNode: DB status=escalated; ClaimState.status=escalated
  user sees original policy-check text (already streamed) + terminal escalation message
```

## File:line references for suspected bugs

| # | File | Line(s) | Bug description |
|---|------|---------|-----------------|
| B1 | `src/agentic_claims/agents/intake/hooks/postToolFlagSetter.py` | (missing; related 94-111, 145-153) | Never clears `clarificationPending`. Once set by unsupported-currency turn, it persists for the entire conversation lifetime, poisoning `postModelHook` drift detection on every subsequent plain-text AIMessage. |
| B2 | `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py` | 165-169 | Phase 2 violation branch tells the agent to call askHuman and "Do not advance until the user responds", but gives NO instruction for how to advance after the user DOES respond. Missing: "On justification received, set intakeFindings.justification and proceed to Phase 3 → submitClaim." |
| B3 | `src/agentic_claims/agents/intake/hooks/postModelHook.py` | 64-66 | Drift predicate is too loose. A plain-text summary sentence preceding a legitimate tool call on the SAME turn is indistinguishable from a plain-text question when the router splits the turn into two supersteps (model emits summary first, then tool call in next model pass). Combined with B1, guaranteed false positive. |
| B4 | `src/agentic_claims/agents/intake/hooks/postModelHook.py` | 39-43 | Corrective message assumes the plain-text content was a QUESTION ("You produced a user-facing question…"). If the plain-text was actually an informational summary (valid per prompt §5 "plain assistant messages are informational"), the correction misguides the LLM, making the second drift nearly certain. |
| B5 | `src/agentic_claims/agents/intake/nodes/humanEscalation.py` | 51-60 | `_classifyTrigger` falls through to `unsupportedScenario` whenever `validatorEscalate` is the cause. A false-positive validator escalation (from B1–B4) is not distinguishable from a genuinely unsupported scenario. No "soft" escalation category for policy-exception confusion. |
| B6 | `src/agentic_claims/core/state.py` | 41-67 | No `policyExceptionJustified` / `exceptionJustification` field. `intakeFindings.justification` exists only in the submitClaim payload schema (v5 prompt line 180), not as first-class ClaimState — so there is no state flag that `postModelHook`/`preModelHook` can gate on to know "justification already received, stop looping". |

## Recommended fix direction (concrete)

Ranked by impact-to-risk ratio.

### F1 (highest impact): Clear `clarificationPending` when the pending question is answered

Scope: `postToolFlagSetter.py`.

Add: when a `ToolMessage` for `askHuman` appears in the trailing run AND `state.clarificationPending` was True, include `clarificationPending: False` in the returned updates. The user's response IS the answer; the pending state is resolved.

Rough edit:
```python
if toolName == "askHuman":
    askHumanIncrement += 1
    # NEW: askHuman response resolves any pending clarification
    if state.get("clarificationPending"):
        clearClarification = True
    ...
if clearClarification:
    updates["clarificationPending"] = False
```

Rationale: the `askHuman` ToolMessage is definitionally a user answer. If the flag was set to force a clarification, the arrival of a tool-result from `askHuman` satisfies it. Do NOT clear it from `convertCurrency` retries or searchPolicies (only askHuman closes a clarification). This is the smallest change that breaks the loop.

### F2 (high impact): v5 prompt — add explicit post-justification instruction

Scope: `agentSystemPrompt_v5.py` Section 4 Phase 2.

Insert step 6:
```
6. When the user replies to the justification askHuman:
   - If the reply contains "cancel" (case-insensitive), do NOT submit. Call
     askHuman("Would you like to upload a different receipt or abandon
     this claim?").
   - Otherwise, treat the reply as the justification. Record it into
     intakeFindings.justification and proceed to Phase 3 → submitClaim.
     Do not loop back to the policy check.
```

### F3 (medium impact): First-class justification state + gate the drift predicate

Scope: `state.py`, `postToolFlagSetter.py`, `postModelHook.py`.

Add field `policyExceptionJustified: bool` to `ClaimState` and `IntakeSubgraphState`. `postToolFlagSetter` sets it True when the most recent `askHuman` ToolMessage (a) was preceded in the same turn by an AIMessage that called `searchPolicies` OR contained a violation phrase, AND (b) the user reply is not a cancel keyword.

Then tighten `postModelHook` drift predicate:
```python
isDrift = (
    hasContent
    and not hasToolCalls
    and clarificationPending
    and not state.get("policyExceptionJustified", False)
)
```

This provides defence-in-depth alongside F1.

### F4 (lower priority, but recommended for robustness): Distinguish policy-exception escalation from validator escalation

Scope: `humanEscalation.py` `_classifyTrigger`, and `postModelHook` escalation path. Emit a distinct `triggerClass="validatorDrift"` vs `policyExceptionTimeout`, so analytics can flag false-positives.

## Related behaviours / ripple risks

- **Low-confidence-field confirmation loop.** Section 5 error-recovery (`agentSystemPrompt_v5.py:209-213`) says "Low-confidence field, user confirmation needed" uses askHuman. That path does not set `clarificationPending` (postToolFlagSetter only triggers on unsupported-currency). So H1 does NOT affect low-confidence-field turns — UNLESS a currency was ever unsupported earlier in the same session, in which case the stale flag poisons every subsequent plain-text AIMessage. **Any multi-receipt session that once saw an unsupported currency is permanently in this poisoned state.**
- **Field-correction turns (Phase 1 step 9).** Same stale-flag hazard as above. The agent's "re-present the table" response is plain-text; if `clarificationPending` is stale True, the postModelHook will false-positive drift on it.
- **Multi-claim continuation (Phase 3 step 6 "Would you like to submit another receipt?").** After a successful submission, askHuman is called again. `clarificationPending` was never set (submitClaim doesn't set it) — but if ANY earlier unsupported-currency turn occurred in the thread, the stale flag applies to the new-receipt conversation too.
- **`askHumanCount` does not reset between claims.** Same conversation thread = accumulating count. A session with unsupported-currency + field-confirmation + justification + "submit another?" crosses the `> 3` threshold and triggers loop-bound escalation on the NEXT turn even if nothing is actually wrong. Recommend resetting `askHumanCount`, `clarificationPending`, `unsupportedCurrencies`, `validatorRetryCount`, `validatorEscalate` at the start of each new claim (e.g. when `claimSubmitted` becomes True, or when a new image upload begins).

## Confidence & gaps

- H1 is confirmed by code reading across all six files. I did not run the live graph or reproduce the exact LLM behavior on the corrective-retry step (I do not know whether the second model call truly re-emits the policy text or calls askHuman with a different phrasing). Both paths end in the same escalation, so the claim-ends-in-ESCALATED symptom is explained either way.
- H2 is confirmed by reading the v5 prompt end-to-end; no post-justification instruction exists.
- Not investigated: whether LangGraph 1.1.3's `post_model_hook_router` truly re-runs `preModelHook` before the corrective retry. The `postModelHook.py` docstring claims it does (L15-17) citing `chat_agent_executor.py L919-956`. If that claim is wrong, the corrective directive may not reach the retry call, but the escalation still fires on second drift. Worth confirming if F1 alone does not fix the bug.

## Next action (when fixing starts)

1. Implement F1 (smallest diff, highest impact). Write a failing test first: a unit test on `postToolFlagSetter` that seeds `state.clarificationPending=True` and a trailing `ToolMessage(name="askHuman", content=justification_text)`, asserts the return includes `clarificationPending: False`.
2. Implement F2 (prompt edit). Add integration test: simulate policy-violation → askHuman → user justification → assert next LLM call is `submitClaim` (not plain-text, not askHuman).
3. F3 and F4 as hardening once F1+F2 stabilize.
4. Also address the cross-claim stale-flag issue (reset flags on new receipt) — file a separate debug note.
