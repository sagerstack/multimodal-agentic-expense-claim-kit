# Phase 13: Intake Agent Hybrid Routing + Bug Fixes — Research

**Researched:** 2026-04-12
**Domain:** LangGraph 1.1.3, create_react_agent hook API, wrapper-graph pattern, state reducers, message rewrite, intake codebase change map
**Confidence:** HIGH (all findings verified against installed source or codebase)

---

## Summary

Phase 13 migrates the intake agent from prompt-only routing (v4.1) to the hybrid pattern: code enforces routing via state flags + hooks, prompt handles conversational nuance only. The 6 open bugs are architectural symptoms of prompt-only routing under pressure.

The installed LangGraph version is **1.1.3** (`langgraph` package), with `langchain-core` 1.2.23 and `langgraph-checkpoint-postgres` 3.0.5. The `create_react_agent` in 1.1.3 supports `pre_model_hook` and `post_model_hook` as first-class keyword arguments. Both are available in the installed source at `.venv/lib/python3.14/site-packages/langgraph/prebuilt/chat_agent_executor.py`. The CONTEXT.md decision to use a wrapper-graph pattern instead of native hooks remains sound — the installed source confirms `post_model_hook` with `version="v2"` creates a `post_model_hook_router` that controls loop continuation, but the routing logic within that hook is limited: the router checks for pending tool calls and either re-enters tools or exits. Complex conditional routing to a `human_escalation` node requires the wrapper-graph pattern, which is confirmed as the right approach.

`RemoveMessage` and `REMOVE_ALL_MESSAGES` are available in LangGraph 1.1.3 from `langgraph.graph.message` (confirmed by runtime test). The `pre_model_hook` supports `llm_input_messages` as an ephemeral channel — returning `{"llm_input_messages": [...]}` from the hook passes those messages to the LLM without writing them to `state["messages"]`, which is exactly the ephemeral-directive pattern required by CONTEXT.md.

**Primary recommendation:** Implement the wrapper-graph pattern exactly as described in CONTEXT.md. Wire `pre_model_hook` on the `create_react_agent` subgraph for ephemeral directive injection (via `llm_input_messages`). Place the validator and escalation router in outer-graph nodes. Use `RemoveMessage` for soft-rewrite in the `post_model_hook`. The reviewer queue already filters on `status = "escalated"` — no reviewer-side changes needed.

---

## 1. Hook API Mechanics (LangGraph 1.1.3)

**Source:** `.venv/lib/python3.14/site-packages/langgraph/prebuilt/chat_agent_executor.py` — verified by direct inspection.

### `create_react_agent` signature (installed 1.1.3)

```python
create_react_agent(
    model,
    tools,
    *,
    prompt: SystemMessage | str | Callable | Runnable | None = None,
    response_format = None,
    pre_model_hook: RunnableLike | None = None,       # NEW in v1.x
    post_model_hook: RunnableLike | None = None,      # NEW in v1.x, version="v2" only
    state_schema = None,
    context_schema = None,
    checkpointer = None,
    store = None,
    interrupt_before = None,
    interrupt_after = None,
    debug = False,
    version: Literal["v1", "v2"] = "v2",
    name = None,
)
```

Both hooks are confirmed present at the installed version. `version="v2"` is the default and is required for `post_model_hook` to function.

### `pre_model_hook` contract

- Called as a graph node named `"pre_model_hook"` before the `"agent"` (LLM-calling) node.
- Takes current graph state; returns a state update dict.
- **Critical:** MUST return at least one of `"messages"` or `"llm_input_messages"`.
- Returning `{"llm_input_messages": [...]}` passes those messages directly to the LLM WITHOUT writing to `state["messages"]`. This is the ephemeral-directive channel for injecting guardrail SystemMessages.
- Returning `{"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}` OVERWRITES `state["messages"]` permanently — use only for soft-rewrite, not directive injection.
- The state schema is extended dynamically when `pre_model_hook` is provided: a `CallModelInputSchema` subclass adds `llm_input_messages: list[AnyMessage]` to the existing schema (source L724–740).

```python
# Source: chat_agent_executor.py L400-410
# At least one of `messages` or `llm_input_messages` MUST be provided
{
    # If provided, will UPDATE the `messages` in the state
    "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), ...],
    # If provided, will be used as the input to the LLM,
    # and will NOT UPDATE `messages` in the state
    "llm_input_messages": [...],
    # Any other state keys that need to be propagated
    ...
}
```

**Async support:** If the hook is a coroutine function (`async def`), pass it directly. `_get_prompt_runnable` handles coroutine detection (L154–158).

### `post_model_hook` contract (version="v2")

- Called as a graph node named `"post_model_hook"` after every `"agent"` (LLM-calling) node invocation.
- Takes current graph state; returns a state update dict.
- After the hook runs, `post_model_hook_router` (source L919–956) determines next step:
  - If pending tool calls exist (no matching ToolMessage) → routes to `"tools"` via `Send`.
  - If last message is a `ToolMessage` → routes back to `entrypoint` (= `"pre_model_hook"` if hook exists).
  - Otherwise → routes to `END` or `"generate_structured_response"`.
- **Limitation for Phase 13:** This built-in router cannot route to an external `human_escalation` node (outside the subgraph). This is why the wrapper-graph pattern is needed for escalation routing.

```python
# post_model_hook minimal signature
async def myPostModelHook(state: AgentState) -> dict:
    messages = state["messages"]
    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    # inspect last_ai, update state flags
    return {"myFlag": True}  # partial state update; messages optional
```

