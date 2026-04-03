# Roadmap: Agentic Expense Claims

## Overview

This roadmap covers two milestones. v1.0 (Phases 1-2.5) delivered the Intake Agent on Chainlit -- that work is archived. v2.0 (Phases 6-10) replaces Chainlit with a custom FastAPI + Jinja2 + HTMX multi-page application, migrates all validated intake functionality, and adds the Compliance, Fraud, and Advisor agents with a reviewer interface. The five phases in v2.0 are ordered by infrastructure dependency: the application scaffold must be correct before any streaming work begins, and the Claim Review page is strictly blocked on agent output from Compliance and Fraud.

## v1.0 Phases (Archived)

- [x] **Phase 1: Foundation Infrastructure** -- Project skeleton, LangGraph orchestration with 4 stub agents, Docker Compose
- [x] **Phase 2: Supporting Infrastructure** -- DB schema, MCP servers, OpenRouter client, Qdrant policy ingestion
- [x] **Phase 2.1: Intake Agent + Receipt Processing** -- VLM extraction, policy validation, conversational claim submission
- [x] **Phase 2.2: Intake Agent Gap Closure** -- submitClaim fix, structured output, prompt improvements
- [x] **Phase 2.3: Intake Agent UAT Fix** -- Field mapping fix, model fallback, streaming CoT, ConversationRunner
- [x] **Phase 2.4: CoT Thinking Panel + Bug Fixes** -- Reasoning tokens, idempotency, SSL, claim number sequence
- [ ] **Phase 2.5: Reasoning Panel + Model Upgrade** -- QwQ-32B, Type A+B reasoning, progressive streaming, schema-driven prompt

See MILESTONES.md for archived v1.0 details.

## v2.0 Phases

- [x] **Phase 6: FastAPI Scaffold + Static Shell** -- Replace Chainlit, all 4 pages served as static shells, lifespan singleton, session middleware
- [x] **Phase 7: SSE Streaming + Full Chat Page** -- SSE event taxonomy, streaming pipeline, V1 migration, complete Chat Page feature set
- [ ] **Phase 6.1: Model Upgrade + UX Fixes** -- Switch LLM from QwQ-32B to Qwen3-235B-A22B (fast MoE, no CoT chains), swap to v2 system prompt, fix submission summary panel (100% on submit, show Claim ID, correct amounts)
- [ ] **Phase 8: Dashboard + Audit Log Pages** -- Approver Dashboard (KPIs, claims table) and Audit & Transparency Log (decision timeline)
- [ ] **Phase 9: Claim Review Page** -- Escalated claim display, approve/reject actions, receipt zoom, claim navigation
- [ ] **Phase 10: Browser E2E Tests** -- Playwright test suite covering all 4 pages against a live server

---

## Phase Details

### Phase 6: FastAPI Scaffold + Static Shell

**Goal:** The FastAPI application is running in Docker, serving all 4 pages as static Jinja2-rendered shells with the full "Neon Nocturne" sidebar layout, and the LangGraph graph + checkpointer are initialized once at startup as singletons -- eliminating the critical per-request checkpointer lifecycle pitfall before any streaming work begins.

**Depends on:** Phase 2.5 (v1.0 complete)

**Requirements:** UIFN-01, UIFN-02, UIFN-03, UIFN-04, UIFN-05, UIFN-06, UIFN-07, UIFN-08, UIFN-09, UIFN-10, MIGR-02, MIGR-09, MIGR-10

**Success Criteria** (what must be TRUE when Phase 6 completes):
1. `docker compose up` starts the FastAPI app via uvicorn (not Chainlit); visiting all 4 page URLs returns HTTP 200 with the correct Jinja2 template rendered -- no 404s, no `TemplateNotFound` errors
2. All 4 pages display the shared sidebar navigation with correct active-page indicator highlighting, system status pulse animation, Manrope/Inter fonts, Material Symbols icons, and "Neon Nocturne" dark color scheme -- visually matching the Stitch designs
3. Tailwind CSS is generated via `pytailwindcss` (not CDN); the built CSS file is served from the static directory and renders the dark theme correctly
4. App startup logs confirm the LangGraph graph and `AsyncPostgresSaver` checkpointer are initialized exactly once in the lifespan context -- not per-request
5. All 61 existing unit/integration tests pass without modification; the ConversationRunner headless tests continue to function (backend unchanged)
6. Each page load creates or retrieves a signed session cookie containing `thread_id` and `claim_id` -- verifiable by inspecting cookies in the browser

