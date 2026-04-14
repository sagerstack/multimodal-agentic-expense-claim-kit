# Phase 13: Intake Agent Hybrid Routing + Bug Fixes - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<authoritative_references>
## Required Reading — Authoritative References (DO NOT SKIP)

**Note to `gsd-phase-researcher` and `gsd-planner`:** Phase 13 is an **architectural-alignment** phase. The decisions below were derived directly from the sources listed here. These sources ARE the prescription. Your research answers _how to implement_ the prescription in this codebase with LangGraph 1.1.3 — not _whether_ to implement it or _what_ alternatives exist.

**Read these files first, before any Context7 / WebSearch / WebFetch call.** Every decision in this document carries citations to line numbers in these files. When your research recommendations contradict these sources, the sources win unless you can produce a stronger authoritative reference.

### Primary prescriptions (project-local, read in full)

| File | Role in Phase 13 |
|------|------------------|
| `docs/deep-research-langgraph-react-node.md` | LangGraph ReAct architecture, hook patterns, fallback hierarchy (L371–376), escalation rules, tool-invocation protocol, interrupts vs elicitation |
| `docs/deep-research-systemprompt-chat-agent.md` | System-prompt blueprint, instruction hierarchy (L57–65), defence-in-depth (L131–137), escalation and handoff rules (L526–536), recovery flowchart (L540–551) |
| `docs/deep-research-report.md` | System prompt blueprint, policy-variable prompts, instruction hierarchy, trust boundaries, escalation rules |
| `artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md` | Gap analysis of v4.1 prompt, Approach 3 (Hybrid, recommended), implementation context block with file paths, imports, sequencing, gotchas |

### Supporting references (read relevant sections)

| File | When to Consult |
|------|----------------|
| `artifacts/research/2026-04-03-react-agent-prompt-design-technical.md` | Earlier ReAct prompt-design research — useful for historical context on v3 / v4 decisions |
| `.planning/phases/11-intake-multi-turn-fix/11-RESEARCH.md` | Phase 11 resume-contract research — relevant to askHuman interrupt lifecycle; don't duplicate |
| `.planning/phases/11-intake-multi-turn-fix/*-PLAN.md` | Completed Phase 11 plans — the code this phase builds on |
| `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v4_1.py` | Current prompt (the "before" state) — Phase 13 produces a v5 replacement aligned with the sources above |

### Research scope for Phase 13 (what's still open)

Given CONTEXT.md and the references above, `gsd-phase-researcher` should focus investigation on the following gaps that the existing docs do NOT fully cover:

1. **LangGraph 1.1.3 hook API mechanics** — exact `pre_model_hook` / `post_tool_hook` signatures. Read the installed source (`.venv/lib/python3.11/site-packages/langgraph/prebuilt/chat_agent_executor.py` or poetry equivalent). Flagged as variant-across-versions in `technical.md` L238.
2. **Wrapper-graph pattern** — concrete skeleton for embedding `create_react_agent` as a subgraph inside an outer `StateGraph`. Our docs describe this abstractly; produce a working skeleton.
3. **Custom reducer for `unsupportedCurrencies: set[str]`** — confirm the LangGraph pattern for union-reducers on `TypedDict` fields, separate from `add_messages`.
4. **Message drop semantics** — does `add_messages` support `RemoveMessage`, or do we need a different channel for validator soft-rewrite? Check Context7 + installed source.
5. **Codebase file-by-file change map** — read current `agents/intake/node.py`, `core/graph.py`, `core/state.py`, intake tools, `web/sseHelpers.py`, `web/routers/chat.py`, `core/logging.py`. Produce a concrete list of files-to-create and files-to-modify.
6. **Reviewer queue contract** — how Phase 6.3 reviewer UI filters claims. Read `web/routers/reviewer.py` (or equivalent) to confirm `status = "escalated"` surfaces correctly.
7. **Checkpointer compatibility** — confirm `AsyncPostgresSaver` (lifespan singleton) works transparently with the wrapper-graph pattern. Check whether nested subgraphs need their own checkpointer config.
8. **Observability taxonomy** — read `core/logging.py` + existing `logEvent(...)` call sites across `web/`, `agents/`, `mcp_servers/`. Produce a Phase 13 event-name list consistent with existing conventions.

**Out of scope for research** (decisions locked in this CONTEXT.md — do not explore alternatives):

