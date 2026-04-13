---
status: diagnosed
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
source: [13-01-SUMMARY.md, 13-02-SUMMARY.md, 13-03-SUMMARY.md, 13-04-SUMMARY.md, 13-05-SUMMARY.md, 13-06-SUMMARY.md, 13-07-SUMMARY.md, 13-08-SUMMARY.md, 13-09-SUMMARY.md]
started: 2026-04-13T02:00:00Z
updated: 2026-04-13T08:15:00Z
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
issues: 2 (original) + 4 (post-fix live verification)
pending: 0
skipped: 0
notes: |
  Initial UAT: Test 6 passes functionally but display regression from Test 1 recurs. Gap 1 pervasive (Tests 1, 4, 6) and Gap 2 (policy-exception loop) blocks submission flow.

  Post-fix live verification (after executing 13-10, 13-11, 13-12): SSE routing fix (13-10) and DOM styling (13-11) partially hold BUT live stack exposed 4 DEEPER defects across Sessions 2 (post-auto-reset), 3 (VND loop), 4 (German askHuman exposure). See Gaps 3–6 below. Both executor agents (13-11, 13-12) stood down with commits preserved pending consolidated replan.

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

- truth: "After a claim is submitted and chat.auto_reset fires, the next user message on the new thread triggers the intake graph and receives an agent response"
  status: failed
  reason: |
    Live UAT trace (2026-04-13 23:56:12): auto_reset creates new threadId `6ee78a10-8a2a-4dce-ae8c-ce4672ae3164` and claimId `50bb44e7`. User sends "yes" 10ms later. Draft claim row created in DB (dbClaimId=29) BUT no `agent.turn_queued`, no `intake.started`, no SSE events on the new thread. User waits 52 seconds then manually resets at 23:57:04. Meanwhile background post-submission pipeline runs compliance/fraud/advisor on the OLD claim and completes at 23:56:21.
    Hypothesis: race condition between auto_reset + draft_claim insertion + background SSE task on the old thread prevents the new thread's `/chat/message` from queueing a graph turn. Likely wiring defect in `chat.py` or `sseHelpers.py` session queue handling.
  severity: major
  tests: [post-test-flow after Test 1 auto-reset]
  artifacts:
    - path: "docker compose logs app (23:56:12 — 23:57:04)"
      issue: "claim.draft_created fires at 23:56:12.174 on new thread 6ee78a10; no agent.turn_queued / intake.started follows; next user activity is manual chat.reset at 23:57:04"
  missing:
    - "Post-auto-reset new thread must accept and enqueue user messages the same way a cold-started thread does"
    - "Background post-submission SSE task on the old thread must not block the new thread's message intake"
    - "Either serialize the auto-reset + first-message sequence OR ensure the session queue flushes cleanly across thread_id rotation"
  root_cause: ""
  debug_session: ""

- truth: "Policy-exception / justification prompts are emitted as real askHuman tool_calls that fire LangGraph interrupts — not as plain AIMessage content — so clarificationPending state is correctly tracked"
  status: failed
  reason: |
    Live UAT trace (VND session, claim 8ff626a3): 5 policy-exception prompts emitted across 4 user replies, ZERO `askHuman` tool calls. All prompts ("Please provide a brief justification to proceed, or say 'cancel'") arrive as plain `AIMessage.content` with `tool_calls=[]`. Agent message #4 (00:00:17) and #5 (00:00:46) repeat the policy question verbatim after user provides justification. 13-12 F1 fix (clear clarificationPending when askHuman ToolMessage observed) is therefore vacuous on this failing path.
    Contrast: German session (d6ab0ed2) DID call askHuman once (for team-meal clarification), interrupt fired correctly (`taskCount=1, tasksWithInterrupts=[{name:intake, interruptCount:1}]`), resume worked, submission succeeded. LLM obedience to "use askHuman for questions" is INCONSISTENT — prompt-based enforcement alone is insufficient.
  severity: major
  tests: [live-UAT-VND-session]
  artifacts:
    - path: "docker compose logs app — VND session 23:57:18 to 00:01:34"
      issue: "3 of 5 assistant messages are plain-text policy questions with 0 tool_calls; askHuman tool invocation count=0 for the entire VND session"
  missing:
    - "Code-enforced askHuman: pre_model_hook or post_model_hook must detect question-in-plain-content pattern and either (a) rewrite into a tool_call, (b) set clarificationPending without waiting for a ToolMessage, or (c) use structured-output mode to block plain-text questions"
    - "Justification detection must happen independently of askHuman — e.g., a pre_model_hook that inspects last HumanMessage for justification-shaped content and injects a SystemMessage directive to advance to submit"
    - "postModelHook drift predicate needs re-evaluation: it should catch 'policy question as plain content' before it re-emits on the next turn"
  root_cause: ""
  debug_session: ""