**Plans:** 3 plans

Plans:
- [x] 06-01-PLAN.md -- FastAPI app structure (`web/` package), uvicorn Docker config, lifespan (checkpointer + graph singleton), SessionMiddleware, StaticFiles, pytailwindcss build
- [x] 06-02-PLAN.md -- Jinja2 base template (`base.html`): sidebar, top nav, active-page indicator, system status, fonts, icons, Neon Nocturne theme variables
- [x] 06-03-PLAN.md -- 4 page shells (Chat, Dashboard, Audit Log, Review) with full Stitch layout structure, all routing wired, smoke tests verify zero 404s

---

### Phase 7: SSE Streaming + Full Chat Page

**Goal:** The complete Chat Page (Page 1) is functional -- SSE streams token-by-token AI responses from the LangGraph Intake Agent, receipt upload stores the image and triggers VLM extraction, LangGraph interrupt/resume works for clarifications, the thinking panel streams named steps interleaved with reasoning, and all v1.0 Intake Agent capabilities work identically through the new UI.

**Depends on:** Phase 6

**Requirements:** STRE-01, STRE-02, STRE-03, STRE-04, STRE-05, MIGR-01, MIGR-03, MIGR-04, MIGR-05, MIGR-06, MIGR-07, MIGR-08, CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, CHAT-06, CHAT-07, CHAT-08, CHAT-09, CHAT-10, CHAT-11

**Success Criteria** (what must be TRUE when Phase 7 completes):
1. Uploading a receipt image in the new chat UI and typing a message triggers VLM extraction and streams the AI response token-by-token into the chat area -- the user sees the response building character-by-character, not appearing all at once
2. The thinking panel opens automatically when the agent begins processing, shows named step labels ("Extracting fields...", "Checking policy...", "Converting currency...") as they execute, and streams Type A agent reasoning and Type B QwQ reasoning tokens interleaved with tool summaries -- without losing its expand/collapse state across HTMX swaps
3. When the LangGraph interrupt fires (askHuman tool), the chat input is disabled and a clarification prompt appears in the chat; on the user's next message, the graph resumes from the interrupt -- interrupt state is detected via `graph.aget_state()` on each request, not carried in a session flag
4. Closing the browser tab while the agent is processing cancels the running `astream_events()` generator -- no continued LLM token burn after disconnect
5. The submission summary right panel updates in real-time to show current total, item count, category breakdown, and warning/flag count as claims are processed in the session
6. The SSE endpoint uses a per-session `asyncio.Queue` to decouple the `POST /chat/message` form submission from the `GET /chat/stream` SSE connection -- a `curl` test can confirm the POST returns an HTMX fragment immediately while the SSE stream delivers events asynchronously

**Plans:** 3 plans

Plans:
- [x] 07-01-PLAN.md -- SSE event taxonomy (`SseEvent` constants), `POST /chat/message` -> `asyncio.Queue` -> `GET /chat/stream` pipeline, `EventSourceResponse`, disconnect cleanup
- [x] 07-02-PLAN.md -- V1 migration: image upload endpoint (multipart Form + File), imageStore wiring, interrupt/resume via `graph.aget_state()`, QwQ-32B reasoning token pass-through
- [x] 07-03-PLAN.md -- Chat Page Jinja2 template completion: drag-and-drop upload with inline preview, thinking panel, confirm/edit buttons, submission summary panel, inline confidence scores, policy citation rendering

---

### Phase 6.1: Model Upgrade + UX Fixes

**Goal:** The Chat Page responds in seconds instead of minutes by switching the LLM from QwQ-32B (reasoning model with uncontrollable 1-3min CoT chains) to Qwen3-235B-A22B-Instruct (fast MoE, 22B active params, no thinking mode), and the Submission Summary panel correctly reflects claim state after submission -- showing 100% complete, the Claim ID, converted amounts, and category.

