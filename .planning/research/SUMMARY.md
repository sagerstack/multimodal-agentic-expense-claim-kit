# Project Research Summary

**Project:** Agentic Expense Claims — v2.0 UX Redesign (Chainlit → FastAPI + HTMX)
**Domain:** Multi-page server-rendered AI chat application with LangGraph streaming backend
**Researched:** 2026-03-30
**Confidence:** HIGH

---

## Executive Summary

This milestone replaces Chainlit with a custom FastAPI + Jinja2 + HTMX web application while leaving the entire backend stack unchanged. The research confirms this is a well-understood pattern in 2026: FastAPI 0.135.2 ships native SSE support, HTMX 2.0.8 has a mature SSE extension, and Alpine.js 3.x handles client-side state cleanly. The combination covers all required interactivity (streaming AI responses, drag-and-drop file upload, real-time thinking panels, interrupt/resume clarification) without a JavaScript build pipeline. All technology choices are validated against official documentation with HIGH confidence.

The recommended approach is a clean vertical slice: introduce a `web/` package inside `src/agentic_claims/` to house the new FastAPI app, routers, session management, and dependencies. Jinja2 templates live at the repo root (matching the Stitch HTML designs directly). The LangGraph graph is compiled once at app startup via FastAPI's lifespan pattern and shared as a singleton via `app.state`. Each browser session gets isolated state through Starlette's `SessionMiddleware` (signed cookie holding `thread_id` + `claim_id`), with all LangGraph checkpointing still persisted in PostgreSQL.

The critical risks are infrastructure-level, not feature-level. Two pitfalls can cause complete rewrites if ignored: opening the `AsyncPostgresSaver` checkpointer per-request instead of once at app startup (produces connection-closed errors on every second message), and failing to cancel SSE generators on client disconnect (causes silent LLM cost burn and memory leaks). Both have clear prevention patterns that must be established in Phase 1 before any streaming work begins. SSE event name mismatches, Alpine state destruction from HTMX DOM swaps, and the Playwright EventSource interception limitation are well-understood moderate risks with documented mitigations.

---

## Key Findings

### Recommended Stack

The new UI layer adds six components on top of the unchanged backend (LangGraph, PostgreSQL, Qdrant, MCP servers, OpenRouter). All are either already in the stack or add zero operational overhead. FastAPI 0.135.2 and Jinja2 3.1.6 are the server-side core. HTMX 2.0.8 + Alpine.js 3.x handle frontend interactivity with no build step. Tailwind via `pytailwindcss` (v3, matching the Stitch designs) generates production CSS without Node.js. Playwright with the async pytest plugin covers E2E tests.

See `.planning/research/STACK.md` for version matrix, CDN vs vendor tradeoffs, and installation commands.

**Core technologies:**
- **FastAPI 0.135.2**: ASGI web framework with native SSE (`EventSourceResponse` built-in since 0.135.0); already in the stack.
- **Jinja2 3.1.6**: Server-side templating via Starlette's built-in `Jinja2Templates`; template inheritance maps directly to the 4 Stitch HTML designs.
- **HTMX 2.0.8 + htmx-ext-sse 2.2.4**: Hypermedia for all server round-trips; SSE extension for declarative token streaming without JavaScript.
- **Alpine.js 3.x**: Local client state (drag-over highlight, thinking panel expand/collapse, file preview); auto-picks up HTMX-injected DOM via MutationObserver.
- **pytailwindcss 0.3.0 (Tailwind v3)**: Wraps Tailwind v3 standalone CLI; stays on v3 because the Stitch designs use `tailwind.config = { theme: { extend: { colors: {...} } } }` JS config syntax, which breaks under v4's CSS-first `@theme` system.
- **playwright 1.58.0 + pytest-playwright-asyncio 0.7.2**: Browser E2E testing with async-native fixtures; consistent with the project's existing `pytest-asyncio` usage.
- **Starlette SessionMiddleware + StaticFiles** (bundled): Cookie-based session for `thread_id`/`claim_id`; static file serving for built CSS and vendored JS.

**What NOT to use:** `sse-starlette` (redundant), Tailwind v4 CDN, React/Vue/any SPA, WebSockets, `fastapi-jinja` (abandoned), or pytest-playwright sync variant.

---

### Expected Features

The 4 Stitch HTML pages define the full feature set. Research confirmed industry norms (Expensify, Ramp, AppZen) and validated which features are genuinely expected vs. differentiating.

See `.planning/research/FEATURES.md` for the full feature priority matrix and dependency graph.