- Whether to use wrapper-graph vs full StateGraph rewrite (locked: wrapper)
- Whether to add a secondary currency provider (locked: no)
- Whether to cache currency rates (locked: no)
- Whether to send email on escalation (locked: no)
- Whether to bounds-check manual rates (locked: trust user)
- Whether to use LLM-as-judge validator (locked: state-flag predicate only)
- Whether to migrate to `create_agent` / newer LangGraph primitives (locked: stay on 1.1.3)

</authoritative_references>

<domain>
## Phase Boundary

Migrate the intake agent from v4.1 prompt-only routing to a hybrid architecture aligned with `docs/deep-research-langgraph-react-node.md`, `docs/deep-research-systemprompt-chat-agent.md`, and `docs/deep-research-report.md`:

- **Routing in code** — deterministic via state flags, hooks, and conditional edges.
- **Conversation in prompt** — the system prompt governs tone, content, and clarification phrasing; it no longer enforces control flow.

Closes 6 open intake-layer bugs (2, 3, 4, 5, 6, 7) as symptoms of the same misalignment. Does NOT touch: compliance/fraud/advisor agent layers (Phase 8.1), Phase 11 askHuman resume contract (already complete), Phase 6.3 reviewer UI.

Authoritative references consulted in discussion:
- `docs/deep-research-langgraph-react-node.md` (hook patterns, fallback hierarchy, escalation)
- `docs/deep-research-systemprompt-chat-agent.md` (defence-in-depth, instruction hierarchy, escalation rules)
- `artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md` (gap analysis, Approach 3 Hybrid)

</domain>

<decisions>
## Implementation Decisions

### Hook architecture — wiring pattern

- **Wrapper graph pattern.** Outer `StateGraph` with a `preIntakeValidator` node, the existing `create_react_agent` as a subgraph, and a `postIntakeRouter` node. `create_react_agent` keeps its convenience; deterministic routing logic lives in the outer graph nodes, not inside the prebuilt.
- Rationale: `deep-research-langgraph-react-node.md` L461 prefers newer primitives with middleware hooks; `technical.md` L238 warns `pre_model_hook` signature varies across LangGraph versions. The wrapper pattern avoids betting Phase 13 on native-hook stability and gives us a clean fallback (see below).
- If LangGraph native hooks prove insufficient or unstable on 1.1.3, the outer `StateGraph` already carries the validator/router logic — no architectural rework needed.

### Hook architecture — directive injection

- Synthetic `SystemMessage` directives (e.g., "currency VND unsupported — use manual-rate flow") are rebuilt **from state flags on every LLM invocation** via the pre-model hook (or the equivalent `preIntakeValidator` node in the wrapper graph).
- State flags are the source of truth; the `SystemMessage` is a derived view, rebuilt per call.
- Matches `technical.md` L154, L201–202.

### Hook architecture — message lifecycle

- **Ephemeral** — directive SystemMessages are scoped to one LLM invocation and never written to `state.messages`.
- State stays clean; no cleanup discipline needed; no risk of stale directives influencing later turns.
- Matches `systemprompt-chat-agent.md` L198 ("store minimal persistent information; prefer summarised checkpoints") and `langgraph-react-node.md` L99–101 (context-pollution warning).

### Hook architecture — fallback if native hooks fall short

- Already absorbed by the wrapper pattern. No separate fallback decision required.

### Escalation — destination

- **End-turn + save draft + reviewer queue.** On escalation the intake agent closes the turn, the claim is persisted with `status = "escalated"` and metadata, the reviewer picks it up via the existing Phase 6.3 queue.
- No email notification. Reviewer checks their queue.
- Claim stays in the system as a first-class record — never lost.

### Escalation — triggers (all four apply)

The `human_escalation` path fires when any one of these fires:

1. `askHumanCount` exceeds the per-slot threshold (treated as loop-bound safety net).
2. Critical tool failure — MCP DB unreachable, VLM permanent error, or other tool failure beyond repair capacity.
3. User explicitly asks for a human or uses a give-up phrase.
4. Unsupported scenario the agent cannot resolve — e.g., unsupported currency combined with user unable to provide a manual rate.

Matches `systemprompt-chat-agent.md` L526–536 and `technical.md` L185.

### Escalation — claim state shape

- `claims.status = "escalated"` + escalation metadata: `{reason, askHumanCount, unsupportedCurrencies, triggeredAt}`.
- Reviewer queue filters on `status = "escalated"`. Clean audit trail; explicit state machine transition.

### Escalation — user-facing message

