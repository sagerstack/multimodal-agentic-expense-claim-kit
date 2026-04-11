# Phase 11: Intake Multi-Turn Fix - Research

**Researched:** 2026-04-11
**Domain:** LangGraph interrupt/resume, SSE pipeline, observability, UX bug fixes
**Confidence:** HIGH

## Summary

This phase addresses a core behavioral issue: the intake agent currently runs all three phases (extraction, policy check, submission) in a single uninterrupted ReAct loop. The fix requires restoring the `askHuman` tool (deleted in commit `1e419fa`) to trigger LangGraph `interrupt()` calls between phases, plus resolving 6 additional issues ranging from logging standardization to currency UX bugs.

The SSE interrupt/resume pipeline is fully intact (`SseEvent.INTERRUPT`, `awaiting_clarification` session flag, `Command(resume=...)` in `sseHelpers.py:738-739`, interrupt detection at lines 1178-1193). The `askHuman` tool just needs to be recreated and added to the tools list. The system prompt's TURN ROUTING section must be rewritten to make the agent call `askHuman` between phases instead of proceeding automatically.

**Primary recommendation:** Recreate `askHuman` tool with `interrupt()`, update system prompt TURN ROUTING to enforce pauses, fix the 6 peripheral issues, and convert remaining raw `logger.info()` calls to `logEvent()`.

## Standard Stack

No new libraries needed. All work uses existing stack:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.1.3 | Graph orchestration, `interrupt()` | Already in use |
| langchain-core | 1.2.23 | `@tool` decorator, messages | Already in use |
| langgraph-checkpoint-postgres | 3.0.5 | State persistence across interrupts | Already in use |
| python-json-logger | (installed) | JSON structured logging | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FastAPI SSE | (built-in) | `ServerSentEvent` for interrupt events | Interrupt detection |

## Architecture Patterns

### Pattern 1: LangGraph `interrupt()` inside a Tool

**What:** The `askHuman` tool calls `interrupt(payload)` which suspends the ReAct agent mid-loop. The graph checkpoints state, `astream_events` terminates, and the SSE pipeline detects the interrupt in `finalState.tasks[0].interrupts`. On the next user message, `Command(resume=data)` resumes from the checkpoint.

**When to use:** Between each intake phase (extraction -> policy check -> submission).

**How it works end-to-end (verified from codebase):**

1. Agent calls `askHuman(question, data)` tool
2. Tool body calls `interrupt({"question": question, "data": data})`
3. LangGraph suspends, checkpoints state to Postgres
4. `astream_events` generator completes
5. `runGraph()` fetches `finalState = await graph.aget_state(config)` (line 1076)
6. Detects `finalState.next` is non-empty and `task.interrupts` exists (lines 1180-1183)
7. Extracts question from interrupt payload (line 1184-1188)
8. Sets `request.session["awaiting_clarification"] = True` (line 1189)
9. Yields `ServerSentEvent(raw_data=question, event=SseEvent.INTERRUPT)` (line 1190)
10. On next POST, `chat.py` builds `graphInput["isResume"] = True` (lines 128-140)
11. `sseHelpers.py` line 738-739: `invokeInput = Command(resume=graphInput["resumeData"])`
12. Graph resumes from checkpoint, `interrupt()` returns the resume data to the tool

**Original askHuman code (from git history):**
```python
@tool
def askHuman(question: str, data: dict) -> dict:
    """Ask the user a question and wait for their response."""
    response = interrupt({"question": question, "data": data})
    return response
```

**Key constraint:** `interrupt()` is imported from `langgraph.types`. In LangGraph 1.1.3, `interrupt()` works inside tools called by `create_react_agent`. No `interrupt_before`/`interrupt_after` graph-level config is needed.

### Pattern 2: System Prompt TURN ROUTING with Mandatory askHuman Calls

**What:** The current TURN ROUTING (lines 54-61 of `agentSystemPrompt_v2.py`) routes the agent through phases automatically. It must be rewritten to require `askHuman` calls between phases.

**Current behavior (broken):**
```
Phase 1 -> Agent presents extraction -> Agent immediately proceeds to Phase 2
Phase 2 -> Agent presents policy check -> Agent immediately proceeds to Phase 3
Phase 3 -> Agent submits claim
```

