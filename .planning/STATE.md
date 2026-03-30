# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-30)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Milestone v2.0 — Phase 6: FastAPI Scaffold + Static Shell

## Current Position

Phase: 6 — FastAPI Scaffold + Static Shell
Plan: Not started
Status: Roadmap defined, ready for Phase 6 planning
Last activity: 2026-03-30 — v2.0 roadmap created (Phases 6–10)

```
v2.0 Progress: [..........] 0/14 plans
Phase 6:       [..........] 0/3 plans
```

## Performance Metrics

**Velocity (from v1.0):**
- Total plans completed: 24
- Average duration: 8 min
- Total execution time: 2.97 hours

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

Carried forward from v1.0:
- LangGraph orchestration: validated, continues
- MCP servers as Docker services: validated, continues
- Vertical slice architecture per agent: validated, continues
- CamelCase naming throughout: validated, continues
- OpenRouter via OpenAI SDK: validated, continues
- FastMCP with Streamable HTTP: validated, continues

New for v2.0:
- Chainlit replaced by FastAPI + Jinja2 + HTMX
- Stitch HTML designs (`docs/ux/`) are the UI spec
- Dark theme only ("Neon Nocturne")
- Playwright for browser E2E tests (Phase 10)
- SSE for chat streaming via HTMX sse extension (Phase 7)
- Alpine.js for local UI state (Phase 7, 9)
- `asyncio.Queue` per session to decouple POST from SSE GET (Phase 7)
- Checkpointer as lifespan singleton — not per-request (Phase 6, critical pitfall prevention)
- Tailwind v3 via pytailwindcss — not CDN, not v4 (Stitch designs use v3 JS config syntax)

### Critical Pitfalls to Avoid

From research (see .planning/research/PITFALLS.md):

1. **Checkpointer per-request** (HIGH recovery cost) — Must be lifespan singleton in Phase 6
2. **SSE generator not cancelled on disconnect** (MEDIUM) — Must check `request.is_disconnected()` in Phase 7
3. **HTMX SSE attribute placement** — `hx-ext="sse"` and `sse-connect` must be on the same element in Phase 7
4. **Interrupt/resume state lost** — Use `graph.aget_state()` to detect interrupts; no session flags in Phase 7
5. **Alpine.js state destroyed on HTMX swap** — Target inner leaf nodes; keep Alpine on stable outer containers in Phase 7+

### Phase Dependencies

- Phase 6 has no hard dependency (replaces app.py)
- Phase 7 depends on Phase 6 (needs scaffold + static pages)
- Phase 8 depends on Phase 7 (HTMX partial patterns established, backend data available from intake)
- Phase 9 depends on Phase 8 (page navigation patterns established, claims data available)
- Phase 10 depends on Phase 9 (all 4 pages must be complete before E2E test authoring)

### Research Flags (from SUMMARY.md)

- **Phase 9** — Fraud/Advisor agent data storage schema not yet researched; `003_add_agent_output_columns.py` migration likely needed. Run `/gsd:research-phase` before Phase 9 planning.
- **Phase 10** (conditional) — Playwright async SSE sentinel patterns may need deeper research if `waitForSelector` proves insufficient for multi-step LangGraph streaming.

### Pending Todos

- Verify actual requirement count: REQUIREMENTS.md header says 54 but enumeration yields 61. Update header during Phase 6.
- Phase 2.5 has 2 skipped plans (CSS reasoning block styles, E2E browser verification) — these are superseded by the new v2.0 UI and Playwright suite respectively.

### Blockers/Concerns

- Phase 2.5 remains not started (it was open when v2.0 was initialized). The new UI supersedes the Chainlit-specific plans (02.5-04 CSS, 02.5-05 E2E). Plans 02.5-01 through 02.5-03 (QwQ-32B, schema-driven prompt, progressive streaming) should be completed or skipped depending on whether the Chainlit migration context is still needed — MIGR-07 and MIGR-08 in Phase 7 carry these capabilities forward.

## Session Continuity

Last session: 2026-03-30
Stopped at: v2.0 roadmap creation complete
Resume file: None

### Roadmap Evolution

- v1.0 archived to MILESTONES.md (24/26 plans across phases 1–2.5)
- v2.0 milestone started: Phases 6–10, 14 plans total
- Roadmap created: 2026-03-30
