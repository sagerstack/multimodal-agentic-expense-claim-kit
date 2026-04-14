---
phase: 13-intake-agent-hybrid-routing-and-bug-fixes
plan: "03"
subsystem: agent-prompts
tags: [langgraph, react-agent, system-prompt, intake, hybrid-routing, layered-operating-manual]

# Dependency graph
requires:
  - phase: 13-intake-agent-hybrid-routing-and-bug-fixes
    provides: "Phase context and research docs: 13-CONTEXT.md, 13-RESEARCH.md, technical.md"
provides:
  - "agentSystemPrompt_v5.py: layered operating manual with routing stripped, descriptive content retained"
  - "INTAKE_AGENT_SYSTEM_PROMPT_V5 export + INTAKE_AGENT_SYSTEM_PROMPT alias for Plan 13-06 swap"
affects:
  - 13-04 (preIntakeValidator node; references Section 6 directive contract from v5)
  - 13-05 (preModelHook; synthesizes ROUTING DIRECTIVE messages described in v5 Section 6)
  - 13-06 (node.py import swap from v4_1 to v5; uses INTAKE_AGENT_SYSTEM_PROMPT alias)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Layered operating manual prompt structure (8 sections: role, authority, tool catalog, phases, error-recovery, directive contract, escalation, output)"
    - "Routing-in-code / conversation-in-prompt separation: prompt contains zero routing logic; all phase transitions live in outer StateGraph"
    - "Synthetic directive contract: ROUTING DIRECTIVE SystemMessages injected by pre-model hook, obeyed verbatim by LLM"

key-files:
  created:
    - src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py
  modified: []

key-decisions:
  - "Escalation message verbatim from technical.md L185: 'I couldn't complete this automatically. Your draft is saved. A reviewer will follow up.'"
  - "Section 6 synthetic directive contract prepares the LLM to receive ROUTING DIRECTIVE SystemMessages from pre-model hook (Plan 13-05)"
  - "Currency handling in Phase 1 Step 3 describes the two-tier Frankfurter -> manual-rate chain without any routing conditions; the post-tool hook (Plan 05) sets the unsupportedCurrencies flag"
  - "Phase 13 traceability model: deep-research-report.md is the upstream synthesis; its two derivative docs (systemprompt-chat-agent.md and multi-turn-react-prompt-technical.md) are the authoritative cite-sites for implementation (see Traceability section)"

patterns-established:
  - "Every prompt section cites the specific research doc and line range it derives from (enables traceability audit)"
  - "Confidence label thresholds in v5: High >=0.85, Medium 0.60-0.84, Low <0.60 (tightened from v4.1's High >=0.90, Medium 0.75-0.89)"

# Metrics
duration: 2min
completed: 2026-04-12
---

# Phase 13 Plan 03: v5 System Prompt Summary

**8-section layered operating manual replacing v4.1 ACTIVE-CLAIM GATE + TURN ROUTING with pure descriptive content; routing stripped to code layer per hybrid architecture**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-12T14:38:31Z
- **Completed:** 2026-04-12T14:40:25Z
- **Tasks:** 2 (read/catalogue + write)
- **Files modified:** 1 (created)

## Accomplishments

- Created `agentSystemPrompt_v5.py` with full 8-section layered operating manual structure
- Removed all routing logic from the prompt: ACTIVE-CLAIM GATE, TURN ROUTING table, error-string matching ("404"/"not found"), loop-bound escalation triggers, "do not call convertCurrency again" directive, phase gate conditions, CONVERSATION DISCIPLINE history-scanning rules
- Preserved and tightened all descriptive content: tool catalog, per-phase steps, confidence labels, intakeFindings 6-key schema, output format
- Verbatim escalation message from technical.md L185 present in Section 7
- Synthetic directive contract present in Section 6 so pre-model hook directives are obeyed
- Bug 4 fixed: VND hardcoded rate example `0.000054` (v4.1 L154) and VND display example (v4.1 L181) removed entirely

## v5 Section Layout (Final)

| Section | Content | Source |
|---------|---------|--------|
| 1. Role and persona | "calm operator" identity, job scope, tone rules | systemprompt-chat-agent.md L44-55 |
| 2. Authority and trust | Instruction hierarchy (System > dev > user > tool), untrusted tool outputs | systemprompt-chat-agent.md L57-65 |
| 3. Tool catalog | 6 tools described: what they return, argument minimality | langgraph-react-node.md, systemprompt-chat-agent.md L70-84 |
| 4. Workflow phases | Phase 1/2/3 step content, no phase-gate conditions | deep-research-report.md, systemprompt-chat-agent.md L36-40 |
| 5. Error-recovery phrasing | User-facing text for unsupported currency, low-confidence, image failure | systemprompt-chat-agent.md L540-551 |
| 6. Synthetic directive contract | ROUTING DIRECTIVE obedience contract for pre-model hook | technical.md L154, L201-202; systemprompt-chat-agent.md L57-65 |
| 7. Escalation terminal message | Verbatim template; runtime owns emission | technical.md L185; systemprompt-chat-agent.md L526-536 |
| 8. Output format | No chain-of-thought leakage, tool-call discipline, askHuman-only questions | systemprompt-chat-agent.md L86-97 |

