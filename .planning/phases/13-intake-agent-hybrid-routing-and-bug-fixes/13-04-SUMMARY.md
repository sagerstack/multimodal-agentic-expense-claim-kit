---
phase: 13
plan: 04
subsystem: intake-hooks
tags: [langgraph, hooks, preModelHook, postModelHook, escalation, validator]

dependency_graph:
  requires:
    - 13-02 (ClaimState with validatorRetryCount, validatorEscalate, clarificationPending, unsupportedCurrencies, askHumanCount, turnIndex)
  provides:
    - preModelHook: ephemeral directive injection via llm_input_messages channel
    - postModelHook: soft-rewrite validator with 1-retry bound and escalate signal
    - humanEscalationNode: terminal escalation node with DB status write
  affects:
    - 13-06 (wrapper graph wires these hooks into create_react_agent subgraph)
    - 13-07 (formal unit tests for all three modules)

tech_stack:
  added: []
  patterns:
    - llm_input_messages ephemeral channel for directive injection (LangGraph 1.1.3)
    - RemoveMessage soft-rewrite via langgraph.graph.message
    - settings.db_mcp_url convention for MCP calls (consistent with submitClaim.py, advisor/node.py)

key_files:
  created:
    - src/agentic_claims/agents/intake/hooks/__init__.py
    - src/agentic_claims/agents/intake/hooks/preModelHook.py
    - src/agentic_claims/agents/intake/hooks/postModelHook.py
    - src/agentic_claims/agents/intake/nodes/__init__.py
    - src/agentic_claims/agents/intake/nodes/humanEscalation.py
  modified: []

decisions:
  - "logEvent signature requires logging.Logger as first arg and logCategory= keyword (not category=). Plan template used wrong signature — corrected automatically."
  - "humanEscalation uses getSettings().db_mcp_url, not a hardcoded literal. All existing call sites (submitClaim.py, advisor/node.py, chat.py, graph.py) use settings.db_mcp_url — no hardcoded 'mcp-db:8000' strings exist anywhere in the codebase."
  - "preModelHook returns llm_input_messages with directives prepended before baseMessages (directives first so LLM sees them as latest system context before conversation history)."
  - "postModelHook trigger predicate: all three must be true (hasContent + no tool_calls + clarificationPending). Returns {} on any non-drift state — zero false positives by construction."

metrics:
  duration: "9 minutes"
  completed: "2026-04-12"
---

# Phase 13 Plan 04: Hooks and Escalation Summary

**One-liner:** Built preModelHook (ephemeral directive injection via llm_input_messages), postModelHook (soft-rewrite validator with 1-retry escalation), and humanEscalationNode (terminal node with DB status write via settings.db_mcp_url).

## What Was Built

### File Tree

```
src/agentic_claims/agents/intake/
├── hooks/
│   ├── __init__.py          (package marker, re-exports preModelHook + postModelHook)
│   ├── preModelHook.py      (77 lines)
│   └── postModelHook.py     (117 lines)
└── nodes/
    ├── __init__.py          (package marker)
    └── humanEscalation.py   (154 lines)
```

### Hook Contracts

#### preModelHook(state: dict) -> dict

**Input state keys read:**
- `messages` (list[AnyMessage]) — conversation history
- `unsupportedCurrencies` (set[str]) — from _unionSet reducer
- `clarificationPending` (bool) — pending user input flag
- `claimId`, `threadId`, `turnIndex` — correlation for log events

**Output:**
- Always returns `{"llm_input_messages": [...]}` — never `{"messages": ...}`
- When flags set: `{"llm_input_messages": [<directive SystemMessage(s)>, *baseMessages]}`
- When no flags: `{"llm_input_messages": [*baseMessages]}` (pass-through)

**Invariant:** Does NOT write to `state.messages`. Directives are ephemeral — scoped to one LLM invocation.

#### postModelHook(state: dict) -> dict

**Input state keys read:**
- `messages` — scans for last AIMessage
- `clarificationPending` (bool) — trigger gate
- `validatorRetryCount` (int) — retry bound gate

**Trigger predicate (all three must be true):**
1. Last AIMessage has non-empty content
2. Last AIMessage has no tool_calls
3. `clarificationPending` is True

**Output branches:**
| State | Return |
|---|---|
| No drift | `{}` (no-op) |
| First drift (retryCount == 0) | `{"messages": [RemoveMessage(bad_id), SystemMessage(corrective)], "validatorRetryCount": 1}` |
| Second drift (retryCount >= 1) | `{"validatorEscalate": True}` |

#### humanEscalationNode(state: dict) -> dict

**Input state keys read:**
- `claimId`, `threadId` — correlation
- `dbClaimId` — DB primary key for MCP update (may be None)
- `askHumanCount`, `validatorEscalate` — trigger classification
- `unsupportedCurrencies` — metadata snapshot
- `intakeFindings` — merged with escalationMetadata (preserved)
- `status` — old status for log event