**Depends on:** Phase 7

**Requirements:** STRE-04, CHAT-05, MIGR-07

**Success Criteria** (what must be TRUE when Phase 6.1 completes):
1. A receipt upload + full claim submission flow completes in under 60 seconds total (all turns combined), down from 7+ minutes with QwQ-32B
2. The thinking panel shows tool activity steps (names + summaries) without reasoning preview content -- no empty or broken panels
3. After `submitClaim` succeeds, the Submission Summary panel shows: 100% Complete, the claim number (CLAIM-XXX), the correct SGD amount, the expense category, and the "Submit Entire Batch" button is hidden
4. The v2 system prompt is active with tool-calling discipline, submission reality guardrails, and self-verification -- imported from `agentSystemPrompt_v2.py`
5. All existing tests pass without regression; new unit tests cover BUG-013 guard and step-driven progressPct

**Plans:** 2 plans

Plans:
- [ ] 06.1-01-PLAN.md -- Model switch (env config), v2 system prompt swap, ClaimState expansion (claimNumber), intakeNode state propagation, receipt image serving endpoint
- [ ] 06.1-02-PLAN.md -- Summary panel fixes (claimNumber header, 100% on submit, receipt thumbnail, conditional button), BUG-013 guard, step-driven progressPct, thinking panel header live tool name + duration counter, unit tests

---

### Phase 8: Dashboard + Audit Log Pages

**Goal:** The Approver Dashboard (Page 2) displays live KPI counts and a filterable recent claims table, and the Audit & Transparency Log (Page 3) shows a decision pathway timeline for each claim -- both pages use HTMX partial swaps for filtering and selection with data served from JSON API endpoints backed by the existing PostgreSQL claims and audit_log tables.

**Depends on:** Phase 7

**Requirements:** DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, AUDT-01, AUDT-02, AUDT-03, AUDT-04, AUDT-05, AUDT-06, AUDT-07

**Success Criteria** (what must be TRUE when Phase 8 completes):
1. The Dashboard page loads with three KPI cards showing live counts from the database: Total Pending, Auto-Approved, and Escalated -- refreshing the page after submitting a claim reflects the updated count
2. The Recent Claims table shows claim number, employee ID, category, amount, and a color-coded status badge for each claim; clicking a row navigates to the Claim Review page for that specific claim
3. The status filter buttons (Pending, Approved, Escalated) trigger an HTMX partial swap that replaces only the claims table rows without a full page reload -- the KPI cards and sidebar remain stable
4. The Audit Log page lists all claims in the left panel with status badge and amount; selecting a claim replaces the right panel with a vertical decision timeline showing Upload, AI Extraction, Policy Check, and Final Decision steps with timestamps
5. The AI Extraction timeline step shows the VLM confidence score; the Policy Check step shows the matched policy reference with a "View Policy Reference" link; the receipt image is accessible via the "View Receipt" button

**Plans:** 3 plans

Plans:
- [ ] 08-01-PLAN.md -- `GET /api/dashboard` JSON endpoint (KPI counts, claims table data with status filter), Dashboard Jinja2 template with KPI cards, status filter HTMX wiring, row navigation link
- [ ] 08-02-PLAN.md -- `GET /api/audit/{claim_id}` JSON endpoint (decision timeline from audit_log + claims), AI Efficiency panel (auto-approval rate)
- [ ] 08-03-PLAN.md -- Audit Log Jinja2 template: claim list panel, decision timeline right panel, confidence score display, policy citation link, View Receipt button

---

### Phase 9: Claim Review Page

**Goal:** The Claim Review Page (Page 4) allows a reviewer to inspect an escalated claim -- seeing the receipt image with zoom controls, extracted fields, the AI flag reason with confidence score, and pre-populated rejection reason options -- and submit an Approve or Reject decision with notes that updates the claim status in the database.

**Depends on:** Phase 8

**Requirements:** REVW-01, REVW-02, REVW-03, REVW-04, REVW-05, REVW-06, REVW-07, REVW-08