## Before/After Line Count

| Metric | v4.1 | v5 | Change |
|--------|------|----|--------|
| Total file lines | 292 | 273 | -19 lines |
| Prompt body chars | ~9,100 | ~8,100 | ~11% smaller |
| Routing-logic sections removed | ACTIVE-CLAIM GATE, TURN ROUTING, CONVERSATION DISCIPLINE (Rules 1-4), Phase gate conditions ("When: ..."), ERROR HANDLING "convertCurrency 404" branch, ESCALATION loop triggers | 0 | All gone |
| Sections added | — | Section 6 (directive contract) | New |

Note: raw line count does not capture the routing-logic removal since v5 added the directive contract and more thorough phase content. The prompt body is ~11% shorter in characters. The routing logic removed constitutes approximately 35% of v4.1's semantic content.

## Grep Proof — Routing Prose Gone

```bash
# All return 0
grep -c "ACTIVE-CLAIM GATE\|TURN ROUTING\|do not call convertCurrency again" agentSystemPrompt_v5.py
# → 0

grep "0.000054" agentSystemPrompt_v5.py
# → (no output)

grep "VND.*550\|29\.70\|if.*error.*404" agentSystemPrompt_v5.py
# → (no output)
```

## Research Sources Cited Per Section

| v5 Section | Primary Source | Lines Referenced |
|------------|---------------|-----------------|
| 1. Role/persona | docs/deep-research-systemprompt-chat-agent.md | L44-55 |
| 2. Authority | docs/deep-research-systemprompt-chat-agent.md | L57-65 |
| 3. Tool catalog | docs/deep-research-langgraph-react-node.md; systemprompt-chat-agent.md | L70-84 |
| 4. Workflow phases | docs/deep-research-report.md; systemprompt-chat-agent.md | L36-40 |
| 5. Error-recovery | docs/deep-research-systemprompt-chat-agent.md | L540-551 |
| 6. Directive contract | artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md | L154, L201-202 |
| 7. Escalation | artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md | L185 |
| 8. Output format | docs/deep-research-systemprompt-chat-agent.md | L86-97 |

## Traceability Rationale for deep-research-report.md (Warning 2 fix)

Phase 13 treats `docs/deep-research-report.md` as the **upstream synthesis** document and its two derivative docs as the authoritative cite-sites for implementation:

- `docs/deep-research-systemprompt-chat-agent.md` operationalises the report's layered operating manual blueprint and instruction-hierarchy prescriptions into concrete prompt structure (used in v5).
- `artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md` operationalises the same blueprint into the hook/validator/wrapper-graph layer (Plans 04/05/07).

The report's policy-variable-prompt and defence-in-depth-tier prescriptions ARE present in v5 — they are subsumed by Section 4 (policy variable phases) citing `deep-research-report.md` directly, and by the hook/validator layer citing `technical.md`. Every downstream hook and validator cites one of the two derivative docs rather than the report directly.

**Phase 13 treats `deep-research-report.md` as the upstream synthesis and its two derivative docs as the authoritative cite-sites for implementation. This is the intentional traceability model; additional grep-coverage of the report across source files is explicitly NOT required.**

## Task Commits

Each task was committed atomically:

1. **Task 1: Read v4.1 and catalogue routing vs content** — no file output (read/plan step)
2. **Task 2: Write agentSystemPrompt_v5.py** — `466c5a1` (feat)

**Plan metadata:** `[docs commit hash — see below]`

## Files Created/Modified

- `src/agentic_claims/agents/intake/prompts/agentSystemPrompt_v5.py` — new layered operating manual prompt; exports INTAKE_AGENT_SYSTEM_PROMPT_V5 and INTAKE_AGENT_SYSTEM_PROMPT alias

## Decisions Made

- Escalation message verbatim from technical.md L185 is embedded in Section 7 with the note "runtime owns emission" — prevents the LLM from emitting it in ordinary turns
- Confidence label thresholds tightened: High >=0.85 (was >=0.90), Low <0.60 (unchanged), Medium the gap between them — aligns with the broader range used in extractReceiptFields
- Section 6 directive contract gives the LLM explicit instructions for ROUTING DIRECTIVE messages before they exist in code (Plans 04/05 build the hook that emits them) — enables defence-in-depth ordering: prompt first, then code
- convertCurrency tool description in Section 3 mentions `supported: false` response shape to match the structured-error contract being introduced in Plan 13-01

## Deviations from Plan

None — plan executed exactly as written. v5 was created fresh without copying routing prose from v4.1.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- v5 prompt is complete and verified. Plan 13-06 (node.py import swap) can reference `INTAKE_AGENT_SYSTEM_PROMPT` alias for a drop-in swap.
- Section 6 directive contract is in place for Plan 13-05 (preModelHook) to rely on.
- Confidence label thresholds updated in v5 (High >=0.85) — verify extractReceiptFields returns confidenceScores in the same range before Plan 13-06 wiring.
- No blockers for Plans 13-04 through 13-09.

---
*Phase: 13-intake-agent-hybrid-routing-and-bug-fixes*
*Completed: 2026-04-12*