**Output:**
```python
{
    "messages": [AIMessage(content="I couldn't complete this automatically. ...")],
    "status": "escalated",
    "claimSubmitted": False,
    "intakeFindings": {**existingFindings, "escalationMetadata": {...}},
    "validatorEscalate": False,  # cleared
}
```

**Escalation trigger classification:**
- `validatorEscalate=True` → `"unsupportedScenario"`
- `askHumanCount > 3` → `"loopBound"`
- Default → `"unsupportedScenario"` (criticalToolFailure / userGiveUp detected by Plan 05)

### MCP URL Convention — Verified Consistency

The plan's WARNING 4 mandated verifying that `humanEscalation.py` uses the same URL convention as `submitClaim.py`. Result:

```
grep -rn "mcp-db:8000" src/agentic_claims/
# No results — there are ZERO hardcoded URL literals in the codebase.

grep -rn "db_mcp_url" src/agentic_claims/
# src/agentic_claims/core/config.py: db_mcp_url field (settings source)
# src/agentic_claims/core/graph.py: settings.db_mcp_url
# src/agentic_claims/web/routers/chat.py: settings.db_mcp_url (x2)
# src/agentic_claims/agents/advisor/tools/updateClaimStatus.py: settings.db_mcp_url
# src/agentic_claims/agents/advisor/node.py: settings.db_mcp_url (x5)
# src/agentic_claims/agents/fraud/tools/queryClaimsHistory.py: settings.db_mcp_url (x3)
```

`humanEscalation.py` uses `getSettings().db_mcp_url` — byte-identical convention. No divergent literal introduced.

### Observability Events Emitted

| Event | Module | logCategory | When |
|---|---|---|---|
| `intake.hook.pre_model.directive_injected` | preModelHook | routing | Each flag that triggers a directive |
| `intake.validator.trigger` | postModelHook | routing | Drift detected |
| `intake.validator.rewrite` | postModelHook | routing | First drift soft-rewrite |
| `intake.validator.escalate` | postModelHook | routing | Second drift escalation signal |
| `intake.escalation.triggered` | humanEscalation | agent | Escalation node entered |
| `claim.status_changed` | humanEscalation | agent | DB status write successful |
| `intake.escalation.db_write_failed` | humanEscalation | agent | DB write failure (non-fatal) |

All events carry `claimId`, `threadId`, `agent="intake"` for correlation. Validator events also carry `turnIndex`, `validatorRetryCount`.

## Decisions Made

### logEvent Signature Correction (Rule 1 - Bug)

The plan template showed `logEvent("event.name", {...}, category="routing")` but the actual signature is `logEvent(logger, "event.name", *, logCategory=..., **fields)`. All three modules use the correct signature with a module-level `logger = logging.getLogger(__name__)`.

### MCP URL: settings.db_mcp_url (not hardcoded)

The plan mentioned a potential `_MCP_DB_URL = "http://mcp-db:8000/mcp"` fallback, but the codebase has zero hardcoded URL literals. The canonical pattern is `settings.db_mcp_url` throughout. `humanEscalation.py` uses `getSettings()` inline, same as `advisor/node.py`.

### No wiring yet

These modules are self-contained. Plan 13-06 wires them into the wrapper graph via `create_react_agent(pre_model_hook=preModelHook, ...)` and conditional edges.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] logEvent signature mismatch in plan template**

- **Found during:** Task 1 implementation
- **Issue:** Plan template showed `logEvent("event", {...}, category="routing")` but actual signature is `logEvent(logger, event, *, logCategory=..., **fields)`. STATE.md also documents this: "logEvent keyword is logCategory= (not category=)".
- **Fix:** Used correct signature with module-level logger and logCategory= keyword in all three modules.
- **Files modified:** preModelHook.py, postModelHook.py, humanEscalation.py
- **Commit:** All three task commits

**2. [Rule 1 - Bug] Plan suggested hardcoded `_MCP_DB_URL` constant**

- **Found during:** Task 3 implementation (WARNING 4 grep check)
- **Issue:** Plan template included `_MCP_DB_URL = "http://mcp-db:8000/mcp"`. Grep confirmed the codebase has zero hardcoded URL literals — all sites use `settings.db_mcp_url`.
- **Fix:** Used `getSettings().db_mcp_url` instead of any hardcoded literal. Updated the module docstring to document this convention with the grep evidence.
- **Files modified:** humanEscalation.py
- **Commit:** feat(13-04): create nodes package and humanEscalationNode terminal node

## Test Results

```
4 failed, 265 passed, 4 skipped
```

The 4 failures are pre-existing tracked bugs (test_e2e_intake_narrative, testBlurryImageReturnsError, testCurrencyToolErrorProducesCorrectionMessage, testActivePageIndicatorDashboard). Zero regressions introduced.

## Commits

| Hash | Type | Description |
|---|---|---|
| `575f2c2` | feat(13-04) | Create hooks package and preModelHook module |
| `05d3eac` | feat(13-04) | Create postModelHook with soft-rewrite and escalate |
| `5b9193c` | feat(13-04) | Create nodes package and humanEscalationNode terminal node |
