# Phase 14: intake-gpt Deterministic Workflow Hardening - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete the interrupt state machine and runtime advancement in the intake-gpt subgraph (`src/agentic_claims/agents/intake_gpt/`). The goal is a fully deterministic workflow where the runtime enforces WHAT happens next at every workflow gate, and the LLM handles HOW it is communicated conversationally.

This phase does NOT add new workflow steps or change the claim submission flow. It hardens the existing flow.

</domain>

<decisions>
## Implementation Decisions

### Interrupt UI affordances — structured responses for binary decisions

Field confirmation and submit confirmation use **Yes/No clickable buttons** in the chat UI, not free text. This eliminates the classification problem for binary decision points entirely.

- `field_confirmation` interrupt: renders Yes/No buttons. User must click to advance.
- `submit_confirmation` interrupt: renders Yes/No buttons. User must click to advance.
- `policy_justification` interrupt: free text only (user must type their reason — buttons don't apply here).
- Phase 14 covers both the backend change (emit a button-type interrupt) and the frontend change (render clickable buttons in the chat, handle click as structured reply).

### Interrupt classification mechanism

Since `field_confirmation` and `submit_confirmation` use buttons, classification for those is trivial (button click = answer, text during button prompt = side question candidate).

For `policy_justification` (free text): **pure logic classification**.
- Ends with `?` OR starts with interrogative word (`what`, `why`, `how`, `when`, `who`, `is`, `can`, `does`, `will`) → side question
- Contains negative tokens (`no`, `nope`, `cancel`, `skip`, `never mind`, `forget it`) → decline/cancel
- Everything else → justification answer (the user's text is preserved verbatim as the justification)

No LLM classification call. Classification is deterministic and unit-testable.

### Negative response recovery paths

**Field confirmation No (user clicks No):**
- Agent asks open-ended: "What looks incorrect?" (free text)
- LLM interprets the reply and updates the relevant slot(s)
- After correction: loop back to field confirmation — show updated extraction table + Yes/No buttons again
- User must click Yes before policy check runs

**Submit confirmation No (user clicks No):**
- Claim is cancelled entirely
- Full session reset (new claim ID if user wants to start again)
- Agent offers to start a new claim

### Side question re-presentation — consistent across all interrupts

When a user asks a side question during ANY pending interrupt (field confirmation, policy justification, submit confirmation):
1. LLM responds to the side question (conversational answer)
2. Runtime keeps `pendingInterrupt` open — no state change, no advancement
3. Agent steers back: "Back to [the pending question] — [re-present the blocking ask]"
   - Field confirmation: steers back with Yes/No buttons (no full table re-render)
   - Policy justification: steers back with "please provide your justification for the expense"
   - Submit confirmation: steers back with Yes/No buttons

No side question limit — the agent always steers back, no escalation after N questions.

### Deterministic gate scope — all remaining transitions hardened

All workflow transitions are runtime-enforced in Phase 14. The LLM cannot skip or narrate past any gate.

| Gate | Current state | Phase 14 target |
|---|---|---|
| field_confirmation Yes → searchPolicies | LLM-driven (Bug B) | Runtime-enforced |
| searchPolicies + violations → policy_justification | LLM-driven | Runtime-enforced |
| policy_justification answered → submit_confirmation | LLM-driven | Runtime-enforced |
| submit_confirmation Yes → submitClaim | Already runtime-enforced | No change needed |

After each gate clears, the runtime calls the next step. The LLM's job is to communicate around that enforced call — not to decide whether to make it.

### Turn pattern (confirmed design intent)

Every agent turn follows this structure:
1. LLM responds to the user's message (conversational acknowledgment, answer to question, or correction confirmation)
2. Runtime enforces the next workflow step (tool call or interrupt opening)
3. LLM presents the result and asks the confirmation question for that step (or re-presents the pending interrupt if still blocked)

### Existing bugs fixed by these decisions

- **Bug A** (interrupt classification): field_confirmation and submit_confirmation use buttons (no classification needed); policy_justification uses pure logic (symmetric for all token types, not just submit_confirmation)
- **Bug B** (missing deterministic advancement): all 3 remaining gates hardened
- **Bug C** (justification persistence): pure logic preserves the user's actual text verbatim — no token match string overwrites it
- **Bug D** (prompt inconsistency): prompt can be trimmed of workflow prose since runtime enforces progression

### Additional cleanup (from code review)

- `IntakeGptSubgraphState` in `state.py` is dead code (never imported) — delete
- `_CURRENCY_SYMBOL_MAP`, `_VALID_CATEGORIES`, `_END_CONVERSATION_TOKENS`, `_AFFIRMATIVE_TOKENS`, `_NEGATIVE_TOKENS` are hardcoded business constants — move to `Settings` / config
- `applyToolResultsNode` processes only the last tool message — fix to process all tool messages in the turn
- Image detection in `turnEntryNode` uses `"uploaded a receipt image" in latestText.lower()` — decouple from Chainlit/app layer wording (use a state flag or content-type check)
- `interrupt_prompt.py` exists but is never imported — delete (dead file)
- System prompt (`prompt.py`) trimmed of workflow-step prose; retains only conversational guidance

### Claude's Discretion

- Exact button rendering approach in the chat UI (HTMX event, Alpine.js handler, or direct form element)
- How the backend SSE event signals a button-type interrupt vs a text interrupt
- Whether the field correction (after user says what's wrong) uses a targeted slot update or a full re-extraction pass
- Token set values for the config constants (starting values from current code)

</decisions>

<specifics>
## Specific Ideas

- "field_confirmation: we can give users two Yes/No button options so they have to click it to move forward? if they respond with a question instead, LLM responds with the answer but steers them back to the field conf" — confirmed design intent from user
- "it is option 2 but again show them the two options to click — Yes/No" — re-present buttons (not full table) after answering a side question at field confirmation
- "no limit — always re-present" — side question tolerance is infinite, always steer back
- "harden all remaining" — all 3 LLM-driven transitions become runtime-enforced, not just the one with the confirmed bug

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 14 scope.

</deferred>

---

*Phase: 14-intake-gpt-react-replacement*
*Context gathered: 2026-04-14*
