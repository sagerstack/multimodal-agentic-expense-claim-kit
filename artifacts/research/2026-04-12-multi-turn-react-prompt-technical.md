# Technical Research: Multi-Turn ReAct Agent Prompt Design with LangGraph Interrupts

**Date:** 2026-04-12
**Context:** Debugging the intake agent in `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v3.py` — agent re-asks the same `askHuman` question on every user reply, never acknowledges off-topic user messages, and loops when `convertCurrency` fails with 404 for unsupported currencies (e.g., VND).

---

## Strategic Summary

Three patterns dominate 2025–2026 literature for multi-turn ReAct agents with interrupts: **(1) prompt-only routing** (what v3 does today), **(2) code-level state-machine routing** via LangGraph conditional edges, and **(3) hybrid: code enforces transitions, prompt handles conversational nuance**. Best practice converges on **hybrid**: prompt-only routing drifts under pressure (off-topic replies, tool failures), pure code-routing loses conversational flexibility. v3's current prompt is pattern (1) and exhibits the predicted drift.

---

## Requirements (inferred from codebase)

- ReAct agent via `langgraph.prebuilt.create_react_agent` (6 tools: `getClaimSchema`, `extractReceiptFields`, `searchPolicies`, `convertCurrency`, `submitClaim`, `askHuman`)
- `askHuman` uses `langgraph.types.interrupt()` inside the tool body
- `AsyncPostgresSaver` checkpointer persists state across interrupts
- Resume via `Command(resume={"response": message, "action": "confirm"})` from `chat.py:184`
- Must handle: user confirmations, corrections, off-topic replies, tool failures (Frankfurter 404 for unsupported currencies)

---

## Approach 1: Prompt-Only Turn Routing (current v3)

**How it works:** The entire routing logic lives in the system prompt under `TURN ROUTING`. The LLM inspects its own message history at the start of each turn and decides which phase to execute based on which tool results are present. No code-level gating.

**Libraries/tools:** `create_react_agent` + sophisticated prompt.

**Pros:**
- One place to iterate (the prompt)
- No graph topology changes needed
- Conversational flexibility — LLM can interpret nuanced user input
- Works fine for the golden path

**Cons:**
- **Drift under pressure.** The JB (Architecting Prompts) article and Microsoft Power Platform conversation-design guidance both flag this: "without intentional guardrails, behavior will drift in ways that may sound plausible but fail to meet user expectations." v3 drifts exactly this way when a tool consistently returns 404.
- **No loop bound.** LangGraph community explicitly warns: "Graphs with loops (like retry logic) will run forever if the exit condition is never met. Always pair a loop with a counter or a time limit in state." v3 has no such counter — the agent can re-call `askHuman` with the same question indefinitely.
- **Off-topic responses silently drop.** There is no instruction that says "address the user's message before routing" — so the LLM's acknowledgment reasoning stays in the thinking panel and never reaches the user.
- **Weaker models (gpt-4o-mini) struggle more** — the 10+ step routing logic assumes strong instruction-following.

**Best when:** Simple single-phase agents with no interrupts, or POC stage.

**Complexity:** S (to write), but L (to debug when it drifts).

---

## Approach 2: Code-Level State Machine with Conditional Edges

**How it works:** Replace `create_react_agent` with an explicit `StateGraph`. Each phase (extract, policy, submit) is its own node. Conditional edges route based on typed state fields, not LLM reasoning. `interrupt()` lives between nodes, not inside tools. The prompt only instructs the LLM about *what to do in the current phase* — not which phase to do.

**Libraries/tools:** `langgraph.graph.StateGraph`, `add_conditional_edges`, custom state (`phase: Literal["extract", "policy", "submit"]`, `retryCount: int`, `unsupportedCurrency: bool`).

**Pros:**
- **Deterministic routing.** State fields decide transitions, not LLM.
- **Loop bounds trivial to add** — `if state["retryCount"] > 2: goto fallback_node` in conditional edge.
- **No phase regression.** Once phase advances, it can't silently revert.
- **Debuggable** — state transitions show in checkpointer history.

**Cons:**
- **Rewrites significant intake code.** Lose `create_react_agent` convenience.
- **Less conversational.** Harder for the agent to handle novel user inputs that don't match the state machine.
- **More surface area for bugs** in the routing functions themselves.
- Community pattern is newer (Markaicode state-machine guide, ActiveWizards) — fewer battle-tested examples than ReAct.

**Best when:** Workflows with well-defined phases and strong transition rules (expense claims is a decent fit).

**Complexity:** L.

---