### Summary: what hooks can do vs. what requires the wrapper graph

| Concern | Native hook can do it | Wrapper graph needed |
|---------|----------------------|---------------------|
| Inject ephemeral directive SystemMessage | YES (`llm_input_messages`) | No |
| Update state flags from tool results | YES (`post_model_hook`) | No |
| Soft-rewrite bad AIMessage + retry | YES (`post_model_hook` + `RemoveMessage`) | No |
| Route to external `human_escalation` node | NO | YES |
| Increment `askHumanCount` in outer state | NO (subgraph can't write outer state) | YES |

---

## 2. Wrapper-Graph Pattern — Working Skeleton

**Source:** CONTEXT.md decisions + `core/graph.py` (current topology) + chat_agent_executor.py (hook wiring).

The wrapper graph wraps `create_react_agent` as a subgraph node. The outer graph holds state fields that the subgraph cannot set. The `post_model_hook` on the subgraph handles soft-rewrite; the outer `postIntakeRouter` node handles escalation routing.

```python
# src/agentic_claims/agents/intake/node.py (Phase 13 skeleton)

from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages, RemoveMessage, REMOVE_ALL_MESSAGES
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, AIMessage, AnyMessage
from agentic_claims.core.state import ClaimState

# ── Inner subgraph: create_react_agent with hooks ──────────────────────────

async def preModelHook(state: dict) -> dict:
    """Inject ephemeral directive SystemMessages when state flags are set.

    Returns llm_input_messages (not messages) so directives are never
    persisted to state.messages. Source: chat_agent_executor.py L400-410.
    """
    base_messages = state.get("messages", [])
    directives = []

    unsupportedCurrencies: set = state.get("unsupportedCurrencies", set())
    if unsupportedCurrencies:
        currencies = ", ".join(sorted(unsupportedCurrencies))
        directives.append(SystemMessage(
            content=f"ROUTING DIRECTIVE: Currencies {currencies} are not supported by "
                    f"the automatic provider. Do NOT call convertCurrency for these currencies. "
                    f"Use the manual-rate askHuman flow immediately."
        ))

    clarificationPending: bool = state.get("clarificationPending", False)
    if clarificationPending:
        directives.append(SystemMessage(
            content="ROUTING DIRECTIVE: A clarification is pending. "
                    "You must call askHuman to surface the question to the user. "
                    "Do NOT emit a plain text question."
        ))

    if directives:
        # logEvent here for intake.hook.pre_model.directive_injected
        return {"llm_input_messages": directives + list(base_messages)}
    return {"llm_input_messages": list(base_messages)}


async def postModelHook(state: dict) -> dict:
    """Validate LLM output; soft-rewrite if clarification was emitted as plain text.

    Trigger: AIMessage has content + no tool_calls + clarificationPending flag is set.
    Action: RemoveMessage the bad AIMessage, inject corrective directive, signal retry.
    """
    messages = state.get("messages", [])
    clarificationPending = state.get("clarificationPending", False)
    validatorRetryCount = state.get("validatorRetryCount", 0)

    last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai is None:
        return {}

    isDrift = (
        bool(last_ai.content)
        and not last_ai.tool_calls
        and clarificationPending
    )

    if not isDrift:
        return {}

    if validatorRetryCount >= 1:
        # Second drift: signal escalation; outer postIntakeRouter will route
        # logEvent intake.validator.escalate
        return {"validatorEscalate": True}

    # First drift: soft-rewrite
    corrective = SystemMessage(
        content="CORRECTION: You produced a user-facing question without calling askHuman. "
                "Retry: call askHuman with your question now."
    )
    # logEvent intake.validator.rewrite
    return {
        "messages": [RemoveMessage(id=last_ai.id), corrective],
        "validatorRetryCount": validatorRetryCount + 1,
    }


def buildIntakeSubgraph(llm, tools) -> CompiledStateGraph:
    """Build the create_react_agent subgraph with pre/post hooks."""
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=INTAKE_AGENT_SYSTEM_PROMPT,  # v5 prompt
        state_schema=IntakeSubgraphState,   # see Section 3
        pre_model_hook=preModelHook,
        post_model_hook=postModelHook,
        version="v2",
        name="intakeSubgraph",
    )


# ── Outer wrapper graph ────────────────────────────────────────────────────

async def preIntakeValidator(state: ClaimState) -> dict:
    """Outer pre-node: increment askHumanCount from previous turn's interrupt.

    Reads the interrupt count from checkpointer state. This node fires once
    per outer-graph invocation (not per LLM call). Per-LLM-call directive
    injection lives in preModelHook (inner subgraph).
    """
    # Increment turnIndex for correlation
    return {"turnIndex": state.get("turnIndex", 0) + 1}


def postIntakeRouter(state: ClaimState) -> str:
    """Conditional edge: route to escalation or back to END after intake subgraph."""
    if state.get("validatorEscalate"):
        return "humanEscalation"
    if state.get("askHumanCount", 0) > 3:
        return "humanEscalation"
    if state.get("claimSubmitted"):
        return "submitted"  # existing evaluatorGate path
    return "pending"


async def humanEscalationNode(state: ClaimState) -> dict:
    """Terminal escalation node: set status=escalated, emit terminal message."""
    from langchain_core.messages import AIMessage
    from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool

    terminalMessage = AIMessage(
        content="I couldn't complete this automatically. Your draft is saved. "
                "A reviewer will follow up."
    )
    # Update DB status to escalated
    # logEvent intake.escalation.triggered

    return {
        "messages": [terminalMessage],
        "status": "escalated",
        "claimSubmitted": False,
    }


def buildOuterGraph(intakeSubgraph) -> StateGraph:
    """Outer StateGraph wrapping the intake subgraph."""
    builder = StateGraph(ClaimState)

    builder.add_node("preIntakeValidator", preIntakeValidator)
    builder.add_node("intakeSubgraph", intakeSubgraph)
    builder.add_node("humanEscalation", humanEscalationNode)

    builder.add_edge(START, "preIntakeValidator")
    builder.add_edge("preIntakeValidator", "intakeSubgraph")

    builder.add_conditional_edges(
        "intakeSubgraph",
        postIntakeRouter,
        {
            "humanEscalation": "humanEscalation",
            "submitted": END,   # evaluatorGate in the main graph handles rest
            "pending": END,
        }
    )
    builder.add_edge("humanEscalation", END)

    return builder
```

**Critical note on subgraph state schema:** `create_react_agent` enforces that `state_schema` has `messages` and `remaining_steps` keys (source L539–545). `ClaimState` lacks `remaining_steps`. The subgraph must use a separate `IntakeSubgraphState` that extends `ClaimState` or a slimmer schema. See Section 3.

---

## 3. State Shape and Reducers

### Current `ClaimState` (source: `src/agentic_claims/core/state.py`)

```python
class ClaimState(TypedDict):
    claimId: str
    status: str
    messages: Annotated[list[AnyMessage], add_messages]  # reducer: append
    extractedReceipt: Optional[dict]
    violations: Optional[list[dict]]
    currencyConversion: Optional[dict]
    claimSubmitted: Optional[bool]
    claimNumber: Optional[str]
    intakeFindings: Optional[dict]
    complianceFindings: Optional[dict]
    fraudFindings: Optional[dict]
    advisorDecision: Optional[str]
    dbClaimId: Optional[int]
```

### Phase 13 additions to `ClaimState`

| Field | Type | Reducer | Purpose |
|-------|------|---------|---------|
| `askHumanCount` | `int` | replace (last write wins) | Loop-bound counter; incremented by outer graph per interrupt |
| `unsupportedCurrencies` | `Annotated[set[str], union_reducer]` | union (additive) | Accumulates unsupported currency codes across turns |
| `clarificationPending` | `bool` | replace | True when a clarification is pending from a post-tool flag |
| `validatorRetryCount` | `int` | replace | Counts soft-rewrite attempts this turn; reset per turn |
| `validatorEscalate` | `bool` | replace | Signal from postModelHook to outer router |
| `turnIndex` | `int` | replace | Per-turn correlation counter for log events |

### Custom reducer for `unsupportedCurrencies: set[str]`

LangGraph supports custom reducers on `Annotated` TypedDict fields. The reducer function receives `(existing, update)` and returns the merged value.

```python
# src/agentic_claims/core/state.py — add to imports
from typing import Annotated, Optional, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

def _unionSet(existing: set | None, update: set | None) -> set:
    """Reducer: union two sets. Either arg may be None."""
    a = existing or set()
    b = update or set()
    return a | b

class ClaimState(TypedDict):
    # ... existing fields ...
    unsupportedCurrencies: Annotated[set[str], _unionSet]
    askHumanCount: int
    clarificationPending: bool
    validatorRetryCount: int
    validatorEscalate: bool
    turnIndex: int
```

**Confidence:** HIGH. This pattern is how `add_messages` itself works (`Annotated[list, add_messages]`). Any callable `(existing, update) -> merged` is valid. Verified against LangGraph docs pattern in `langgraph.graph.message`.

### `IntakeSubgraphState` (inner schema for create_react_agent)

`create_react_agent` enforces `remaining_steps` on the subgraph state (source L539). The inner state must include it:

```python
from langgraph.managed import RemainingSteps
from typing_extensions import NotRequired

class IntakeSubgraphState(TypedDict):
    """State schema for the create_react_agent inner loop."""
    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]
    # Phase 13 flag fields (read by hooks)
    unsupportedCurrencies: Annotated[set[str], _unionSet]
    clarificationPending: bool
    validatorRetryCount: int
    validatorEscalate: bool
```

The outer `ClaimState` and inner `IntakeSubgraphState` share fields by name. When the outer graph passes state into the subgraph node and the subgraph updates matching fields, those updates propagate back to outer state via the subgraph-node return merge. This is standard LangGraph subgraph wiring.

---

## 4. Message Rewrite Channel

**Source:** `chat_agent_executor.py` L400–410, confirmed by `langgraph.graph.message` runtime import.

### `RemoveMessage` and `REMOVE_ALL_MESSAGES` — confirmed available in 1.1.3

```python
from langgraph.graph.message import RemoveMessage, REMOVE_ALL_MESSAGES
# Both import successfully in installed 1.1.3 environment (verified at runtime)
```

### Soft-rewrite in `post_model_hook`

```python
# Remove the bad AIMessage by ID and inject a corrective SystemMessage:
return {
    "messages": [
        RemoveMessage(id=last_ai.id),          # removes one specific message
        corrective_system_message,             # adds corrective directive
    ],
    "validatorRetryCount": current_count + 1,
}
```

`add_messages` reducer handles `RemoveMessage`: when a `RemoveMessage(id=X)` is in the update list, it removes the message with that ID from `state["messages"]`. The corrective `SystemMessage` is then appended.

**Important:** `REMOVE_ALL_MESSAGES` (value `"__remove_all__"`) can be used as `RemoveMessage(id=REMOVE_ALL_MESSAGES)` to clear all messages. For soft-rewrite we want to remove only the bad AIMessage, so use `RemoveMessage(id=last_ai.id)`.

### Why not `llm_input_messages` for the rewrite?

`llm_input_messages` is ephemeral — it passes modified input to the LLM without touching `state["messages"]`. But soft-rewrite requires that the bad AIMessage is removed from state so it doesn't reappear on the next turn. Therefore `messages` (with `RemoveMessage`) is the correct channel for soft-rewrite, not `llm_input_messages`.

---

## 5. Files-to-Modify / Files-to-Create Map

### Files to CREATE

| File | Description |
|------|-------------|
| `src/agentic_claims/agents/intake/hooks/preModelHook.py` | Ephemeral directive injection via `llm_input_messages`. Reads `unsupportedCurrencies`, `clarificationPending` from state; builds directive SystemMessages; returns `{"llm_input_messages": ...}`. Emits `intake.hook.pre_model.directive_injected`. |
| `src/agentic_claims/agents/intake/hooks/postModelHook.py` | Validator: detects plain-text AIMessage when `clarificationPending` is set; soft-rewrites via `RemoveMessage` on first drift; sets `validatorEscalate=True` on second. Emits `intake.validator.trigger`, `intake.validator.rewrite`, `intake.validator.escalate`. |
| `src/agentic_claims/agents/intake/hooks/postToolHook.py` | (If implemented as named hook rather than inline in outer graph) Reads tool results from latest ToolMessages; sets `unsupportedCurrencies`, `clarificationPending`. Emits `intake.hook.post_tool.flag_set`. **Note:** In the wrapper-graph pattern, post-tool flag setting can live in `intakeNode`'s message-scan loop (current `node.py` L155–244) rather than a separate hook. Decision for planner. |
| `src/agentic_claims/agents/intake/nodes/humanEscalation.py` | Terminal escalation node. Sets `status="escalated"`, emits terminal message, calls `updateClaimStatus` MCP. Emits `intake.escalation.triggered`. |
| `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py` | Rewritten system prompt. Strips routing prose; adds: layered operating-manual structure, escalation awareness, resume semantics, strict tool contract section. Does NOT contain routing logic. File naming at planner's discretion (v5 vs clean break). |
| `tests/test_intake_hooks.py` | Tests for `preModelHook` (directive injection when flags set/unset), `postModelHook` (soft-rewrite on first drift, escalate on second, no-op on clean AIMessage). |

### Files to MODIFY

| File | Line-level change |
|------|------------------|
| `src/agentic_claims/core/state.py` | Add 6 new fields: `askHumanCount: int`, `unsupportedCurrencies: Annotated[set[str], _unionSet]`, `clarificationPending: bool`, `validatorRetryCount: int`, `validatorEscalate: bool`, `turnIndex: int`. Add `_unionSet` reducer function. |
| `src/agentic_claims/agents/intake/node.py` | Major rewrite: (1) add `buildIntakeSubgraph()` factory with hook args, (2) add `preIntakeValidator` node, (3) add `postIntakeRouter` conditional-edge function, (4) update `intakeNode` to invoke subgraph via outer wrapper, (5) update message-scan loop to set `unsupportedCurrencies` from structured `{supported: false}` responses, (6) update to increment `askHumanCount` on interrupt detection. Current L69–73 (create_react_agent call) expands significantly. |
| `src/agentic_claims/core/graph.py` | Add `humanEscalation` node to the main graph's topology. Wire: after `intake` (or the new outer wrapper), `postIntakeRouter` decides `human_escalation` vs `evaluatorGate`. The `humanEscalationNode` sets `status="escalated"` and routes to `END`. No change to compliance/fraud/advisor nodes. |
| `src/agentic_claims/agents/intake/tools/convertCurrency.py` | Catch MCP error responses and normalize to `{supported: false, currency: "VND", error: "unsupported"}` when the MCP server returns HTTP 404 or an error dict containing "404", "not found", "unsupported". Currently L30–39 passes raw MCP response through. Add parsing after `result = await mcpCallTool(...)`. |
| `mcp_servers/currency/server.py` | In `convertCurrency` (L58–63): change `except httpx.HTTPStatusError as e:` to detect 404 and return `{"error": "unsupported", "currency": fromCurrency, "supported": False}` instead of the current generic error string `f"Frankfurter API error: {e.response.status_code} ..."`. Also return `{"supported": True, ...}` on success for explicitness (optional but cleaner). |
| `src/agentic_claims/web/sseHelpers.py` | Remove PROBE A (L1395–1417) and PROBE D (L793–805) debug log blocks. These are `level=logging.WARNING` `logEvent` calls with `"debug.interrupt_check"` and `"debug.invoke_input_built"` events. Remove the blocks entirely; the interrupt-check logic below PROBE A (L1420–1435) stays. |
| `src/agentic_claims/web/routers/chat.py` | Bug 7 fix: `aget_state` is called twice for the same thread on message submission — once at L56 (auto-reset check) and once at L179 (resume detection). Consolidate: read state once, check both `claimSubmitted` (auto-reset) and interrupt status (resume detection) from the single snapshot. |
| `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v4_1.py` | No changes — this is the "before" state. The v5 prompt replaces it. |
| `tests/test_intake_agent.py` | Update `test_intakeAgentHasSixTools` if tool count changes. Add tests for new state fields, hook wiring, escalation path. |
| `tests/test_intake_tools.py` | Add test: `convertCurrency` 404 returns `{supported: false, currency: "VND", error: "unsupported"}` shape. Existing tests remain. |

### Files NOT touched (confirmed in scope)

- `src/agentic_claims/agents/compliance/node.py` — out of scope
- `src/agentic_claims/agents/fraud/node.py` — out of scope
- `src/agentic_claims/agents/advisor/node.py` — out of scope
- `src/agentic_claims/web/routers/review.py` — reviewer queue already handles `"escalated"` (see Section 6)
- Phase 11 files — `askHuman` tool, `interruptDetection.py` — stay unchanged

---

## 6. Reviewer Queue Contract

**Source:** `src/agentic_claims/web/routers/review.py` (verified), `src/agentic_claims/web/routers/manage.py` (verified).

### Current state

The reviewer queue already handles `"escalated"` as a valid status. No changes needed to the reviewer layer.

**`manage.py` L28:** `_VALID_STATUSES` includes `"escalated"`. Reviewers can filter to see only escalated claims.

**`review.py` L355 and L400:** `showActions = claim["status"] == "escalated"` — the "Approve / Reject" action buttons are shown when status is `"escalated"`. This is the correct behavior for intake-escalated claims: the reviewer takes action.

**`advisor/node.py` L241:** The advisor already writes `"status": "escalated"` to DB for its own escalation path. The intake escalation in Phase 13 must write the same value via the same `updateClaimStatus` MCP call pattern.

### What Phase 13 must write

When `humanEscalationNode` fires, it must:
1. Call `updateClaimStatus(claimId=dbClaimId, newStatus="escalated", actor="intake_agent")` via the DB MCP server.
2. Persist escalation metadata in `intakeFindings` (or a new `escalationMetadata` JSONB field on the claim): `{reason, askHumanCount, unsupportedCurrencies, triggeredAt}`.
3. Set `ClaimState.status = "escalated"`.

The reviewer will then see the claim in the manage list with status filter `"escalated"` and can open the review page for it.

### Confirmed: no schema changes needed for the reviewer layer

The reviewer queries claims by `status` column directly. `"escalated"` is already in the allowed status set. The Phase 13 escalation path just needs to write the right status value.

---

## 7. Checkpointer Compatibility

**Source:** `src/agentic_claims/core/graph.py` (current getCompiledGraph), `chat_agent_executor.py` (subgraph compilation).

### Current checkpointer setup

The main graph uses `AsyncPostgresSaver` with an `AsyncConnectionPool` (pool size 20). The pool is opened once at startup in `getCompiledGraph()` and passed to `builder.compile(checkpointer=checkpointer)` (source: `graph.py` L163–166).

### Wrapper-graph compatibility: CONFIRMED

When a subgraph is embedded as a node in an outer `StateGraph`, the **outer graph's checkpointer handles all state persistence**. The subgraph does NOT get its own checkpointer. The `create_react_agent` call for the inner subgraph should be compiled WITHOUT a checkpointer:

```python
intakeSubgraph = create_react_agent(
    model=llm,
    tools=tools,
    prompt=INTAKE_AGENT_SYSTEM_PROMPT,
    state_schema=IntakeSubgraphState,
    pre_model_hook=preModelHook,
    post_model_hook=postModelHook,
    version="v2",
    name="intakeSubgraph",
    checkpointer=None,   # CRITICAL: no checkpointer on inner subgraph
)
```

Then in the outer graph:
```python
builder.add_node("intakeSubgraph", intakeSubgraph)
# The outer graph compile call carries the checkpointer:
graph = builder.compile(checkpointer=checkpointer)
```

### `AsyncPostgresSaver` pool compatibility with subgraphs

The pool-based checkpointer (`AsyncPostgresSaver(pool)`) issues concurrent reads/writes across the pool. Nested subgraph execution in the same thread is sequential (not concurrent), so there is no pool contention issue. The setup in `getCompiledGraph()` does not need to change.

### Setup procedure: no change needed

The `setupSaver.setup()` call (L156–160) runs once to create LangGraph's checkpointer tables. The new nodes (`preIntakeValidator`, `humanEscalation`) are just nodes in the same graph — no additional table setup required.

---

## 8. Observability Event Taxonomy

**Source:** `src/agentic_claims/core/logging.py`, call-site grep across codebase.

### Existing events to preserve (verified call sites)

| Event | Location | Category |
|-------|----------|----------|
| `user.chat_message_submitted` | `web/routers/chat.py:95` | `chat_history` |
| `agent.turn_queued` | `web/routers/chat.py:228` | `agent` |
| `agent.turn_stream_completed` | `web/routers/chat.py:251` | `agent` |
| `claim.draft_created` | `web/routers/chat.py:138` | `chat_history` |
| `claim.draft_failed` | `web/routers/chat.py:155` | `chat_history` |
| `intake.started` | `agents/intake/node.py:97` | `agent` |
| `intake.agent_invoked` | `agents/intake/node.py:141` | `agent` |
| `intake.completed` | `agents/intake/node.py:251` | `agent` |
| `intake.llm_402_fallback` | `agents/intake/node.py:122` | `agent` |
| `tool.convertCurrency.started` | `tools/convertCurrency.py:28` | `tool` |
| `tool.convertCurrency.completed` | `tools/convertCurrency.py:38` | `tool` |
| `claim.submission_started` | `tools/submitClaim.py:110` | `agent` |
| `claim.submission_completed` | `tools/submitClaim.py:308` | `agent` |
| `claim.submission_failed` | `tools/submitClaim.py:290` | `agent` |
| `graph.evaluator_gate` | `core/graph.py:34` | `graph` |
| `sse.aget_state_timing` | `web/sseHelpers.py:717` | `sse` |
| `chat.resume_check_failed` | `web/routers/chat.py:185` | `chat` |
| `chat.auto_reset` | `web/routers/chat.py:74` | `chat_history` |

### Phase 13 new events (logCategory = "agent" for intake-internal, "routing" for hook/validator/router)

| Event | logCategory | Key fields | When |
|-------|-------------|-----------|------|
| `intake.turn.start` | `agent` | claimId, threadId, turnIndex | Per outer wrapper invocation |
| `intake.turn.end` | `agent` | claimId, threadId, turnIndex, elapsed | Per outer wrapper completion |
| `intake.hook.pre_model.directive_injected` | `routing` | claimId, threadId, turnIndex, flagName, directiveSummary | When preModelHook injects a directive |
| `intake.hook.post_tool.flag_set` | `routing` | claimId, threadId, flagName, flagValue, toolName | When post-tool sets a state flag |
| `intake.validator.trigger` | `routing` | claimId, threadId, turnIndex, validatorRetryCount | When postModelHook detects drift |
| `intake.validator.rewrite` | `routing` | claimId, threadId, turnIndex, retryIndex, correctiveDirective | When soft-rewrite fires |
| `intake.validator.escalate` | `routing` | claimId, threadId, turnIndex, reason | When second drift triggers escalation |
| `intake.router.decision` | `routing` | claimId, threadId, branch, reason | Per postIntakeRouter conditional edge |
| `intake.escalation.triggered` | `agent` | claimId, threadId, triggerClass, askHumanCount, unsupportedCurrencies | When humanEscalationNode fires |
| `intake.currency.manual_rate_captured` | `agent` | claimId, threadId, currency, rate, source="user" | When user provides manual FX rate |
| `claim.status_changed` | `agent` | claimId, dbClaimId, oldStatus, newStatus, actor | On any status write including "escalated" |

### Correlation requirements (from CONTEXT.md)

Every Phase 13 event must carry: `claimId`, `threadId`, `turnIndex`, `agent="intake"`.

Validator retry events add `retryIndex` sub-field alongside the parent `turnIndex`.

### Events to REMOVE (bugs 5)

- `debug.interrupt_check` at `web/sseHelpers.py:1396` — PROBE A, `level=WARNING`. Remove the entire try/except block (L1395–1417). The interrupt check logic below it (L1419–1435) stays.
- `debug.invoke_input_built` at `web/sseHelpers.py:794` — PROBE D, `level=WARNING`. Remove the entire `logEvent` block (L793–805).

---

## 9. Current v4.1 Prompt Dissection

**Source:** `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v4_1.py` (read in full).

### Structure

Total: ~260 lines. Sections:

| Section | Lines (approx) | Type | Phase 13 disposition |
|---------|----------------|------|---------------------|
| TOOL-CALLING DISCIPLINE | ~30 | Content + some routing | Keep as content, strip routing implications |
| TOOLS (6 descriptions) | ~20 | Content | Keep, simplify |
| ACTIVE-CLAIM GATE | ~15 | **Routing** | REMOVE — move to code (pre-hook flag) |
| CONVERSATION DISCIPLINE (Rules 1–4) | ~20 | Mix | Rules 2–3 = content; Rules 1, 4 = code |
| TURN ROUTING (table) | ~10 | **Routing** | REMOVE — move to code (state flags drive transitions) |
| WORKFLOW (Phase 1, 2, 3) | ~100 | Content | Keep as per-phase instructions; strip sub-routing |
| OUTPUT FORMAT | ~10 | Content | Keep |
| RULES | ~10 | Content + routing | Keep content rules; remove "re-run" enforcement (code handles) |
| ERROR HANDLING | ~15 | Mix | Keep content; remove routing logic (code handles) |
| ESCALATION | ~10 | **Routing + content** | Remove routing trigger; keep user-facing message template |

### What is routing (move to code) vs content (keep in prompt)

**Must move to code:**
- ACTIVE-CLAIM GATE (which phase to enter) — becomes outer `preIntakeValidator` + state flags
- TURN ROUTING table (phase transitions by history scan) — becomes state flags set by post-tool hook
- `convertCurrency` error → manual-rate branch instruction — becomes `clarificationPending` flag injected by pre-model hook
- "Stop looping" escalation triggers — become `askHumanCount > 3` conditional edge
- "Do not call convertCurrency again for this currency" — becomes `unsupportedCurrencies` flag + directive

**Must stay in prompt (v5 content):**
- Tool descriptions and when-to-call rules
- Phase 1/2/3 per-phase step instructions (what to do, not when to enter)
- User-facing message phrasing (confirmation text, policy-check text, escalation terminal message)
- Resume semantics paragraph ("When resumed from askHuman...")
- Confidence label mapping (High/Medium/Low thresholds)
- intakeFindings 6-key schema
- Output format rules

**v5 prompt should be structured as a layered operating manual** (per `systemprompt-chat-agent.md` L36–40): Role & tone → Authority & trust → Tool policy → Workflow phases (content-only, no routing logic) → Error recovery (content only) → Safety.

---

## 10. Test Patterns Inventory

**Source:** `tests/test_intake_agent.py` (read in full), `tests/test_intake_tools.py` (from CLAUDE.md inventory).

### Current patterns in `test_intake_agent.py`

- `patch("agentic_claims.agents.intake.node.create_react_agent")` — mock at the factory level
- `patch("agentic_claims.agents.intake.node.getIntakeAgent", return_value=mockAgent)` — mock the factory return for `intakeNode` tests
- `AsyncMock` for `agent.ainvoke` — returns pre-built message lists
- `MagicMock` for sync functions like `bufferStep`
- All async tests use `@pytest.mark.asyncio`
- State always typed as `ClaimState` dict literal

### New test targets for Phase 13

**`tests/test_intake_hooks.py` (new file)**

```python
# Pattern: test preModelHook in isolation

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agentic_claims.agents.intake.hooks.preModelHook import preModelHook

@pytest.mark.asyncio
async def test_preModelHookInjectsDirectiveWhenUnsupportedCurrencySet():
    state = {
        "messages": [HumanMessage(content="Process receipt")],
        "unsupportedCurrencies": {"VND"},
        "clarificationPending": False,
    }
    result = await preModelHook(state)
    assert "llm_input_messages" in result
    llm_msgs = result["llm_input_messages"]
    directive = next((m for m in llm_msgs if isinstance(m, SystemMessage)), None)
    assert directive is not None
    assert "VND" in directive.content
    assert "messages" not in result  # must NOT write to messages


@pytest.mark.asyncio
async def test_preModelHookNoDirectiveWhenNoFlags():
    state = {
        "messages": [HumanMessage(content="Process receipt")],
        "unsupportedCurrencies": set(),
        "clarificationPending": False,
    }
    result = await preModelHook(state)
    assert "llm_input_messages" in result
    # No SystemMessage directives
    directive = next((m for m in result["llm_input_messages"] if isinstance(m, SystemMessage)), None)
    assert directive is None
```

**`tests/test_post_model_hook.py` (in `test_intake_hooks.py`)**

```python
from langchain_core.messages import AIMessage, HumanMessage
from agentic_claims.agents.intake.hooks.postModelHook import postModelHook

@pytest.mark.asyncio
async def test_postModelHookSoftRewritesFirstDrift():
    bad_ai = AIMessage(content="What currency is this?", id="ai-1", tool_calls=[])
    state = {
        "messages": [HumanMessage(content="Submit"), bad_ai],
        "clarificationPending": True,
        "validatorRetryCount": 0,
        "validatorEscalate": False,
    }
    result = await postModelHook(state)
    assert "messages" in result
    assert any(hasattr(m, "id") and m.id == "ai-1" for m in result["messages"])
    assert result.get("validatorRetryCount") == 1
    assert not result.get("validatorEscalate")


@pytest.mark.asyncio
async def test_postModelHookEscalatesSecondDrift():
    state = {
        "messages": [AIMessage(content="What?", id="ai-2", tool_calls=[])],
        "clarificationPending": True,
        "validatorRetryCount": 1,
        "validatorEscalate": False,
    }
    result = await postModelHook(state)
    assert result.get("validatorEscalate") is True


@pytest.mark.asyncio
async def test_postModelHookNoOpOnCleanResponse():
    clean_ai = AIMessage(content="All done.", id="ai-3", tool_calls=[])
    state = {
        "messages": [clean_ai],
        "clarificationPending": False,
        "validatorRetryCount": 0,
    }
    result = await postModelHook(state)
    assert result == {}  # no changes
```

**`tests/test_intake_tools.py` — add**

```python
@pytest.mark.asyncio
async def test_convertCurrencyReturnsStructuredErrorOnUnsupportedCurrency():
    """convertCurrency wraps MCP 404 into {supported: false, currency, error}."""
    # Mock mcpCallTool to return Frankfurter-style error
    with patch("agentic_claims.agents.intake.tools.convertCurrency.mcpCallTool") as mockMcp:
        mockMcp.return_value = {"error": "Frankfurter API error: 404 ..."}
        result = await convertCurrency.ainvoke({"amount": 100, "fromCurrency": "VND", "toCurrency": "SGD"})
    assert result.get("supported") is False
    assert result.get("currency") == "VND"
    assert "error" in result
```

**`tests/test_state_reducers.py` (new or add to existing)**

```python
from agentic_claims.core.state import _unionSet

def test_unionSetMergesTwoSets():
    assert _unionSet({"VND"}, {"THB"}) == {"VND", "THB"}

def test_unionSetHandlesNone():
    assert _unionSet(None, {"VND"}) == {"VND"}
    assert _unionSet({"VND"}, None) == {"VND"}
    assert _unionSet(None, None) == set()
```

---

## 11. Risks / Unknowns

### Risk 1: Subgraph state field pass-through

When `create_react_agent` is compiled with a custom `state_schema` (e.g., `IntakeSubgraphState`) and embedded as a node in the outer `StateGraph` (which uses `ClaimState`), LangGraph's subgraph state merging passes only fields present in BOTH schemas back to the outer state. Fields like `unsupportedCurrencies` must be in both `ClaimState` and `IntakeSubgraphState` for the outer graph to receive updates from the inner graph. The planner must verify this with a smoke test before building the full hook logic.

**Mitigation:** Keep the Phase 13 state flags (`unsupportedCurrencies`, `clarificationPending`, `validatorRetryCount`, `validatorEscalate`) in both schemas. Alternatively, manage all flag updates in the outer graph's message-scan loop (existing pattern in `node.py` L155–244) instead of inside the subgraph hooks, bypassing the schema-merge concern entirely.

### Risk 2: `create_react_agent` deprecation warning in 1.1.3

The installed source marks `create_react_agent` as deprecated (L274–276: `@deprecated("... moved to langchain.agents ...")`). This emits a `UserWarning` at import time but does NOT change runtime behavior. CONTEXT.md locks the decision to stay on 1.1.3 and not migrate. The warning can be suppressed with `warnings.filterwarnings("ignore", ...)` if it pollutes logs.

### Risk 3: `post_model_hook` routing logic conflict

The built-in `post_model_hook_router` (source L919–956) re-routes based on pending tool calls. If the `postModelHook` sets `validatorEscalate=True` but the last AIMessage still has tool_calls (edge case: a drifted message that has both content and tool_calls), the router will send to `"tools"` anyway — overriding the escalation signal. The validator predicate (content + no tool_calls + pending flag) guards against this case, but the planner should add an explicit test to verify.

### Risk 4: `askHumanCount` increment timing

The `askHumanCount` needs to be incremented after each interrupt (each time `askHuman` fires). The current `askHuman` tool body calls `interrupt()` directly. There is no post-tool hook firing point for a tool that doesn't return (interrupt suspends execution). The count must be incremented in the outer graph's `preIntakeValidator` node on RESUME (when the graph is re-invoked after an interrupt). The planner needs to decide the increment site: `preIntakeValidator` on resume only, or `intakeNode` during message-scan when an `askHuman` ToolMessage is detected.

**Recommended:** Increment in `intakeNode`'s existing message-scan loop when an `askHuman` ToolMessage is found in the result, consistent with the current pattern for other tool results.

### Risk 5: v5 prompt regression

Removing routing logic from the prompt may cause regressions if the code guardrails don't fully cover all routing branches the prompt previously handled. CONTEXT.md prescribes ordering: prompt fixes first, then tool hardening, then code guardrails. The planner should schedule individual story-level tests before each wave.

### Risk 6: `IntakeSubgraphState` field isolation

If `create_react_agent`'s inner state schema includes `ClaimState` fields (e.g., `claimSubmitted`, `extractedReceipt`), the inner agent can overwrite them unexpectedly. The recommendation is to keep `IntakeSubgraphState` minimal: only `messages`, `remaining_steps`, and the Phase 13 flag fields. Claim-specific fields remain in outer `ClaimState` only.

---

## Sources

### Primary (HIGH confidence — verified against installed source or codebase)

- `.venv/lib/python3.14/site-packages/langgraph/prebuilt/chat_agent_executor.py` — `create_react_agent` signature, pre/post hook contracts, `post_model_hook_router` logic, `llm_input_messages` channel, `RemoveMessage` documentation
- `src/agentic_claims/agents/intake/node.py` — current `intakeNode`, `getIntakeAgent`, message-scan loop
- `src/agentic_claims/core/state.py` — current `ClaimState` fields
- `src/agentic_claims/core/graph.py` — current graph topology, `AsyncPostgresSaver` usage
- `src/agentic_claims/agents/intake/tools/convertCurrency.py` — current error passthrough (Bug 6 source)
- `mcp_servers/currency/server.py` — Frankfurter API error response shape
- `src/agentic_claims/web/sseHelpers.py` — PROBE A/D log locations (Bug 5), `aget_state` call
- `src/agentic_claims/web/routers/chat.py` — duplicate `aget_state` (Bug 7), existing events
- `src/agentic_claims/web/routers/review.py` — reviewer queue filter on `status="escalated"`
- `src/agentic_claims/web/routers/manage.py` — `_VALID_STATUSES` set confirming `"escalated"`
- `src/agentic_claims/core/logging.py` — `logEvent` signature, `logCategory` taxonomy
- `src/agentic_claims/web/interruptDetection.py` — `isPausedAtInterrupt` (unchanged)
- `tests/test_intake_agent.py` — current test patterns
- Runtime confirmation: `langgraph==1.1.3`, `langchain-core==1.2.23`, `langgraph-checkpoint-postgres==3.0.5`
- Runtime confirmation: `RemoveMessage` and `REMOVE_ALL_MESSAGES` importable from `langgraph.graph.message`

### Secondary (HIGH confidence — authoritative project docs)

- `.planning/phases/13-intake-agent-hybrid-routing-and-bug-fixes/13-CONTEXT.md` — all locked decisions
- `artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md` — gap analysis, Approach 3, implementation context (files list L222–234, gotchas L238)
- `docs/deep-research-langgraph-react-node.md` — hook patterns, fallback hierarchy
- `docs/deep-research-systemprompt-chat-agent.md` — prompt blueprint, instruction hierarchy

---

## Metadata

**Confidence breakdown:**
- Hook API mechanics: HIGH — read from installed source, runtime-confirmed
- Wrapper-graph skeleton: HIGH — derived from installed source + current graph.py
- State shape and reducers: HIGH — current state.py + `add_messages` pattern
- Message rewrite channel: HIGH — runtime-confirmed RemoveMessage import
- Files-to-modify map: HIGH — all files read directly
- Reviewer queue contract: HIGH — `review.py` and `manage.py` read directly
- Checkpointer compatibility: HIGH — current graph.py pattern confirmed
- Observability taxonomy: HIGH — all call sites grepped directly
- Prompt dissection: HIGH — v4.1 read in full

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (stable — LangGraph 1.1.3 pinned, no version changes expected)