- Terminal message: _"I couldn't complete this automatically. Your draft is saved. A reviewer will follow up."_
- No summary, no "anything to pass on" follow-up ask. Keep the terminal state simple and final.
- Template verbatim from `technical.md` L185.

### Currency fallback — chain shape

- **Two-tier chain:** Frankfurter → manual-rate `askHuman`. No secondary API provider.
- Unsupported currency (VND, THB, IDR, PHP, MYR, etc.) triggers an `askHuman` turn asking the user for the rate. User-provided rate is stored and used for conversion.

### Currency fallback — secondary provider

- **None.** No `open.er-api.com` or `exchangerate-api.com` integration. Manual rate via `askHuman` covers all currencies Frankfurter does not.
- Reduces new dependencies; simpler ops; accepts that SEA currencies require one extra user turn.

### Currency fallback — manual-rate verification

- **Trust the user-provided rate.** Store the receipt with `manualRate = true` flag and rate source = `"user"` on `receipts`. Reviewer can challenge the rate during approval.
- No sanity-range bounds check, no web-search cross-check.
- Aligns with `langgraph-react-node.md` L376: human-in-the-loop is the final authority.

### Currency fallback — caching

- **No caching.** Provider hit every call.
- Accepts the wasteful calls for now; revisit if volume grows.

### Currency tool contract (mandatory for the chain to work)

- `convertCurrency.py` **must** return a structured response on unsupported-currency 404: `{supported: false, currency: "VND", error: "unsupported"}`. Replaces today's raw error string.
- Required per `technical.md` L153 (Gap 3 fix). Without this, the post-tool hook has nothing reliable to match on.

### Post-model validator — strategy

- **Soft rewrite + re-invoke once, then escalate.**
- First drift: drop the offending plain-text `AIMessage`, inject a corrective `SystemMessage` ("You produced a user-facing question without calling askHuman. Retry with askHuman."), re-invoke the model.
- If second attempt also drifts: route to `human_escalation`.
- Matches `systemprompt-chat-agent.md` L117 (self-correction) → L526 (escalation on repeat failure).

### Post-model validator — trigger predicate

- Fires when **all three** are true: `AIMessage` has content + `AIMessage` has no `tool_calls` + a state flag indicates a clarification is pending (e.g., `unsupportedCurrencyPending`, `ambiguousFieldPending`, set by the post-tool hook).
- The state flag is authoritative — validator never fires on legitimate terminal responses (claim submitted, summary, final escalation message).
- Zero false positives by construction.

### Post-model validator — retry bound

- **1 retry**, then escalate. Tight bound.
- First drift is treated as a transient miss; second drift is treated as a systemic failure that needs a human.

### Post-model validator — telemetry

- Structured log event on every trigger: `logEvent("intake.validator.rewrite", {originalMessage, stateFlags, correctiveDirective, outcome: "rewrite_success" | "escalated"})`.
- Essential for measuring drift rate and tuning.

### Observability — end-to-end debuggability (first-class requirement)

Post-implementation debuggability is a non-negotiable Phase 13 requirement. Every moving part introduced or modified must emit structured events via the existing `logEvent()` infrastructure (`src/agentic_claims/core/logging.py`). This is a hard success criterion for Phase 13 — not a nice-to-have.

**What must be logged (per turn):**

1. **User prompts** — `chat.user_message_submitted` (already logged in `web/routers/chat.py`). Verify Phase 13 does not regress this.
2. **LLM invocations** — `intake.llm.request` + `intake.llm.response` on every call from the intake agent. Fields: model, message count, tokens in/out (if available), latency ms, turn index, claimId, threadId.
3. **Tool calls** — `intake.tool.invoke` on entry + `intake.tool.result` on exit for every tool (`extractReceiptFields`, `searchPolicies`, `convertCurrency`, `submitClaim`, `askHuman`, `getClaimSchema`). Fields: toolName, arguments (redacted per existing rules), result summary, duration ms, success/error class, structured-error class when applicable (`supported: false`, etc.).
4. **Routing decisions** — every conditional edge and hook decision emits an event:
   - `intake.hook.pre_model.directive_injected` with flag name + directive summary when a synthetic SystemMessage is built.
   - `intake.hook.post_tool.flag_set` with flag name + value when post-tool hook updates state.
   - `intake.validator.trigger` / `intake.validator.rewrite` / `intake.validator.escalate` per validator outcome.
   - `intake.router.decision` per outer-graph conditional edge with branch taken + reason.
