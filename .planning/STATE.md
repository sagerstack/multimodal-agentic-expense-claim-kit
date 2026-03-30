# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-30)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Milestone v2.0 — UX Redesign + Full Pipeline

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-03-30 — Milestone v2.0 started

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
- Playwright for browser E2E tests
- SSE for chat streaming (HTMX sse extension)
- Alpine.js for local UI state

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2.5 closed early (2 plans skipped — CSS and E2E were Chainlit-specific)
- Chainlit removal means rewriting app.py (~200 lines) as FastAPI routes
- ConversationRunner (headless E2E) must continue working after migration

## Session Continuity

Last session: 2026-03-30
Stopped at: Milestone v2.0 initialization
Resume file: None

### Roadmap Evolution

- v1.0 archived to MILESTONES.md (24 plans across phases 1-2.5)
- v2.0 milestone started: UX redesign + full agent pipeline