**Target behavior:**
```
Phase 1 -> Agent presents extraction -> Agent calls askHuman -> PAUSE
User confirms -> Phase 2 -> Agent presents policy check -> Agent calls askHuman -> PAUSE
User confirms -> Phase 3 -> Agent submits claim
```

**Key insight:** The TURN ROUTING must be rewritten so that each phase's final action is calling `askHuman` instead of ending with "End with: '...'" text. The routing conditions already check for tool results in conversation history, which will naturally work across interrupt/resume cycles since the checkpointer preserves all messages.

### Pattern 3: Decision Pathway State Across Interrupts

**What:** The Decision Pathway resets its state at the start of each `runGraph()` call, then seeds from `priorState` (lines 693-716). This already handles multi-turn correctly because it reads `extractedReceipt`, `searchPolicies` results, and `claimSubmitted` from the checkpointed state.

**Concern for Issue #3:** When a user uploads another receipt after submission, the pathway needs to reset. Currently, `pathwayCompletedTools` seeds from state -- if `claimSubmitted` is True from a prior receipt, all steps show as completed even for the new receipt. The `chat/reset` endpoint (line 236-267) clears session state including `draft_created`, but it does NOT clear the graph checkpoint.

### Anti-Patterns to Avoid

- **Using `interrupt_before`/`interrupt_after` on graph nodes:** Not needed. The tool-level `interrupt()` is simpler and already supported by the full SSE pipeline.
- **Breaking the ReAct agent into multiple separate graph nodes:** Would require rewriting the entire graph topology. The tool-level interrupt is the correct approach.
- **Modifying `sseHelpers.runGraph()` for interrupt detection:** The detection logic at lines 1178-1193 already works. No changes needed to the SSE pipeline core.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Inter-phase pause | Custom node splitting | `interrupt()` in `askHuman` tool | Full pipeline already exists, just re-add the tool |
| Interrupt detection | Custom SSE interrupt handler | Existing `finalState.tasks[0].interrupts` check | Lines 1178-1193 already handle this |
| State persistence across pauses | Custom state store | LangGraph AsyncPostgresSaver checkpoint | Already configured and working |
| Structured logging | Custom logger wrapper | Existing `logEvent()` from `core/logging.py` | Already handles redaction, Seq, structured fields |

## Common Pitfalls

### Pitfall 1: askHuman in TOOL_LABELS and TOOL_TO_STEP

**What goes wrong:** Adding `askHuman` to the tools list but forgetting to add it to `TOOL_LABELS` (sseHelpers.py line 38-44) causes "Running askHuman..." in the thinking panel. Also, `_calcProgressPct` (line 358-386) already has `askHuman` handling at line 380, so that's fine.
**How to avoid:** Add `"askHuman": "Waiting for your input..."` to TOOL_LABELS.

### Pitfall 2: System prompt tool count mismatch

**What goes wrong:** The system prompt says "You have 5 tools" (line 18). Adding `askHuman` makes it 6.
**How to avoid:** Update the count and add `askHuman` to the TOOLS section with its signature.

### Pitfall 3: Test assertion on tool count

**What goes wrong:** `test_intake_agent.py` line 40-41 asserts `len(tools) == 5`. Adding `askHuman` breaks this test.
**How to avoid:** Update assertion to `len(tools) == 6` and add `"askHuman"` to the expected tool names.

### Pitfall 4: Currency correction regex doesn't match bare currency codes

**What goes wrong:** Issue #5 says the agent doesn't recognize bare currency codes like "USD". Looking at `_currencyCorrectionMessage` (line 318-329), it only fires when `convertCurrency` returns an error. The issue is likely in the system prompt's currency check logic at lines 76-78 -- the agent sees an ambiguous currency and asks for confirmation, but when the user replies just "USD", the TURN ROUTING advances to Phase 2 instead of staying in Phase 1 to handle the correction.
**How to avoid:** The TURN ROUTING needs to handle the case where the user's reply is a currency code correction. This should trigger a re-call of `convertCurrency` with the corrected currency, not advance to Phase 2.

### Pitfall 5: Unsupported currency infinite retry loop

**What goes wrong:** Issue #6 describes VND (Vietnamese Dong) causing a 404 from Frankfurter API. The `convertCurrency` tool returns an error, `_currencyCorrectionMessage` fires, the user provides the same currency code, and the cycle repeats.
**How to avoid:** After the first currency error, the system should offer a manual exchange rate override option. This requires: (a) the system prompt to instruct the agent to offer manual rate entry after a failed conversion, and (b) the agent to calculate the SGD amount using the user-provided rate instead of calling `convertCurrency` again.