## Approach 3: Hybrid — Code Enforces Transitions, Prompt Handles Conversation

**How it works:** Keep `create_react_agent` as the intake node. Add a thin wrapper layer:

1. **Pre-LLM guard (node-level):** Before calling the LLM, inspect state/message history. If `convertCurrency` has returned 404 twice for the same currency, inject a synthetic `ToolMessage` into history saying `"CURRENCY_UNSUPPORTED: offer manual rate now"`. This pushes the LLM down the correct branch without relying on it to infer from a raw 404.
2. **Post-tool middleware:** After certain tools, check state and short-circuit. E.g., after `convertCurrency` returns 404, automatically flip `state["needsManualRate"] = True`.
3. **Prompt tightening:** Remove low-signal instructions; add three high-signal rules:
   - "Before any phase work, if the user's last message contains a question, off-topic input, or confusion, address it in one sentence at the start of your response, then proceed."
   - "If `askHuman` was your last tool call and the user's reply doesn't answer that question, acknowledge it and try a different approach — do NOT call `askHuman` with the same question."
   - "If state flag `CURRENCY_UNSUPPORTED` is set, immediately invoke the manual-rate flow. Do NOT call `convertCurrency` again for that currency."
4. **Loop bound in state:** `state["askHumanCount"] += 1` on each interrupt; conditional edge routes to a `human_escalation` node if count > 3.

**Libraries/tools:** Existing stack. Add a `preModelHook` or `postToolHook` (LangGraph supports both for `create_react_agent`).

**Pros:**
- **Minimal code churn** — keep intake node topology.
- **Deterministic guardrails** on the things that matter (loop bounds, tool-failure branches) while keeping LLM for conversation.
- **Matches LangGraph community consensus** (James Li "Advanced LangGraph", PremAI deep dive, Markaicode state-machine guide).
- **Resilient to weaker models** — guards catch drift that gpt-4o-mini would miss.

**Cons:**
- Two places to reason about (code + prompt) — need clear comment/doc saying "routing lives in code, conversation in prompt."
- Pre-model hooks add a little latency per turn.

**Best when:** Existing ReAct agent that mostly works but has specific failure modes — our exact situation.

**Complexity:** M.

---

## Comparison

| Aspect | Approach 1 (current v3) | Approach 2 (full state machine) | Approach 3 (hybrid) |
|--------|------------|------------|------------|
| Complexity to build | S | L | M |
| Complexity to debug | L | M | M |
| Loop prevention | None (prompt hope) | Deterministic | Deterministic |
| Off-topic handling | Accidental | Requires extra node | Prompt rule |
| Tool-failure branching | Prompt inference | Conditional edge | Post-tool hook |
| Conversational quality | Best | Weakest | Best |
| Weaker-model resilience | Poor | Strong | Strong |
| Matches 2026 best practice | No | Partially | Yes |

---

## Gap Analysis — v3 System Prompt vs. Best Practices

Mapped against findings from LangGraph docs, JB's "Architecting Prompts" framework, Microsoft Well-Architected conversation-design guidance, ElevenLabs prompting guide, and the LangChain forum resume-after-interrupt discussion.

### Gap 1: No "acknowledge user before routing" rule

**Best practice** (JB, Microsoft, ElevenLabs): "Design the flow to prompt the user with clarifying questions, offer alternative suggestions, or redirect the conversation in a way that keeps the user engaged." Explicit conditional instructions like "If the user is frustrated/off-topic, acknowledge their concerns before proceeding."

**v3 today:** TURN ROUTING jumps straight to phase detection. Off-topic user replies are reasoned about internally but never addressed in the final output (observed in screenshot 2: "Unable to provide the exact time now..." appears in thinking, never in response).

**Fix:** Add at top of TURN ROUTING:
> "Before phase routing: if the user's most recent message contains a direct question, off-topic input, or confusion, address it in one short sentence at the START of your final response, then continue with phase work."

---

### Gap 2: No loop bound on `askHuman`

**Best practice** (LangGraph community, Markaicode state-machine guide): "Always pair a loop with a counter or a time limit in state."

**v3 today:** Agent can re-invoke `askHuman` with the same question every turn indefinitely. No code-level bound either.

**Fix (Approach 3):**
- Add `askHumanCount: int` to `ClaimState`
- Pre-model hook increments on each interrupt
- Prompt rule: "Do not call `askHuman` with the same question twice in a row. If the user's previous reply didn't resolve the issue, acknowledge it and try a different approach."
- Code-level escape hatch: after 3 interrupts, conditional edge routes to `human_escalation` node that ends gracefully.