**Success Criteria** (what must be TRUE when Phase 9 completes):
1. Opening the Claim Review page for a specific claim displays the receipt image in the left column and extracted fields (merchant, date, amount, category) as read-only labeled cards in the right column -- data loaded from the database, not hardcoded
2. The flag reason card shows the AI-generated explanation and confidence score for why the claim was escalated
3. Clicking "Approve" with optional reviewer notes submits a PATCH request that updates the claim status to "approved" in the database and redirects to the next escalated claim; clicking "Reject" requires selecting a pre-defined rejection reason (Duplicate, Incomplete, Policy violation) before the button activates
4. The receipt image responds to zoom-in and zoom-out button clicks via Alpine.js CSS `transform: scale()` -- starting at 1x, incrementing/decrementing by 0.25x, bounded between 0.5x and 3x
5. Previous/Next navigation buttons cycle through escalated claims without returning to the dashboard -- the URL and displayed claim update in place via HTMX partial swap

**Plans:** 3 plans

Plans:
- [ ] 09-01-PLAN.md -- `GET /api/review/{claim_id}` and `PATCH /api/review/{claim_id}/decision` endpoints, escalated claims list endpoint for Previous/Next navigation
- [ ] 09-02-PLAN.md -- Claim Review Jinja2 template: receipt image display, extracted fields panel, flag reason card, approve/reject form with reviewer notes, rejection reason radio buttons
- [ ] 09-03-PLAN.md -- Alpine.js zoom controls (zoom in/out buttons, scale state, bounded range), Previous/Next navigation HTMX wiring

---

### Phase 10: Browser E2E Tests

**Goal:** A Playwright test suite covers the happy path through all 4 pages and one escalation path -- all tests use sentinel elements and `waitForSelector` (never `waitForTimeout`), run against a live uvicorn server in a background thread, and pass reliably in CI.

**Depends on:** Phase 9

**Requirements:** TEST-01, TEST-02, TEST-03, TEST-04, TEST-05

**Success Criteria** (what must be TRUE when Phase 10 completes):
1. Running `poetry run pytest tests/e2e/ -v` starts a live uvicorn server, runs all 5 Playwright tests, and all pass -- no `waitForTimeout` calls, no flaky timing-based assertions
2. The chat page E2E test uploads a receipt image, waits for the SSE stream to complete via a `data-testid="stream-done"` sentinel element, confirms extraction fields appear in the chat, and verifies the submission summary panel updates
3. The dashboard E2E test navigates to `/dashboard`, asserts all 3 KPI cards are present, verifies at least one claim row exists in the table, and confirms clicking a row navigates to the correct claim review URL
4. The audit log E2E test selects a submitted claim from the left panel and verifies the decision timeline appears in the right panel with at least 3 steps (Upload, Extraction, Policy Check)
5. The claim review E2E test opens an escalated claim, verifies the receipt image, extracted fields, and flag reason card are present, clicks Approve, and confirms the claim status updates to "approved" on redirect

**Plans:** 2 plans

Plans:
- [ ] 10-01-PLAN.md -- Playwright infrastructure: `live_server` fixture (uvicorn background thread), `data-testid` sentinel audit across all 4 page templates, pytest-playwright-asyncio configuration
- [ ] 10-02-PLAN.md -- E2E test authoring: 5 tests (chat, dashboard, audit log, claim review, escalation path), zero `waitForTimeout`, full pass verification

---

## Progress

**Execution Order:**
v2.0 phases execute in numeric order: 6 -> 7 -> 6.1 -> 8 -> 9 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 6. FastAPI Scaffold + Static Shell | 3/3 | Complete (v2 redo) | 2026-04-02 |
| 7. SSE Streaming + Full Chat Page | 3/3 | Complete | 2026-04-02 |
| 6.1. Model Upgrade + UX Fixes | 0/2 | Not started | -- |
| 8. Dashboard + Audit Log Pages | 0/3 | Not started | -- |
| 9. Claim Review Page | 0/3 | Not started | -- |
| 10. Browser E2E Tests | 0/2 | Not started | -- |

**v2.0 total:** 6/16 plans complete

**v1.0 (archived):** 24/26 plans complete (see MILESTONES.md)
