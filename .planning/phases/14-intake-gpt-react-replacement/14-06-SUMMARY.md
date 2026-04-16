---
phase: 14-intake-gpt-react-replacement
plan: "06"
subsystem: agent
tags: [intake-gpt, langgraph, state-machine, correction-loop, session-reset, tdd]

requires:
  - phase: 14-03
    provides: runtime bypasses (Gates 1-3), applyToolResultsNode field_confirmation branch, submit_confirmation flow
  - phase: 14-02
    provides: _classifyInterruptReply with negative/affirmative token detection, side_question guard

provides:
  - "field_confirmation No → correction loop: field_correction_requested → field_correction interrupt → correction_received → field_confirmation re-emission"
  - "submit_confirmation No → cancelled state + sessionReset flag + plain acknowledgement"
  - "chat.py session rotation on sessionReset (mirrors claimSubmitted QueueRotationSignal pattern)"
  - "InterruptResolution.correction_requested outcome + IntakeGptState.sessionReset: NotRequired[bool]"

affects: [14-07, chat-layer, sse-stream, session-management]

tech-stack:
  added: []
  patterns:
    - "Runtime Gate FC1/FC2 pattern: applyToolResultsNode sets transitional step, reasonNode detects and emits interrupt deterministically without LLM"
    - "sessionReset flag pattern: graph signals chat layer via state field rather than out-of-band mechanism"
    - "Narrowed classifier outcome: correction_requested replaces side_question for field_confirmation + negative token"

key-files:
  created: []
  modified:
    - src/agentic_claims/agents/intake_gpt/graph.py
    - src/agentic_claims/agents/intake_gpt/state.py
    - src/agentic_claims/web/routers/chat.py
    - tests/test_intake_gpt.py

key-decisions:
  - "correction_requested is a distinct outcome from side_question — negative token on field_confirmation is semantically different from a free-form interrogative"
  - "Field correction is text-only (no NLP parsing): correctionText stored verbatim in slots, appended to contextMessage on field_confirmation re-emission — full NLP correction parsing deferred as out-of-scope for Phase 14"
  - "sessionReset detected in postMessage preamble (priorState snapshot), not in SSE loop — mirrors existing claimSubmitted pattern exactly"
  - "workflow.status = 'cancelled' is a new terminal-like value for the cancel path (distinct from 'completed' and 'active')"

patterns-established:
  - "Gate FC1: currentStep == field_correction_requested + no pendingInterrupt → emit field_correction without LLM"
  - "Gate FC2: currentStep == correction_received + no pendingInterrupt → emit updated field_confirmation without LLM"
  - "Gate SC: currentStep == submission_declined + status == cancelled → emit plain text ack, advance to submission_cancelled_acknowledged"

duration: 25min
completed: 2026-04-14
---

# Phase 14 Plan 06: No-Path Recovery Flows Summary

**Correction loop + submit-cancel session reset: field_confirmation No opens a free-text correction question; submit_confirmation No cancels the claim and rotates the session via sessionReset flag.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-14T07:53:30Z
- **Completed:** 2026-04-14T08:18:30Z
- **Tasks:** 2 (RED + GREEN)
- **Files modified:** 4

## Accomplishments

- Narrowed `_classifyInterruptReply` to return `correction_requested` (not `side_question`) when field_confirmation receives a negative token — semantically correct distinction
- Implemented full correction loop state machine: `field_correction_requested` → Gate FC1 emits `field_correction` interrupt → `correction_received` → Gate FC2 re-emits `field_confirmation` with correction context appended
- Submit-confirmation No path now sets `workflow.status = "cancelled"` and `intakeState.sessionReset = True`; Gate SC emits plain acknowledgement inviting a new receipt upload
- `chat.py` session rotation on `sessionReset` fully wired — mirrors existing `claimSubmitted` QueueRotationSignal pattern exactly (new claimId/threadId, clearImage, queue rotation)
- 37/37 tests pass, zero regressions

## Correction-Loop State Machine

