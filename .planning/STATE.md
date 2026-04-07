# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-30)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Milestone v2.0 — Phase 8.2 complete, Phase 8.1 and 10 remain

## Current Position

Phase: 8.2 — Advisor Refactor + Schema Alignment (COMPLETE)
Plan: 3/3 plans complete
Status: All plans executed and verified. Advisor LLM reasoning captured, review v2 promoted, category pipeline wired, Manage + Analytics pages added.
Last activity: 2026-04-08 — Phase 8.2 verification passed

```
v2.0 Progress: [##########################] 26/32 plans
Phase 6:       [##########] 3/3 plans (complete)
Phase 7:       [##########] 3/3 plans (complete)
Phase 6.1:     [##########] complete
Phase 6.2:     [##########] 4/4 plans (complete)
Phase 6.3:     [##########] 6/6 plans (complete)
Phase 8:       [##########] 5/5 plans (complete)
Phase 8.1:     [####......] 0/4 plans (in progress — bugs documented)
Phase 8.2:     [##########] 3/3 plans (complete)
Phase 10:      [..........] 0/2 plans
```

## Performance Metrics

**Velocity (from v1.0):**
- Total plans completed: 27
- Average duration: 8 min
- Total execution time: ~3.5 hours

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
- Tailwind v4 CSS-first via pytailwindcss — not CDN, not v3 config (migrated to @import/@theme format)

Phase 6 discoveries:
- pytailwindcss v0.3 downloads Tailwind v4.2.2 (not v3). Migrated to v4 CSS-first format (@import "tailwindcss", @theme block). tailwind.config.js deleted.
- Starlette 1.0 changed TemplateResponse API: now `(request, name, context=)` instead of `(name, {"request": request, ...})`
- Circular import between main.py and pages.py resolved by extracting templates to `web/templating.py`
- itsdangerous required for SessionMiddleware cookie signing (added as dependency)

Phase 6 v2 redo discoveries (2026-04-02):
- projectRoot path resolution broken inside Docker — `Path(__file__).parent` resolves to site-packages, not /app. Fixed with directory-walking detection + /app fallback.
- mcp-rag container crashes on restart due to SSL cert error downloading sentence-transformers model. Fixed by mounting host HuggingFace cache as read-only volume with HF_HUB_OFFLINE=1.
- Ruff N802/N803/N806 rules conflict with CamelCase convention — suppressed in pyproject.toml.

Phase 7 discoveries (2026-04-02):
- FastAPI `EventSourceResponse` with manual construction expects strings/bytes, not `ServerSentEvent` objects. Fix: use `response_class=EventSourceResponse` on the endpoint decorator.
- `ServerSentEvent(data=...)` JSON-serializes strings (adds quotes). Use `raw_data=` for HTML/text payloads that HTMX injects directly into the DOM.
- Ruff N999 (module naming) and N812 (import alias) also conflict with CamelCase convention — added to suppression list.
- HTMX SSE dispatches `htmx:sseMessage` (camelCase with colon), not `sse-message`. Use CustomEvent + window listener pattern for Alpine.js integration.

### Critical Pitfalls to Avoid

From research (see .planning/research/PITFALLS.md):

1. **Checkpointer per-request** (HIGH recovery cost) — RESOLVED in Phase 6 (lifespan singleton)
2. **SSE generator not cancelled on disconnect** (MEDIUM) — Must check `request.is_disconnected()` in Phase 7
3. **HTMX SSE attribute placement** — `hx-ext="sse"` and `sse-connect` must be on the same element in Phase 7
4. **Interrupt/resume state lost** — Use `graph.aget_state()` to detect interrupts; no session flags in Phase 7
5. **Alpine.js state destroyed on HTMX swap** — Target inner leaf nodes; keep Alpine on stable outer containers in Phase 7+

### Phase Dependencies

- Phase 6 COMPLETE
- Phase 7 COMPLETE
- Phase 8 depends on Phase 7 (HTMX partial patterns established, backend data available from intake) — UNBLOCKED
- Phase 9 depends on Phase 8 (page navigation patterns established, claims data available)
- Phase 8 depends on Phase 6.3 (auth + reviewer pages must exist before agent output feeds into them)
- Phase 10 depends on Phase 8 (all agents must be functional before E2E test authoring)

### Research Flags (from SUMMARY.md)

- **Phase 9** — Fraud/Advisor agent data storage schema not yet researched; `003_add_agent_output_columns.py` migration likely needed. Run `/gsd:research-phase` before Phase 9 planning.
- **Phase 10** (conditional) — Playwright async SSE sentinel patterns may need deeper research if `waitForSelector` proves insufficient for multi-step LangGraph streaming.

### Pending Todos

- Verify actual requirement count: REQUIREMENTS.md header says 54 but enumeration yields 61. Update header during Phase 7.
- Phase 2.5 has 2 skipped plans (CSS reasoning block styles, E2E browser verification) — these are superseded by the new v2.0 UI and Playwright suite respectively.
- Pre-existing test failure: `testSubmitClaimCallsInsertClaimAndInsertReceipt` — FIXED in Phase 6.2 (commit ed1e16d, field key alignment).

### Blockers/Concerns

- Phase 2.5 remains not started (it was open when v2.0 was initialized). The new UI supersedes the Chainlit-specific plans (02.5-04 CSS, 02.5-05 E2E). Plans 02.5-01 through 02.5-03 (QwQ-32B, schema-driven prompt, progressive streaming) should be completed or skipped depending on whether the Chainlit migration context is still needed — MIGR-07 and MIGR-08 in Phase 7 carry these capabilities forward.

## Session Continuity

Last session: 2026-04-08
Stopped at: Completed 08.2-03-PLAN.md (Manage Claims page, Analytics page, sidebar Manage/Analytics links, category fix in review.py)
Resume file: None

### Roadmap Evolution

- v1.0 archived to MILESTONES.md (24/26 plans across phases 1–2.5)
- v2.0 milestone started: Phases 6–10, 14 plans total
- Phase 6 completed: 2026-04-01 (3 plans, 3 waves)
- Phase 7 completed: 2026-04-02 (3 plans, 3 waves, 36 new tests, browser UAT passed)