---

### Gap 3: Tool-failure routing relies on LLM inference

**Best practice** (LangChain HITL docs, James Li "Advanced LangGraph"): Use conditional edges and typed state for deterministic routing based on tool outcomes, not LLM inspection of raw errors.

**v3 today:** Step 3(d) in Phase 1 tells the LLM to detect "convertCurrency returns an error for an unsupported currency" and offer manual rate. But the Frankfurter 404 error is a raw string, and the LLM (especially gpt-4o-mini) consistently misroutes back to 3(c) ("ambiguous currency") instead of 3(d) ("unsupported currency").

**Fix:**
- **Tool-side:** Modify `src/agentic_claims/agents/intake/tools/convertCurrency.py` to catch 404 and return structured `{supported: false, currency: "VND", error: "unsupported"}` instead of a raw error string. Easier for the LLM to match on.
- **State-side (belt & braces):** Post-tool hook sets `state["unsupportedCurrencies"].add("VND")`. Pre-model hook injects a synthetic system message if the set is non-empty: "Currency VND is unsupported — use manual rate flow, do not retry `convertCurrency`."

---

### Gap 4: No explicit "what happens on resume" guidance

**Best practice** (LangChain forum, blog.langchain.com HITL post): The resumed node re-executes code before the interrupt. Prompts should account for this — e.g., include instructions like "When resumed, the last tool result in your history is `askHuman`'s return value — that is the user's latest reply."

**v3 today:** No mention of resume semantics. The LLM has to infer from tool history what just happened.

**Fix:** Add a brief section:
> "When resuming from `askHuman`: your message history will show `askHuman` returned `{response: "..."}`. That response IS the user's latest reply — treat it as the user's message for the current turn."

---

### Gap 5: TURN ROUTING is 10+ branches deep; weaker models can't follow reliably

**Best practice** (ElevenLabs prompting guide, MindStudio): "Define core personality, goals, guardrails firmly while allowing flexibility in tone and verbosity." Prefer small number of high-signal rules over large number of conditional branches.

**v3 today:** TURN ROUTING has 4 numbered clauses, each with sub-branches and exceptions. This is the failure mode described by JB's "prompts as fragments rather than complete arcs."

**Fix:** Compress TURN ROUTING to 3–4 rules keyed off explicit state flags, not on tool-history inspection. Move phase-specific mechanics into Phase 1/2/3 sections (already there) and let the routing section just decide *which* phase.

---

### Gap 6: No fallback topic / escalation

**Best practice** (Microsoft Power Platform conversation design, Rasa multi-turn guide): Configure a fallback topic the agent uses when it can't handle the input. Avoid "repeating the same line or looping the user through the same step."

**v3 today:** No fallback. Stuck agent → infinite askHuman.

**Fix:** Add a `human_escalation` node (Approach 3) that triggers on any of: (a) `askHumanCount > 3`, (b) critical tool failure, (c) user typing phrases like "give up" / "talk to a human". Response: "I can't resolve this automatically. Your claim is saved as a draft. A human reviewer will follow up."

---

## Recommendation

**Approach 3 (hybrid)** with the 6 gap fixes above. Specifically:

1. **This week — prompt-only fixes** (low risk, high signal):
   - Add "acknowledge user first" rule
   - Add "don't re-ask same question" rule
   - Add resume-semantics paragraph
   - Compress TURN ROUTING to 3–4 state-keyed rules
2. **Next — tool hardening:**
   - Structured 404 return from `convertCurrency.py`
3. **Then — code guardrails:**
   - `askHumanCount` in state + post-tool hook
   - Pre-model hook injects "currency unsupported" synthetic message when flag set
   - `human_escalation` node with conditional edge at count > 3

Ordered this way, each step is independently validatable and reversible.

**Model question (orthogonal):** Strongly consider switching `OPENROUTER_MODEL_LLM` back to Qwen3-235B (the committed `.env.example` default) or trying `claude-sonnet-4-5`. gpt-4o-mini's instruction-following weakness is compounding the prompt-design issues — a stronger model may make Gap 5 less acute.

---

## Implementation Context