```
field_confirmation (buttons: Yes/No)
   │
   ├─ Yes → applyToolResultsNode: currentStep = field_confirmation_answered (Gate 1)
   │
   └─ No  → _classifyInterruptReply: correction_requested
           → applyToolResultsNode: pendingInterrupt=None, currentStep=field_correction_requested, status=active
           → reasonNode Gate FC1: emit requestHumanInput(kind=field_correction, "What looks incorrect?")
                                   pendingInterrupt set, currentStep=field_correction, status=blocked

field_correction (free text, no buttons)
   │
   └─ reply → applyToolResultsNode: slots.correctionText = responseText
                                    pendingInterrupt=None, currentStep=correction_received, status=active
            → reasonNode Gate FC2: emit requestHumanInput(kind=field_confirmation) with correctionText appended
                                    pendingInterrupt set, currentStep=field_confirmation, status=blocked

submit_confirmation (buttons: Yes/No)
   │
   ├─ Yes → submitClaim (unchanged)
   │
   └─ No  → _classifyInterruptReply: cancel_claim
           → applyToolResultsNode: pendingInterrupt=None, workflow.status=cancelled,
                                   currentStep=submission_declined, sessionReset=True
           → reasonNode Gate SC: AIMessage("Claim cancelled. Upload a new receipt to start a new claim.")
                                  currentStep=submission_cancelled_acknowledged, status=completed
           → chat.py (next POST): detects priorIntakeGpt.sessionReset=True → rotate session
```

## Task Commits

1. **RED tests** - `de29759` (test: 3 failing tests for No-path recovery flows)
2. **GREEN implementation** - `b7fc20b` (feat: field-correction loop + submit-cancel session reset)

## Files Created/Modified

- `src/agentic_claims/agents/intake_gpt/graph.py` — `_classifyInterruptReply` narrowed; `_buildFieldCorrectionAiMessage` + `_buildFieldConfirmationAfterCorrectionAiMessage` added; `applyToolResultsNode` correction_requested guard + field_correction kind handler + submit_confirmation cancel_claim update; `reasonNode` Gates FC1, FC2, SC added
- `src/agentic_claims/agents/intake_gpt/state.py` — `InterruptResolution.outcome` extended with `correction_requested`; `IntakeGptState.sessionReset: NotRequired[bool]` added
- `src/agentic_claims/web/routers/chat.py` — `sessionReset` session rotation handler added after `claimSubmitted` block
- `tests/test_intake_gpt.py` — 3 new TDD tests added (N1: field_confirmation No, N2: field_correction reply, N3: submit_confirmation No)

## Decisions Made

- **correction_requested vs side_question**: Plan 14-02 returned `side_question` for field_confirmation + "no". This plan narrows it to `correction_requested` — a semantically distinct outcome that drives the correction loop rather than the LLM side-question re-answering path.
- **Text-only correction (no NLP parsing)**: `correctionText` is stored verbatim in `slots["correctionText"]` and appended to `contextMessage` on field_confirmation re-emission. No NLP slot-patching is performed. This is sufficient for Phase 14 — the user visually confirms the updated extraction on the next field_confirmation. Full NLP correction parsing is explicitly out of scope.
- **workflow.status = "cancelled"**: A new status value for the cancel_claim path on submit_confirmation. Distinct from `"completed"` (normal terminal) and `"active"` (in-progress). Gate SC detects this combination to emit the acknowledgement.
- **chat.py sessionReset wiring**: COMPLETED (not deferred). The implementation mirrors the existing `claimSubmitted` rotation block exactly — same `clearImage`, `QueueRotationSignal`, `request.session` updates, `autoResetFired` flag.

## Deviations from Plan

None — plan executed exactly as specified. The plan's "best-effort" note for chat.py was not needed; the wiring was clean.

## Next Phase Readiness

- Plan 14-07 can proceed: correction loop state machine is fully wired, no blockers.
- The `field_correction` interrupt kind uses `uiKind = "text"` (confirmed by `_deriveUiKind` — text is the default for non-button kinds). The SSE dispatcher will render it as a free-text input, which is correct.