**Must have (table stakes):**
- SSE-streamed AI responses — static "wait and load" is unacceptable in 2026 for any AI chat UI
- Drag-and-drop receipt upload with inline image preview in the chat thread
- Visible AI thinking state (spinner/indicator while VLM extraction and policy check run)
- Clarification prompt display + clarification pause (LangGraph interrupt surfaces as a UI pattern)
- Submission summary right panel with item count, total, category breakdown, and warning flags count
- KPI cards on the approver dashboard (Pending, Auto-Approved, Escalated counts)
- Recent Claims table with status column and row navigation to Claim Review page
- Decision pathway timeline on the Audit Log page (Upload → Extraction → Policy Check → Final Decision)
- Flag reason card + Approve/Reject actions on the Claim Review page

**Should have (differentiators):**
- Thinking panel with named step labels (maps LangGraph node names to human-readable text — the research contribution the demo is built around)
- Inline per-field confidence scores in the chat extraction response
- Policy citation with specific clause reference in the chat response
- AI Insight card on Claim Review (Advisor Agent's contextual note for the human reviewer)
- Download Log as JSON on the Audit Log page

**Defer (v2+):**
- Voice input (requires Web Speech API or Whisper)
- Return-to-Claimant action on Claim Review (requires Email MCP wiring; Approve/Reject is sufficient for demo)
- Anomaly Detection + Cost Benchmark bento cards (require historical data and Fraud Agent completion)
- Auto-Approval Threshold editing (requires Advisor Agent reading config at runtime)

**Critical dependency note:** Page 1 (Chat) is fully functional with only the Intake Agent. Pages 3 and 4 (Audit Log, Claim Review) require Compliance + Fraud + Advisor agent output to show the full decision pathway and flag reason card. Page 2 (Dashboard) requires only database queries against `claims.status`.

---

### Architecture Approach

The architecture is a clean UI-layer replacement. The `src/agentic_claims/web/` package is added; everything else in `src/agentic_claims/` (core, agents, infrastructure) is unchanged. A single `app.state.graph` instance (compiled at startup via `lifespan`) handles all concurrent sessions — each session is isolated by `thread_id` which flows through the LangGraph checkpointer. POST messages and GET SSE streams are decoupled via per-session `asyncio.Queue` objects: the message POST enqueues and returns an HTMX HTML fragment immediately; the long-lived SSE GET dequeues and streams graph events.

See `.planning/research/ARCHITECTURE.md` for the full system diagram, project structure, and all 5 architectural patterns with code examples.

**Major components:**
1. **`web/main.py`** — FastAPI app, lifespan (checkpointer + graph initialization), middleware (SessionMiddleware, StaticFiles), router mounting.
2. **`web/routers/pages.py`** — Full-page GET routes returning `TemplateResponse` for all 4 pages.
3. **`web/routers/chat.py`** — `POST /chat/message` (enqueue + return HTML fragment) and `GET /chat/stream` (SSE bridge to `astream_events()`).
4. **`web/routers/api.py`** — JSON endpoints for dashboard KPI counts, audit log data, and claim review details (HTMX partial swaps on non-chat pages).
5. **`web/session.py`** — Dependency that reads/creates `thread_id` + `claim_id` from the signed session cookie.
6. **`templates/`** — `base.html` (shared layout: sidebar, topnav, Tailwind config) + 4 page templates + partial fragments for HTMX swaps.

**Key patterns:**
- Graph as application-level singleton via `lifespan` (never per-request)
- `asyncio.Queue` per `thread_id` to decouple POST from SSE GET
- HTMX `HX-Request` header check to return partial vs. full template
- Alpine.js state scoped to stable outer containers; HTMX swaps target inner leaf nodes only
- Centralized `SseEvent` constants class shared between server and templates

---

### Critical Pitfalls

See `.planning/research/PITFALLS.md` for all 12 pitfalls with code examples, warning signs, and recovery costs.

1. **Checkpointer per-request lifecycle** — Opening `AsyncPostgresSaver` in a request handler instead of `lifespan` causes `psycopg.OperationalError: the connection is closed` on every second message. Must be resolved in Phase 1. **Recovery cost: HIGH.**

2. **SSE generator not cancelled on client disconnect** — Closing a browser tab leaves `astream_events()` running, burning LLM tokens and Postgres connections. Check `await request.is_disconnected()` inside the generator loop. Must be implemented from day one. **Recovery cost: MEDIUM.**

3. **HTMX SSE attribute placement bug** — `hx-ext="sse"` and `sse-connect` must be on the same element. Splitting them across parent/child silently prevents SSE from connecting with zero console errors. **Recovery cost: LOW but costs hours to diagnose.**

4. **Interrupt/resume state lost between requests** — The Chainlit `awaiting_clarification` flag does not survive stateless HTTP. Use `await graph.aget_state()` to inspect `state.tasks` for pending interrupts before each dispatch. **Recovery cost: MEDIUM.**

5. **Alpine.js state destroyed on HTMX DOM swap** — HTMX replacing a container that owns Alpine `x-data` resets local state (collapsed panel, file preview). Target inner leaf nodes with swaps; keep Alpine state on stable outer containers. **Recovery cost: MEDIUM.**

---

## Implications for Roadmap

Based on combined research, a 6-phase structure is recommended. The ordering is driven by infrastructure dependencies (checkpointer and SSE patterns must be correct before any feature work), then by agent dependencies (Page 1 first because it only needs Intake Agent; Pages 3–4 last because they need Compliance + Fraud + Advisor output).

### Phase 1: FastAPI Scaffold + Static Pages

**Rationale:** All pitfalls classified as "Phase 1 / FastAPI Scaffold" (checkpointer lifecycle, Jinja2 template paths, StaticFiles mounting) must be resolved before any streaming or feature work begins. Getting these wrong causes cascading failures that are expensive to retrofit.

**Delivers:** Running FastAPI app serving all 4 static pages (no backend data yet), correct middleware stack, lifespan with compiled graph singleton, single shared Jinja2Templates instance, static file serving with `url_for`, session middleware with `thread_id`/`claim_id` creation. Smoke-tests in Docker verify zero 404s and no `TemplateNotFound` errors.

**Features from FEATURES.md:** Shared layout (sidebar, top nav, active page indicator), page navigation shell for all 4 pages.

**Pitfalls to avoid:** Checkpointer per-request lifecycle (Pitfall 1), Jinja2 template path breaks (Pitfall 7), StaticFiles 404s in Docker (Pitfall 8).

**Research flag:** Standard patterns — skip `/gsd:research-phase`.

---

### Phase 2: SSE Streaming + Thinking Panel

**Rationale:** The SSE event taxonomy must be designed before writing either the backend stream or the frontend templates. Pitfalls 3, 5, 6, and 12 all live in this phase. The queue-based POST → SSE decoupling pattern is non-obvious and must be established before page-specific feature work builds on top of it.

**Delivers:** Working `POST /chat/message` → `asyncio.Queue` → `GET /chat/stream` pipeline. All 6 SSE event types rendering correctly in isolation (`thinking_start`, `step_name`, `step_content`, `thinking_done`, `token`, `done`). Centralized `SseEvent` constants. Disconnect detection active. Alpine.js thinking panel with collapse/expand that survives 10 consecutive tool executions without state reset.

**Features from FEATURES.md:** SSE-streamed AI responses (P1), visible AI thinking state (P1), thinking panel with named step labels (P2).

**Stack from STACK.md:** FastAPI `EventSourceResponse`, HTMX `hx-ext="sse"` + `sse-connect` + `sse-swap`, Alpine.js `x-show`.

**Pitfalls to avoid:** HTMX SSE attribute placement (Pitfall 3), thinking panel event taxonomy (Pitfall 5), Alpine/HTMX swap conflict (Pitfall 6), event name case sensitivity (Pitfall 12), SSE disconnect cleanup (Pitfall 2).

**Research flag:** SSE + LangGraph integration is moderately novel. Consider `/gsd:research-phase` if Playwright SSE testing strategy needs deeper investigation before finalizing the event taxonomy.

---

### Phase 3: Chat Page — Upload, Interrupt, Summary Panel

**Rationale:** With SSE streaming proven, the full Page 1 feature set can be completed. This phase adds receipt upload (multipart form), interrupt/resume (clarification flow), and the submission summary panel. Pitfalls 4 and 10 must be addressed here.

**Delivers:** Drag-and-drop receipt upload with inline image preview, multipart `Form()` + `File()` endpoint (no JSON body mixing), interrupt detection via `graph.aget_state()`, clarification prompt display in chat, confirm/edit quick-reply buttons, submission summary right panel with item count/total/warnings, batch details list.

**Features from FEATURES.md:** Drag-and-drop upload (P1), clarification interrupt/resume (P1), submission summary panel (P1), inline field confidence scores (P2), policy citation in chat response (P2).

**Pitfalls to avoid:** Interrupt/resume state lost (Pitfall 4), multipart form + file mixing (Pitfall 10).

**Research flag:** Standard patterns — skip `/gsd:research-phase`.

---

### Phase 4: Dashboard + Audit Log Pages (Pages 2 and 3)

**Rationale:** Page 2 (Dashboard) requires only database queries — no agent changes needed. Page 3 (Audit Log) can be built with data already available from the Intake Agent (extraction confidence, policy citations). Both pages share HTMX partial-swap patterns already established in Phase 2.

**Delivers:** Approver dashboard with 3 KPI cards, Recent Claims table with status filter and row navigation. Audit Log with claim list (status badges), decision pathway timeline (timestamps from `audit_log`), confidence score display, policy citation, Download Log as JSON.

**Features from FEATURES.md:** All P1 features for Pages 2 and 3; AI Efficiency trend chart deferred (P3 — needs historical data).

**Pitfalls to avoid:** Returning full page from HTMX partial routes (check `HX-Request` header), `astream_events` without event filtering.

**Research flag:** Standard HTMX patterns for filtering/partial swaps — skip `/gsd:research-phase`.

---

### Phase 5: Claim Review Page + Agent Completion (Page 4)

**Rationale:** The Claim Review page is strictly blocked on Fraud Agent output (`matched_claim_id`, `risk_score`) and Advisor Agent output (`advisor_notes`, routing decision). This phase completes both the agent stubs AND the Claim Review UI together so they can be tested end-to-end.

**Delivers:** Receipt image display, extracted fields panel, AI flag reason card with confidence score, Approve/Reject action buttons with reviewer notes and rejection reason radio buttons, claim navigation (Previous/Next), AI Insight card (Advisor Agent contextual note), linked duplicate reference. Compliance + Fraud + Advisor agents producing stored output. Likely requires migration `003_add_agent_output_columns.py`.

**Features from FEATURES.md:** All P1 and P2 features for Page 4; Return-to-Claimant deferred (P3 — requires Email MCP wiring).

**Research flag:** Fraud + Advisor agent completion patterns and the required database schema for agent outputs are not yet fully researched. Recommend `/gsd:research-phase` before this phase.

---

### Phase 6: E2E Tests + Production Polish

**Rationale:** Playwright SSE testing requires a deliberate strategy (Pitfall 11: `page.route()` cannot intercept EventSource connections). All E2E tests must use sentinel elements + `waitForSelector`. HTTP/2 configuration for the 6-connection browser limit is deferred here — not a local dev concern.

**Delivers:** Full Playwright E2E test suite covering the happy path and one escalation path. `data-testid` sentinel elements on all SSE completion points. Zero `waitForTimeout()` calls. HTTP/2 configuration documented for production.

**Stack from STACK.md:** `pytest-playwright-asyncio 0.7.2`, `uvicorn` live server fixture.

**Pitfalls to avoid:** Playwright EventSource interception limitation (Pitfall 11), HTTP/1.1 6-connection limit (Pitfall 9).

**Research flag:** Playwright async SSE sentinel pattern is moderately uncommon. Keep `/gsd:research-phase` available if async fixture coordination with the live server proves complex.

---

### Phase Ordering Rationale

- **Infrastructure first:** The checkpointer lifecycle pitfall (Pitfall 1) has HIGH recovery cost. Resolving it in Phase 1 protects all subsequent phases from a rewrite-level failure.
- **SSE event taxonomy before features:** The event names, swap targets, and Alpine state boundaries affect every streaming feature in Phases 3–5. Designing them wrong requires rework across multiple pages.
- **Page 1 before Pages 2–4:** Chat is the only page fully independent of Compliance/Fraud/Advisor agents. Delivering it first produces a demonstrable vertical slice.
- **Dashboard before Audit Log:** Dashboard requires only `claims.status` queries (simplest path). Audit Log needs `audit_log` events but no agent dependency beyond Intake.
- **Claim Review last:** Strictly blocked on Fraud + Advisor agents producing stored output. No workaround exists.
- **E2E tests in final phase:** Sentinel elements should be added to templates as pages are built in Phases 2–5, so Phase 6 is purely test authoring against a complete system.

### Research Flags

Phases needing `/gsd:research-phase` during planning:
- **Phase 5:** Fraud + Advisor agent patterns, multi-agent data flow, and database schema for agent outputs (new fields not yet researched)
- **Phase 6 (conditional):** Playwright async SSE test fixtures if the sentinel approach proves insufficient for LangGraph multi-step streaming

Phases with well-documented patterns (skip research-phase):
- **Phase 1:** FastAPI lifespan, SessionMiddleware, StaticFiles — all from official docs, fully verified
- **Phase 2:** SSE streaming patterns fully researched in STACK.md and PITFALLS.md
- **Phase 3:** HTMX multipart upload, interrupt/resume — patterns documented in ARCHITECTURE.md
- **Phase 4:** HTMX partial swap patterns, dashboard queries — established patterns

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via PyPI and official docs. Tailwind v3 vs v4 decision based on direct inspection of Stitch design files. |
| Features | HIGH | Primary source is the Stitch HTML designs (first-party). Industry benchmarks from web search (MEDIUM) only influenced prioritization, not the core feature list. |
| Architecture | HIGH | FastAPI/Starlette/HTMX patterns from official docs. LangGraph integration verified from working code in the existing codebase. Queue-based POST→SSE decoupling is a well-established pattern. |
| Pitfalls | HIGH | Pitfalls 1–2 sourced from a production migration post and FastAPI official docs. Pitfalls 3 and 6 from official HTMX/Alpine repos and confirmed GitHub issues. All 12 pitfalls have documented prevention patterns. |

**Overall confidence: HIGH**

### Gaps to Address

- **Fraud + Advisor agent data storage schema:** The Claim Review page requires `matched_claim_id`, `risk_score`, and `advisor_notes` stored in either the `claims` table or `audit_log`. The exact schema is not yet defined. Resolve in Phase 5 planning — likely requires migration `003_add_agent_output_columns.py`.
- **Auto-Approval Threshold storage:** Where this value lives (env config, database config table, or Advisor Agent logic) is not yet decided. Low risk for Phase 4 (display read-only), but must be resolved before Phase 5 (Advisor Agent needs to read it).
- **Tailwind production build integration:** The current Dockerfile uses Tailwind CDN (from Stitch designs). Integrating `pytailwindcss` into the Docker build step requires a Dockerfile change. Not blocking for development phases, but must happen before any production deployment.

---

## Sources

### Primary (HIGH confidence)

- `fastapi.tiangolo.com/tutorial/server-sent-events/` — FastAPI native SSE, `EventSourceResponse`, `ServerSentEvent` API
- `pypi.org/project/fastapi/` — FastAPI version 0.135.2, release date March 23, 2026
- `htmx.org/extensions/sse/` — HTMX SSE extension v2.2.4, attribute placement constraints, event matching
- `alpinejs.dev/start-here` — Alpine.js v3 CDN, `x-data`, `x-on`, `x-show`
- `pypi.org/project/playwright/` — Playwright 1.58.0
- `pypi.org/project/pytest-playwright-asyncio/` — pytest-playwright-asyncio 0.7.2
- `pypi.org/project/pytailwindcss/` — pytailwindcss 0.3.0
- `tailwindcss.com/docs/upgrade-guide` — v3→v4 breaking changes (JS config → CSS `@theme`)
- `starlette.dev/middleware/` — SessionMiddleware, StaticFiles
- `docs/ux/01_ai_chat_submission.html` (project file) — Confirms Tailwind v3 JS config format in Stitch designs
- `medium.com/@termtrix/i-built-a-langgraph-fastapi-agent-and-spent-days-fighting-postgres` — Checkpointer lifecycle pitfall from real production migration
- `jasoncameron.dev/posts/fastapi-cancel-on-disconnect` — SSE disconnect detection pattern
- `github.com/alpinejs/alpine/discussions/4478` — Alpine state loss on HTMX swaps
- `github.com/microsoft/playwright/issues/15353` — Playwright EventSource interception limitation (documented)
- `github.com/bigskysoftware/htmx/issues/3467` — HTMX SSE attribute placement constraint (confirmed)

### Secondary (MEDIUM confidence)

- Stitch HTML designs: `docs/ux/02_audit_transparency_log.html`, `03_claim_review_escalation.html`, `04_approver_dashboard.html` — Feature specification (first-party design intent)
- Expensify, Ramp, AppZen feature benchmarks — industry norm validation for P1/P2/P3 feature prioritization
- `shaveen12.medium.com/langgraph-human-in-the-loop-hitl-deployment-with-fastapi` — interrupt/resume thread_id consistency pattern
- `sparkco.ai/blog/mastering-langgraph-checkpointing-best-practices-for-2025` — connection pool patterns, lifespan recommendation

---

*Research completed: 2026-03-30*
*Ready for roadmap: yes*