5. **Turn lifecycle** — `intake.turn.start` / `intake.turn.end` bracketing each run of the intake subgraph. `intake.graph.node_entered` / `intake.graph.node_exited` for each node in the wrapper graph.
6. **State transitions** — `claim.status_changed` on any `status` write (existing pattern) with old/new value. Extend to `"escalated"` status.
7. **Escalation events** — `intake.escalation.triggered` with trigger class (loopBound | criticalToolFailure | userGiveUp | unsupportedScenario), metadata snapshot, and outbound reviewer-queue action.
8. **Manual rate flow** — `intake.currency.manual_rate_captured` with currency, rate, source = `"user"`.

**Correlation requirements:**

- Every event carries `claimId`, `threadId`, `turnIndex`, and `agent = "intake"` so a single claim's lifecycle can be reconstructed from logs alone.
- Turn index increments per intake subgraph invocation; allows reconstructing the ReAct loop ordering post-mortem.
- Validator retries share the parent `turnIndex` with a `retryIndex` sub-field.

**What must NOT change:**

- No reduction of existing log events anywhere in the intake pipeline (`chat.*`, `agent.turn_queued`, `agent.turn_stream_completed`, `claim.draft_created`, `claim.draft_failed`, `sse.*`). Phase 13 additions are strictly additive.
- Existing `logCategory` taxonomy (`chat_history`, `agent`, `chat`, `sse`) is preserved; Phase 13 uses `logCategory = "agent"` for intake-internal events and `logCategory = "routing"` for hook/validator/router events.

**Verification requirement:**

- Phase 13 verification must include a trace-reconstruction test: run a representative claim end-to-end (including one escalation path) and confirm the log stream can reconstruct: every user prompt, every LLM call, every tool call and its result, every routing decision, every state transition, in the correct order.

### Claude's Discretion

- Exact signatures of `preIntakeValidator` / `postIntakeRouter` functions.
- Precise state-flag naming (`unsupportedCurrencies: set[str]` vs `unsupportedCurrencyPending: bool`, etc.) — planner decides based on reducer strategy.
- Where to sequence the rate-multiplication math (tool vs service layer) for the manual-rate path.
- Folder structure for new hooks/nodes under `src/agentic_claims/agents/intake/`.
- Log-event schema details beyond the required keys above.
- Whether to version the prompt as `v5` or to do a clean break (file naming).

</decisions>

<specifics>
## Specific Ideas

- **Philosophy anchor:** "Routing lives in code, conversation in prompt." Every design choice in Phase 13 should be testable against this principle — if it routes by inspecting raw tool output strings in the prompt, it's wrong.
- **Belt-and-braces pattern** (from `technical.md` L154): state flag + pre-model directive + post-model validator. The layers compound, so individual layers can be less aggressive.
- **Defence-in-depth ordering** (from `technical.md` Recommendation L191–205): prompt fixes first → tool-contract hardening second → code guardrails third. Phase 13 does all three; order within the plan should respect this so each layer proves its value before the next.
- **Escalation message template is non-negotiable** — use the exact wording from `technical.md` L185. The research work already tested the phrasing.
- **Tool-contract change on `convertCurrency` is the keystone** — without the structured `{supported: false, ...}` response, every other layer degrades. Planner should treat this as Plan-01 or in the earliest wave.

</specifics>

<deferred>
## Deferred Ideas

- **Secondary currency provider** (open.er-api.com or exchangerate-api.com). Noted but skipped for Phase 13; revisit if manual-rate friction proves costly.
- **Currency rate caching** (in-memory or persisted to a `currency_rates` table). Skipped in Phase 13; revisit when volume grows.
- **Email notification on escalation** (via existing `mcp-email` server). Skipped in Phase 13; reviewer queue is the primary handoff.
- **Sanity-range bounds check on manual rates.** Skipped in Phase 13; reviewer catches bad rates during approval.
- **Comment-before-handoff** UX (one-shot askHuman before escalation closes the turn). Skipped — terminal message is simple and final.
- **LLM-as-judge validator** (call a second model to evaluate whether an AIMessage should have been askHuman). Skipped; state-flag predicate is simpler and deterministic.
- **Migration to `create_agent` / newer LangGraph middleware primitives** (per `langgraph-react-node.md` L461). Revisit when LangGraph 2.x API stabilises; Phase 13 stays on 1.1.3.
- **Full custom `StateGraph` rewrite** (Approach 2 from technical research). Not needed given the wrapper pattern; preserved as a future option.

</deferred>

---

*Phase: 13-intake-agent-hybrid-routing-and-bug-fixes*
*Context gathered: 2026-04-12*