### Pitfall 6: on_chat_model_stream DEBUG noise

**What goes wrong:** Issue #0 mentions `on_chat_model_stream` noise. Looking at sseHelpers.py line 753, the line `logger.debug("astream_events event: %s - %s", eventKind, event.get("name", ""))` logs EVERY stream event at DEBUG level. When log level is DEBUG, this produces massive noise.
**How to avoid:** This is an app-owned logger (not a third-party one that can be suppressed via `setupLogging`). The fix is to either remove this debug line, change it to filter out `on_chat_model_stream` events, or gate it behind a specific flag.

### Pitfall 7: Decision Pathway doesn't reset on new receipt after submission

**What goes wrong:** Issue #3. After a claim is submitted, if the user uploads another receipt in the same session, the pathway shows all steps as completed because `priorState.values` has `claimSubmitted=True` from the previous submission.
**How to avoid:** When `hasImage=True` in `graphInput` AND `priorState.values.claimSubmitted=True`, reset the pathway state to show only "Receipt Uploaded" as completed. The graph state for the new receipt will be fresh because the ReAct agent starts a new iteration.

## Code Examples

### Recreating askHuman Tool

```python
# src/agentic_claims/agents/intake/tools/askHuman.py
from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def askHuman(question: str) -> dict:
    """Ask the user a question and wait for their response.

    Use this tool to pause and ask the user for confirmation or input.
    The response will contain the user's reply.

    Args:
        question: The question to ask the user

    Returns:
        Dict with the user's response
    """
    response = interrupt({"question": question})
    return response
```

### Updated Tool List in node.py

```python
from agentic_claims.agents.intake.tools.askHuman import askHuman

tools = [
    getClaimSchema,
    extractReceiptFields,
    searchPolicies,
    convertCurrency,
    submitClaim,
    askHuman,
]
```

### TURN ROUTING Update (System Prompt)

The key change is making the agent call `askHuman` at the end of Phase 1 and Phase 2 instead of just displaying text:

```
## TURN ROUTING

1. **No extractReceiptFields result** -> Phase 1 (extract, present, call askHuman)
2. **extractReceiptFields exists, no searchPolicies result** -> Phase 2 (policy check, call askHuman)
3. **searchPolicies exists, no submitClaim result** -> Phase 3 (submit)
4. **submitClaim exists** -> Present confirmation, offer new receipt
```

Phase 1 ending: Instead of "End with: Do the details look correct?", the agent should call `askHuman("Do the details above look correct?")`.

Phase 2 ending: Instead of "End with: Ready to submit?", the agent should call `askHuman("Ready to submit? Type 'yes' or 'confirm'.")`.

### Removing sendNotification from Advisor

```python
# In advisor/node.py, line 66:
# Change from:
tools=[searchPolicies, updateClaimStatus, sendNotification],
# To:
tools=[searchPolicies, updateClaimStatus],
```

Also update the advisor system prompt to remove references to `sendNotification`.

### Converting Raw Logger to logEvent

```python
# Before (raw logger):
logger.info("complianceNode started", extra={"claimId": claimId})

# After (structured logEvent):
logEvent(
    logger,
    "compliance.started",
    logCategory="agent",
    actorType="agent",
    agent="compliance",
    claimId=claimId,
    status="started",
    message="Compliance agent started",
)
```

### Removing Confirm/Edit Buttons from message_bubble.html

