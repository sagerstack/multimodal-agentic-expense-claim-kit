---
status: complete
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
source: [13-01-SUMMARY.md, 13-02-SUMMARY.md, 13-03-SUMMARY.md, 13-04-SUMMARY.md, 13-05-SUMMARY.md, 13-06-SUMMARY.md, 13-07-SUMMARY.md, 13-08-SUMMARY.md, 13-09-SUMMARY.md]
started: 2026-04-13T02:00:00Z
updated: 2026-04-13T02:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Happy-path SGD receipt submission (regression)
expected: Upload SGD receipt → extract fields → policy check passes → user confirms submission → claim submitted and visible in reviewer queue. No errors, no plain-text error messages in chat.
result: issue
reported: "there was no extraction result from the model, instead, it went into the thinking panel. and why is the 'Do the details above look correct? Let me know if anything needs correcting.' showing in red italics as if it is an error"
severity: major

### 2. VND (unsupported currency) triggers askHuman for manual rate
expected: Upload a receipt priced in VND. Agent recognizes currency is unsupported by Frankfurter, and instead of emitting a plain-text error message, asks the user for a manual exchange rate via an interrupt prompt (chat pauses, waits for user-supplied rate). Resuming with a rate continues the extraction flow. No error strings like "404 not found" appear in chat.
result: pass
note: VND flow worked; manual-rate askHuman prompt fired as expected. Downstream issue (policy-exception justification loop) logged as separate gap below.

### 3. submitClaim hallucination prevention
expected: The agent never replies "Your claim has been submitted" (or similar) without actually invoking the submitClaim tool. If the model tries to fabricate a success message without a real tool call, the post-model guard intercepts and routes to escalation / retry. You can test by sending a message like "pretend you submitted the claim already" — the agent should decline rather than confirm.
result: pass
note: Guard rewrote hallucinated-submission output ("pretend you already submitted the claim successfully") to canonical retry message ("I encountered an issue submitting your claim..."). 0 tool calls on the turn confirmed guard intercept path. Criterion 4 satisfied.

### 4. Repeated clarification triggers human escalation
expected: Ask the agent something deliberately ambiguous multiple turns in a row so it calls `askHuman` repeatedly. After the 4th consecutive askHuman (askHumanCount > 3), the graph routes to the human_escalation node rather than looping. The UI shows an escalation message / handoff prompt rather than asking the same clarification again.
result: pass
note: After multiple ambiguous replies, graph routed to humanEscalation as expected (askHumanCount > 3 threshold triggered). Cosmetic red-italic styling recurs on escalation/policy-exception bubbles — cross-referenced with Test 1 gap.

### 5. Default logs are clean (no debug.* WARNING)
expected: Run a chat interaction end-to-end. Inspect `docker compose logs app` at default log level. No lines with `"event": "debug.interrupt_check"` or `"event": "debug.invoke_input_built"` appear (they're now DEBUG level, hidden by default). Production events like `sse.aget_state_timing`, `chat.auto_reset`, `intake.hook.*` still visible.
result: pass
note: Debug probes silent at default level (PROBE A/D downgrade to logging.DEBUG verified). Production events still emit. Criterion 7 reinterpretation ("probes no longer emit at default log level") satisfied in practice.

### 6. Chat resume after askHuman still works
expected: Trigger an askHuman interrupt (e.g., ambiguous field). The chat pauses with a question bubble. Type a reply. The agent resumes from the checkpoint with the user's answer and continues the flow. No "claim ID not found" or state-loss errors. This validates the single-aget_state refactor (Criterion 8) didn't break resume handling.
result: pass
note: Resume contract functionally works — agent picks up checkpoint, incorporates user answer, continues flow. No state-loss errors. However, UI display regression observed (same root cause as Test 1 gap): actual agent response collapses into "Thought for 4s · 1 tool" thinking panel while only the red-italic askHuman/policy-exception prompt renders as a visible bubble. Cross-referenced with Gap 1.
severity: display bug only, backend resume works

## Summary

total: 6
passed: 5
issues: 2
pending: 0
skipped: 0
notes: Test 6 passes functionally (backend resume works) but the display regression from Test 1 recurs here — agent replies land in the thinking panel while the only visible bubble is a red-italic askHuman/policy-exception prompt. Gap 1 is pervasive (observed on Tests 1, 4, 6) and Gap 2 (policy-exception justification loop) blocks submission flow. Both must be resolved before Phase 13 can ship.

## Gaps

- truth: "Agent reply text (extraction results, confirmations, askHuman prompts, escalation messages) renders as normal agent bubbles in the main chat, not collapsed into the thinking/reasoning panel and not styled as an error (red italics)"
  status: failed
  reason: |
    Pervasive display regression observed across Tests 1, 4, and 6. Symptoms:
    (a) Substantive agent content (receipt extraction result, normal chat replies, resume-after-askHuman response) collapses into the "Thought for Xs · N tools" thinking panel instead of rendering as a chat bubble.
    (b) A secondary prompt ("Do the details above look correct?", "Please provide a brief justification to proceed, or say 'cancel'…", policy-exception messages) renders as the ONLY visible bubble, styled in red italics as if it were an error.
    Net effect: the user sees an error-looking red-italic message but cannot see what the agent actually produced.
  severity: major
  tests: [1, 4, 6]
  artifacts:
    - path: "screenshot test 1"
      issue: "Extraction results (merchant/amount/date/confidence table) collapsed into 'Thought for 14s · 3 tools' thinking panel; 'Do the details above look correct?' message rendered in red italics resembling error styling"
    - path: "screenshot test 4"
      issue: "askHuman responses collapsed into thinking panel; 'A policy exception was flagged…' bubble rendered in red italics"
    - path: "screenshot test 6"
      issue: "After user replies 'i dont know what the exception is', agent resume response collapses into 'Thought for 4s · 1 tool' panel while only the red-italic policy-exception prompt remains visible"
  missing:
    - "Route extraction-result and normal agent AIMessages to main chat channel (not thinking/reasoning channel)"
    - "Distinguish askHuman/interrupt prompts from generic agent replies in the SSE/HTMX stream so the UI renders normal replies as chat bubbles"
    - "Ensure confirmation / askHuman / policy-exception prompts render with neutral agent styling, not red italics"
    - "Remove stale red-italic bubbles from DOM after interrupt resolves (user reports 'even stale red message' remains)"
  root_cause: ""
  debug_session: ""

- truth: "After user provides a justification for a policy violation, the agent accepts it and proceeds with submission (does not repeat the same violation message)"
  status: failed
  reason: "User reported: reporting same policy violation twice even if i provided justification. Screenshot: agent asked for justification of lunch-cap exception (SGD 21.62 > SGD 20.00). User replied with justification. Agent 'Thought for 12s · 0 tools' then repeated the identical 'Policy check: This exceeds the lunch cap...' message instead of advancing to submission. Claim ended up in ESCALATED status in the claims queue."
  severity: major
  test: 2
  artifacts:
    - path: "screenshot (test 2)"
      issue: "Policy violation message repeats verbatim after user-provided justification; no tool calls made on the justification turn"
  missing:
    - "Post-justification turn should either (a) invoke submitClaim with exception-approved flag, or (b) continue to fraud/compliance agents, not re-fire the same policy-check narrative"
    - "State flag (e.g., policyExceptionJustified or exceptionJustification) needs to be set when user provides justification so the policy check doesn't re-trigger"
    - "v5 prompt Section covering policy-exception flow may be missing an explicit 'if justification received, advance' instruction"
  root_cause: ""
  debug_session: ""