- truth: "When the user types 'cancel' during a policy-exception prompt, the agent abandons the submission flow (does not call submitClaim) and acknowledges the cancellation"
  status: failed
  reason: |
    Live UAT trace (VND session 00:01:29 — 00:01:34): User typed "cancel" after 4 loop iterations. Agent's next response triggered `sse.hallucinated_submit_detected` — LLM claimed submission without calling submitClaim tool, guard caught and rewrote to canonical retry message. v5 prompt step 6 (Plan 13-12 F2 addition) did not cause the LLM to branch to the no-submit path.
    This is the SAME "prompt-level obedience is unreliable" root cause as Gap 4. Cancel keyword detection must be enforced code-side.
  severity: major
  tests: [live-UAT-VND-session cancel step]
  artifacts:
    - path: "docker compose logs app — 00:01:29 user msg, 00:01:34 hallucinated_submit_detected"
      issue: "User sends 'cancel'; agent ignores and attempts hallucinated submission; submitClaimGuard rewrites output"
  missing:
    - "Pre-submit code guard that inspects last HumanMessage for /^cancel|abandon|stop/i before permitting submitClaim"
    - "On cancel detection, either route to humanEscalation or reset the claim state (revert to pre-policy-check) with an acknowledgment message"
    - "Cancel must NOT route through the LLM at all — it should be a hard code branch in pre_model_hook or a conditional edge"
  root_cause: ""
  debug_session: ""

- truth: "Internal tool names (askHuman, extractReceiptFields, etc.) are not exposed to end users in the thinking/reasoning panel — display uses human-friendly labels or filters these events entirely"
  status: failed
  reason: |
    Live UAT trace (German session, 00:04:27 and 00:04:43): askHuman tool.start events appeared in the user-visible thinking panel as "Completed askHuman". User feedback: "askHuman is an internal thing, should not be exposed". This is a display-layer leak — the SSE `tool.start` / `tool.end` events include toolName verbatim, and the thinking-panel template renders the raw name.
    Separately, per 13-11 executor's salvage observation: the askHuman tool_call may be routed to the reasoning/thinking SSE channel instead of the `interrupt` channel, explaining why `#interruptTarget` cleanup hook (13-11) couldn't be exercised end-to-end — the pipeline isn't emitting `sse-swap="interrupt"` events during the interrupt flow.
  severity: minor (cosmetic) but blocks 13-11 cleanup verification
  tests: [live-UAT-German-session askHuman display]
  artifacts:
    - path: "docker compose logs app — 00:04:27 tool.start askHuman"
      issue: "tool.start event with toolName='askHuman' renders in thinking panel as 'Completed askHuman'"
    - path: "templates/partials/thinking_*.html (or equivalent)"
      issue: "Template renders raw toolName without user-friendly label mapping"
  missing:
    - "SSE helper should map internal tool names to user-friendly labels (askHuman → 'Asking for clarification', extractReceiptFields → 'Reading receipt', searchPolicies → 'Checking policy', convertCurrency → 'Converting currency', submitClaim → 'Submitting claim')"
    - "Alternative: filter askHuman tool events from the thinking panel entirely, and route to the #interruptTarget interrupt channel instead"
    - "Investigate whether askHuman output reaches `sse-swap=\"interrupt\"` at all — 13-11 cleanup hook presupposes it, but live run suggests content goes to reasoning channel"
  root_cause: ""
  debug_session: ""