Lines 21-29 of `templates/partials/message_bubble.html` contain the "Yes, looks correct" and "Edit details" buttons, wrapped in `{% if confidenceScores %}`. These should be removed entirely since the multi-turn flow handles confirmation through the interrupt/resume cycle.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single ReAct loop (all 3 phases in one `ainvoke`) | Multi-turn with `interrupt()` between phases | This phase | Users can review and correct between phases |
| Raw `logger.info()` with `extra={}` | `logEvent()` with structured fields | Phase 7 (logging.py) | Seq filtering by logCategory, claimNumber, agent, toolName |
| `sendNotification` in advisor tools | Direct MCP call in advisor node | This phase (Issue #1) | Agent can't call it during intake |

## Issue-Specific Findings

### Issue #0: Observability Gap Analysis (from context)

Files needing `logEvent()` conversion:

| File | Current State | Lines Affected |
|------|---------------|----------------|
| `openrouter/client.py` | Zero logging (DEPRECATED file) | Add if still used |
| `compliance/node.py` | Raw `logger.info()/warning()` throughout | ~15 calls |
| `fraud/node.py` | Raw `logger.info()/warning()/error()` throughout | ~20 calls |
| `advisor/node.py` | Raw `logger.info()/warning()/error()` throughout | ~15 calls |
| `intake/node.py` | Raw `logger.info()` | ~4 calls |
| `sseHelpers.py` | Mixed (some `logEvent()`, some raw) | ~12 raw calls |
| `graph.py` | Raw `logger.info()` | ~3 calls |
| `chat.py:208-220` | Raw `logger.info()` | 1 call |

The `sseHelpers.py` DEBUG line at line 753 (`logger.debug("astream_events event: ...")`) is the source of `on_chat_model_stream` noise. Fix: suppress `on_chat_model_stream` events specifically, or remove the debug line.

### Issue #4: System Prompt Reveals Internal Details

Line 112 of `agentSystemPrompt_v2.py`:
```
"Do the details above look correct? If yes, I will continue using your authenticated session details."
```

This leaks the concept of "authenticated session details" to the user. Replace with neutral language:
```
"Do the details above look correct? If yes, I will proceed with the policy check."
```

### Issue #5: Bare Currency Code Recognition

The issue is in how the TURN ROUTING handles a user reply of just "USD" after Phase 1 asks about ambiguous currency. The routing currently says: "the user's reply after Phase 1 is their confirmation (unless they explicitly asked to change a field)". A bare currency code like "USD" doesn't match "explicitly asked to change a field" so the agent advances to Phase 2.

Fix: Add explicit instruction in the system prompt that a reply containing only a currency code (3 uppercase letters) should be treated as a currency correction, not confirmation.

### Issue #6: Unsupported Currency Stuck Loop

When Frankfurter returns 404 for an unsupported currency (e.g. VND), `_currencyCorrectionMessage` returns a generic "tell me the currency" message. The user re-sends the same currency, the tool fails again, and the loop repeats.

Fix approach:
1. In the system prompt, add instructions: "If `convertCurrency` fails twice for the same currency, offer the user the option to provide a manual exchange rate."
2. The agent can then calculate the SGD amount itself (amount * rate) and proceed without calling `convertCurrency` again.
3. No code change needed to `_currencyCorrectionMessage` -- the fix is in the system prompt and possibly a retry counter in the tool error handling.

## Open Questions

1. **Decision Pathway reset on new receipt (Issue #3):**
   - What we know: The pathway seeds from `priorState` which includes `claimSubmitted=True` from previous submission
   - What's unclear: Should the graph state be reset (new `thread_id`) or should the pathway logic detect "new receipt after submission" and reset its display?
   - Recommendation: Reset pathway display when `hasImage=True AND priorState.claimSubmitted=True`. The TURN ROUTING Phase 4 already says "reset to Phase 1 and await a new receipt upload" -- the pathway display just needs to match.

2. **openrouter/client.py logging (Issue #0):**
   - What we know: File is marked DEPRECATED, kept for backward compatibility
   - What's unclear: Is it still called by any code path?
   - Recommendation: Grep for usage. If unused, skip logging conversion. If used, add minimal logging.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: all files listed in context read directly
- LangGraph 1.1.3 installed, `interrupt()` API verified from existing usage in `langgraph.types`
- SSE pipeline code at `sseHelpers.py` lines 738-739, 1178-1193 verified

### Secondary (MEDIUM confidence)
- LangGraph `interrupt()` behavior inside `create_react_agent` tools: confirmed by existing test `test_summary_data.py:110-122` which references `askHuman` tool

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, all existing
- Architecture (interrupt/resume): HIGH - full pipeline verified in codebase, previously worked
- System prompt changes: HIGH - clear diff from current to target behavior
- Logging conversion: HIGH - `logEvent()` pattern well-established in codebase
- Currency UX fixes: MEDIUM - fix approach clear but needs testing with actual LLM behavior
- Pathway reset: MEDIUM - multiple valid approaches, needs design decision

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (stable -- no external dependency changes expected)