<claude_context>
<chosen_approach>
- name: Hybrid — prompt fixes first, then tool hardening, then code guardrails
- libraries: existing stack (LangGraph 1.1.3, langchain-core 1.2.23, langgraph-checkpoint-postgres 3.0.5)
- install: no new dependencies
</chosen_approach>
<architecture>
- pattern: ReAct agent (create_react_agent) with pre_model_hook + post_tool_hook for deterministic guardrails
- components: (1) updated agentSystemPrompt_v4.py, (2) structured-error convertCurrency.py, (3) ClaimState fields for askHumanCount + unsupportedCurrencies, (4) preModelHook function, (5) postToolHook function, (6) human_escalation node
- data_flow: user msg → preModelHook (inject guardrail messages if flags set) → LLM → tool → postToolHook (update state flags) → repeat or interrupt
</architecture>
<files>
- create: src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v4.py (compressed TURN ROUTING)
- create: src/agentic_claims/agents/intake/hooks/preModelHook.py (inject guardrail messages)
- create: src/agentic_claims/agents/intake/hooks/postToolHook.py (update state flags)
- create: src/agentic_claims/agents/intake/nodes/humanEscalation.py (fallback node)
- modify: src/agentic_claims/agents/intake/tools/convertCurrency.py (structured 404 return)
- modify: src/agentic_claims/core/state.py (add askHumanCount, unsupportedCurrencies)
- modify: src/agentic_claims/agents/intake/node.py (wire hooks into create_react_agent)
- modify: src/agentic_claims/core/graph.py (add human_escalation node + conditional edge)
- reference: .planning/phases/11-intake-multi-turn-fix/11-RESEARCH.md for interrupt wiring context
</files>
<implementation>
- start_with: write v4 prompt with 6 gap fixes, A/B it against v3 on the VND test case before touching code
- order: (1) v4 prompt, (2) structured convertCurrency 404 return, (3) state fields + hooks, (4) human_escalation node
- gotchas: (a) pre_model_hook signature varies between LangGraph versions — check 1.1.3 API; (b) interrupt() re-runs the tool from its start on resume — don't put non-idempotent side effects before interrupt call; (c) Frankfurter supports ~30 currencies only — test with VND, THB, IDR to exercise the unsupported branch
- testing: extend tests/test_intake_tools.py with 404 case; add tests/test_intake_hooks.py; add multi-turn test in tests/test_intake_agent.py simulating askHuman loop prevention
</implementation>
</claude_context>

**Next Action:** Draft v4 prompt with the 6 gap fixes and test it against the VND failure case before implementing code guardrails. Validate that a prompt-only fix gets us 80% of the way — only add code hooks if the prompt fix still misroutes.

---

## Sources

- [LangGraph Interrupts — official docs](https://docs.langchain.com/oss/python/langgraph/interrupts) — 2026-04-12
- [How to resume the agent workflow after interrupt() — LangChain Forum](https://forum.langchain.com/t/how-to-resume-the-agent-workflow-after-interrupt/434) — 2026-04-12
- [Making it easier to build human-in-the-loop agents with interrupt — LangChain Blog](https://blog.langchain.com/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt/) — 2026-04-12
- [Human-in-the-loop — LangChain Docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop) — 2026-04-12
- [Architecting Prompts for Agentic Systems — JB (Medium)](https://medium.com/@jbbooth/architecting-prompts-for-agentic-systems-aligning-ai-behavior-with-human-expectations-25b689b3b8f6) — 2026-04-12
- [Recommendations for designing conversational user experiences — Microsoft Power Platform Well-Architected](https://learn.microsoft.com/en-us/power-platform/well-architected/experience-optimization/conversation-design) — 2026-04-12
- [Prompting guide — ElevenLabs](https://elevenlabs.io/docs/eleven-agents/best-practices/prompting-guide) — 2026-04-12
- [Advanced LangGraph: Conditional Edges and Tool-Calling Agents — James Li (DEV)](https://dev.to/jamesli/advanced-langgraph-implementing-conditional-edges-and-tool-calling-agents-3pdn) — 2026-04-12
- [LangGraph State Machine: Complex Branching Logic Guide — Markaicode](https://markaicode.com/langgraph-state-machine-branching-logic/) — 2026-04-12
- [LangGraph Deep Dive: State Machines, Tools, and Human-in-the-Loop — PremAI](https://blog.premai.io/langgraph-deep-dive-state-machines-tools-and-human-in-the-loop/) — 2026-04-12
- [Interrupts and Commands in LangGraph — James B. Mour (DEV)](https://dev.to/jamesbmour/interrupts-and-commands-in-langgraph-building-human-in-the-loop-workflows-4ngl) — 2026-04-12
- [Multi-turn conversation best practice — OpenAI Community](https://community.openai.com/t/multi-turn-conversation-best-practice/282349) — 2026-04-12
- [How to Build Multi-Turn AI Conversations — Rasa Blog](https://rasa.com/blog/multi-turn-conversation) — 2026-04-12
