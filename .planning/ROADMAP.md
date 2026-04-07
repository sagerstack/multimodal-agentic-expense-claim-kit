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
- [x] **Phase 6.1: Model Upgrade + UX Fixes** -- Switch LLM from QwQ-32B to Qwen3-235B-A22B (fast MoE, no CoT chains), swap to v2 system prompt, fix submission summary panel (100% on submit, show Claim ID, correct amounts)
- [x] **Phase 6.2: Chat UI Refresh + Employee ID Fix** -- Apply Stitch "Updated Branding" design to Chat Page (Decision Pathway sidebar, bottom submission table, message styling, top nav) and fix BUG-015 (server-side employee ID extraction)
- [x] **Phase 6.3: User Authentication + Dual Roles + Reviewer Pages** -- Login, auth, roles, Dashboard, Audit Log, Claim Review (absorbs Phase 8 + 9)
- [x] **Phase 8: Compliance, Fraud + Advisor Agents** -- Replace stubs with LLM-powered agents: policy audit, duplicate/anomaly detection, decision routing (auto-approve, return, escalate)
- [ ] **Phase 8.1: Bug Fixes + UX Polish** -- Fix Phase 8 QA bugs (BUG-016–025), restructure claim status lifecycle (8 statuses), Claims page "My Claims" section, draft status in table, LLM timeout handling
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

**Requirements:** MIGR-07, CHAT-09

**Success Criteria** (what must be TRUE when Phase 6.1 completes):
1. A receipt upload + full claim submission flow completes in under 60 seconds total (all turns combined), down from 7+ minutes with QwQ-32B
2. The thinking panel header shows the active tool name with a live duration counter during processing; short reasoning snippets are visible when the model produces pre-tool reasoning text; no empty or broken panels
3. After `submitClaim` succeeds, the Submission Summary panel shows: 100% Complete, the claim number (CLAIM-XXX), the correct SGD amount, the expense category, and the "Submit Entire Batch" button is hidden
4. The v2 system prompt is active with tool-calling discipline, submission reality guardrails, and self-verification -- imported from `agentSystemPrompt_v2.py`
5. All existing tests pass without regression; new unit tests cover BUG-013 guard and step-driven progressPct

**Plans:** 2 plans

Plans:
- [x] 06.1-01-PLAN.md -- Model switch (env config), v2 system prompt swap, ClaimState expansion (claimNumber), intakeNode state propagation, receipt image serving endpoint
- [x] 06.1-02-PLAN.md -- Summary panel fixes (claimNumber header, 100% on submit, receipt thumbnail, conditional button), BUG-013 guard, step-driven progressPct, thinking panel header live tool name + duration counter, unit tests

---

### Phase 6.2: Chat UI Refresh + Employee ID Fix

**Goal:** The Chat Page visually matches the Stitch "AI Chat Submission (Updated Branding)" design -- with a Decision Pathway sidebar replacing the current summary panel, a horizontal bottom submission summary table, updated message bubble styling with avatars and timestamps, and the top nav bar updated to match the new branding -- and BUG-015 is resolved by extracting the employee ID server-side from the user message instead of relying on the LLM to propagate it.

**Depends on:** Phase 6.1

**Requirements:** CHAT-06, CHAT-07, CHAT-09, CHAT-10

**Success Criteria** (what must be TRUE when Phase 6.2 completes):
1. The Chat Page right panel shows a "Decision Pathway" vertical timeline with 4 steps (Receipt Uploaded, AI Extraction, Policy Check, Final Decision) that update in real-time as SSE events arrive -- each step shows a timestamp, status badge (Completed/In Progress/Pending), and the AI Extraction step shows the confidence score
2. The bottom of the Chat Page shows a horizontal Submission Summary section with session total, item count, and a table of processed receipts (Merchant, Date, Amount, Status) -- replacing the current right-panel summary
3. Chat messages use updated styling with bot/user avatars, rounded message bubbles, and timestamps matching the Stitch design
4. A user providing any format of employee ID (EMP-042, 1010736, or any alphanumeric string) has it correctly captured and persisted to the database -- the ID is extracted server-side from the user message, not by the LLM
5. All existing tests pass without regression; new unit tests cover the employee ID extraction logic

**Plans:** 4 plans

Plans:
- [x] 06.2-01-PLAN.md -- TDD: Employee ID server-side extraction module + wire into chat flow and submitClaim pipeline, remove EMP-001 from system prompt
- [x] 06.2-02-PLAN.md -- Decision Pathway sidebar: partial template with 4 steps, SSE pathway-update events, replace right-panel summary
- [x] 06.2-03-PLAN.md -- Bottom Submission Table: horizontal claims table from DB, session total card, SSE real-time row updates
- [x] 06.2-04-PLAN.md -- Branding refresh (Expense AI logo, sidebar nav reduction) + message bubble styling (Analysis Complete badge, timestamps, quick-reply buttons)

---

### Phase 6.3: User Authentication + Dual Roles + Reviewer Pages

**Goal:** The application requires authentication before accessing any page. A login page matching the Stitch design authenticates users with username/password. Two roles (user/reviewer) control route access and sidebar visibility. The Dashboard, Audit Log, and Claim Review pages are fully implemented with live data, HTMX partial swaps, and approve/reject workflows. Intake agent processing writes audit_log entries for the decision timeline. This phase absorbs the scope of Phase 8 (Dashboard + Audit Log) and Phase 9 (Claim Review).

**Depends on:** Phase 6.2

**Requirements:** AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, AUDT-01, AUDT-02, AUDT-03, AUDT-04, AUDT-05, AUDT-06, AUDT-07, REVW-01, REVW-02, REVW-03, REVW-04, REVW-05, REVW-06, REVW-07, REVW-08

**Success Criteria** (what must be TRUE when Phase 6.3 completes):
1. Visiting any page while unauthenticated redirects to `/login`, which renders the Stitch login design with username/password fields matching the dark theme
2. Logging in as a user role redirects to `/` (Chat Page); logging in as a reviewer role redirects to `/dashboard`
3. Users cannot access `/dashboard`, `/audit`, or `/review` pages; reviewers can access all pages
4. Sidebar shows exactly 2 entries: Claims (both roles) and Review (reviewer only)
5. Dashboard shows 3 KPI cards with live counts, claims table with dual navigation (row -> review, audit icon -> audit), and AI Efficiency chart
6. Audit Log page shows list-detail layout with HTMX claim selection, decision timeline with 4 steps, confidence scores, and policy references
7. Claim Review page shows receipt with zoom, extracted fields, flag reason, AI insight, and working approve/reject with audit logging
8. Intake agent writes audit_log entries for receipt upload, AI extraction, and policy check steps
9. Logging out clears the session and redirects to `/login`; all existing tests pass without regression

**Plans:** 6 plans

Plans:
- [x] 06.3-01-PLAN.md -- Auth foundation: Users table + migration + seed data, User model, auth middleware, login/logout endpoints, login template (Stitch design), auth tests
- [x] 06.3-02-PLAN.md -- Sidebar + role routing: Update base.html to 2-entry sidebar, role-based route protection, profile dropdown with logout
- [x] 06.3-03-PLAN.md -- Dashboard page: KPI API endpoints, claims table with dual navigation, AI Efficiency chart, Stitch template
- [x] 06.3-04-PLAN.md -- Audit Log page: Timeline API endpoints, list-detail template with HTMX, decision timeline, confidence scores, intelligence insights
- [x] 06.3-05-PLAN.md -- Claim Review page: Claim detail + decision API endpoints, receipt zoom, extracted fields, approve/reject with audit logging
- [x] 06.3-06-PLAN.md -- Intake audit logging: Buffer + flush pattern for audit_log entries during intake agent processing

---

### Phase 8: Compliance, Fraud + Advisor Agents

**Goal:** The three post-submission agents are fully implemented with LLM-powered reasoning, replacing the current stubs. After a claim is submitted via the Intake Agent, the Compliance Agent audits the claim against company policies (using RAG search), the Fraud Agent detects duplicates and anomalies (amount thresholds, frequency patterns), and the Advisor Agent synthesizes both reports to route the claim: auto-approve (clean), return-to-claimant (violations), or escalate-to-reviewer (suspicious). Each agent writes structured findings to ClaimState and audit_log entries for the decision timeline. The claim status is updated in the database based on the Advisor's routing decision.

**Depends on:** Phase 6.3

**Requirements:** ORCH-03, ORCH-04, ORCH-05, ORCH-06, ORCH-07, APRV-01, APRV-02, APRV-03, REVW-09

**Success Criteria** (what must be TRUE when Phase 8 completes):
1. After a claim is submitted, the Compliance Agent queries the RAG MCP server with the claim's category and amount, evaluates policy rules, and writes a structured compliance report to `ClaimState.complianceFindings` with pass/fail status, violated rules (if any), and policy references
2. After a claim is submitted, the Fraud Agent checks for duplicate claims (same employee + merchant + date), flags anomalous amounts exceeding category thresholds, and writes a structured fraud report to `ClaimState.fraudFindings` with risk score, flags raised, and supporting evidence
3. Compliance and Fraud agents execute in parallel (same LangGraph superstep) -- verifiable by checking that both nodes run in the same superstep via graph execution logs
4. The Advisor Agent receives both compliance and fraud reports, synthesizes a decision, and routes the claim: status "approved" (clean claim, no violations, low risk), status "returned" (policy violations found), or status "escalated" (fraud flags raised or mixed signals requiring human review)
5. The Advisor Agent writes a contextual insight note to ClaimState that is displayed on the Claim Review page's AI Insight card (REVW-09)
6. Each agent writes audit_log entries for its processing step, visible in the Audit Log decision timeline
7. The claim status in the database is updated to match the Advisor's routing decision (approved/returned/escalated)
8. All existing tests pass without regression; new unit tests cover each agent's decision logic with at least 3 scenarios per agent (clean claim, violation, suspicious)

**Plans:** 5 plans

Plans:
- [x] 08-01-PLAN.md -- Foundation: ClaimState expansion (4 fields), Alembic migration 006 (4 columns), ORM model update, shared agent utilities (extractJsonBlock, buildAgentLlm), intake node fix (violations + dbClaimId)
- [x] 08-02-PLAN.md -- Compliance Agent: Evaluator pattern node (RAG query + LLM verdict), system prompt, audit logging, 4+ unit tests
- [x] 08-03-PLAN.md -- Fraud Agent: Tool Call pattern node (3 DB queries + LLM reasoning), SQL injection fix, deterministic duplicate detection, system prompt, 5+ unit tests
- [x] 08-04-PLAN.md -- Advisor Agent: Reflection + Routing pattern node (ReAct with 3 tools), decision routing, DB status + findings persistence, email notifications, 6+ unit tests
- [x] 08-05-PLAN.md -- UI updates: Audit Log 7-step timeline with agent colors, Claim Review compliance/fraud cards, Dashboard status breakdown KPIs, approve/reject restricted to escalated claims

---

### Phase 8.1: Bug Fixes + UX Polish

**Goal:** Fix all bugs discovered during Phase 8 QA, restructure the claim status lifecycle, and polish the Claims page UX. The chat flow completes reliably (no silent hangs), the Decision Pathway accurately reflects the current processing step, claim statuses clearly distinguish AI vs human decisions, and the Claims page shows the user's own claim history.

**Depends on:** Phase 8

**Bugs in scope:**

| Bug | Summary | Status |
|-----|---------|--------|
| BUG-016 | Advisor raw JSON leaks into chat + claim stuck PENDING | Resolved (commit `6f4ac6a`) |
| BUG-017 | Audit Log page crashes on dict confidence value | Resolved (commit `5c89708`) |
| BUG-018 | Duplicate intake audit entries | Resolved (commit `3d75e1b`) |
| BUG-019 | Advisor silent failure — claim stuck PENDING | Resolved (commit `7f231be`) |
| BUG-020 | Receipt image NULL in database | Resolved (ContextVar injection) |
| BUG-021 | Intelligence cards invisible on dark theme | Resolved (card restyling) |
| BUG-022 | Approval badge wrong for reviewer-approved claims | Resolved (approvedBy check) |
| BUG-023 | Claim Review shows auto-approved for escalated claims | Resolved (approvedBy check) |
| BUG-024 | Decision Pathway shows premature COMPLETED status | Open |
| BUG-025 | Chat stuck at Analyzing with no error toast on LLM timeout | Open |
| BUG-026 | Post-submission agents block SSE stream — should run in background | Open |

**Feature changes in scope:**

1. **Claim status lifecycle restructure** — Replace flat statuses with granular lifecycle:
   ```
   draft -> pending -> ai_reviewed -> ai_approved / ai_rejected / escalated -> manually_approved / manually_rejected
   ```
   - `draft`: claim being worked on (pre-submission)
   - `pending`: submitted to DB, awaiting AI pipeline
   - `ai_reviewed`: compliance + fraud agents completed analysis
   - `ai_approved`: advisor auto-approved (clean claim)
   - `ai_rejected`: advisor rejected (policy violations)
   - `escalated`: advisor escalated for human review
   - `manually_approved`: reviewer approved escalated claim
   - `manually_rejected`: reviewer rejected escalated claim
   - Impacts: advisor node, review router, dashboard KPIs, all templates, all tests (~65 locations)

2. **Show draft status in Claims page submission table** — Display the in-progress claim as "draft" in the bottom table while user is working on it

3. **Claims page "My Claims" section** — Add "My Claims" header to the submission table, filter to show only the logged-in user's historical claims (descending order), move table to the left, remove the "Current Report" summary card

4. **Claim Review page layout restructure** — Move all intelligence cards (currently in sidebar) to stack horizontally in rows below the receipt/extracted fields section. Cards display in a responsive grid below the receipt details.

5. **Rename "Flag Reason" to "Intake Agent Findings"** — This card shows extraction confidence scores per field with green highlighting for high confidence values. Replaces the current flag reason display with a confidence-focused view of the VLM extraction output.

6. **New "Conversational Audit" card** — Added below Intake Agent Findings. Shows the Intake agent's observations from the chat conversation (policy violations, soft cap breaches, etc.) paired with the user's justification/response. Captures the back-and-forth between agent and claimant during submission.

7. **Decouple post-submission agents from SSE stream** — After intake submits the claim to DB, the chat immediately returns the submission response to the user (done event fires). Compliance, fraud, and advisor agents run asynchronously in the background (e.g., `asyncio.create_task`). The user does not wait for post-submission processing. Claim Review page shows results when ready. This replaces the current blocking graph execution where the SSE stream waits for the full pipeline (`intake -> compliance || fraud -> advisor -> END`).

**Additional fixes (not bug-numbered):**
- Global error toast system added to `base.html` (catches SSE, HTMX, JS errors)
- SSE stream try-except wrapper in `chat.py` (errors surface to UI instead of silent death)

**Success Criteria:**
1. A receipt upload + full claim submission flow completes without hanging — if the LLM times out, the user sees an error toast within 60 seconds
2. The Decision Pathway only marks steps as COMPLETED after the corresponding tool actually executes in the current agent run (no premature completion from stale state)
3. All Claim Review intelligence cards (Compliance, Fraud, AI Insight) are visually consistent with the Flag Reason card styling on the dark theme
4. Any server-side error during SSE streaming surfaces as a red toast notification in the UI — no silent failures
5. Claim statuses in the DB, UI badges, and KPI cards use the new 8-status lifecycle — no references to old "approved"/"rejected" statuses remain
6. The submission table at the bottom of the Claims page shows "My Claims" header, only the logged-in user's claims (filtered by employee_id), ordered by most recent first, with no "Current Report" card
7. In-progress claims appear as "draft" in the submission table
8. Claim Review page shows all intelligence cards (Intake Agent Findings, Conversational Audit, Compliance, Fraud, AI Insight) stacked horizontally in rows below the receipt details — not in a sidebar
9. "Intake Agent Findings" card displays per-field extraction confidence scores with green color for high confidence
10. "Conversational Audit" card shows agent observations (policy violations, soft cap breaches) alongside user justifications from the intake conversation

**Plans:** 4 plans

Plans:
- [ ] 08.1-01-PLAN.md -- Status lifecycle restructure: 8-state model (draft/pending/ai_reviewed/ai_approved/ai_rejected/escalated/manually_approved/manually_rejected) across advisor node, review router, dashboard, all templates, tests
- [ ] 08.1-02-PLAN.md -- Background processing + bug fixes: Decouple post-submission agents from SSE (BUG-026), LLM timeout config (BUG-025), asyncio.create_task for compliance/fraud/advisor
- [ ] 08.1-03-PLAN.md -- Draft claim + My Claims table: Create draft DB row on first message, employee_id-filtered "My Claims" section, 7-column table, click-to-audit navigation
- [ ] 08.1-04-PLAN.md -- Claim Review card restructure: Move cards from sidebar to 2-col grid below receipt, new Intake Agent Findings + Conversational Audit cards, Pending Review badges, BUG-024 fix

---

### Phase 8.2: Advisor Agent Refactor + Schema Alignment

**Goal:** The Advisor agent captures its actual LLM reasoning in `advisor_findings`, and the Review v2 page displays the real reasoning. Optionally, the Advisor is refactored from ReAct to a deterministic routing function.

**Depends on:** Phase 8.1

**Already done (this session):**
- `advisor_findings` JSONB column added (migration 007), ORM model updated, MCP DB server updated
- Fixed intakeFindings schema defined in v2 system prompt (confidenceScores, policyViolation, justification, remarks, conversion)
- Review v2 template created with Advisory Agent card showing advisor findings
- Review page parser updated to read `confidenceFlags` fallback for old claims
- Existing claims backfilled from audit_log

**Remaining items:**

1. **Capture LLM reasoning in advisor_findings** — The current `advisorFindings` dict is manually constructed from compliance/fraud summaries (not the LLM's actual response). Change to capture the LLM's reasoning text from `result["messages"]` and store it in the `advisor_findings` JSONB column.

2. **Rename `aiInsight` to `submissionHistory`** — The variable name suggests AI involvement but it's a plain SQL COUNT query. Rename across router and templates.

3. **Promote Review v2 as default** — Rename current `/review/{claimId}` route to `/review-archived/{claimId}` (template `review_archived.html`). Rename `/review-v2/{claimId}` to `/review/{claimId}` (template `review.html`). Update dashboard link in `claims_table_rows.html`.

4. **Intake Agent Findings — show per-field confidence scores** — The card currently shows only avg confidence and lowest field. Add a breakdown of all field confidence scores (merchant, date, totalAmount, currency, etc.) below the avg bar. Data is already in `intakeAgentFindings.scores` dict — just needs template rendering.

5. **Rename "Extracted Entity Data" to "Extracted Claim Information"** — Update card title in review_v2.html. Show additional DB fields: line_items, original_currency, original_amount, converted_amount_sgd, receipt_number, exchange rate, submission date.

6. **Fix category always showing "General"** — Category is extracted from `line_items` JSON (looks for a `category` key), but line_items contains actual receipt items (`[{description, amount}]`), not a category field. No `category` column exists on claims or receipts. Fix: add `category` to the mandatory intakeFindings schema, add a `category` column to claims table (migration), add system prompt instruction for the intake agent to infer category from receipt content (must be one of: meals, transport, accommodation, office_supplies, general — matching policy document categories), have submitClaim write it to the column.

7. **New "Manage" page** — Implement a new page at `/manage` for claim management. Pull UI design from Stitch MCP screen "Manage Claims". Wire route, template, and sidebar nav link.

8. **New "Analytics" page** — Implement a new page at `/analytics` for approver analytics/dashboard. Pull UI design from Stitch MCP screen "Enhanced Approver Dashboard". Wire route, template, and sidebar nav link.

**Success Criteria:**
1. The Advisory Agent card on Review v2 displays the LLM's actual reasoning text, not a copy of compliance/fraud summaries
2. `aiInsight` renamed to `submissionHistory` across all files
3. `/review/{claimId}` serves the structured layout (formerly v2), old template deleted (archived route not needed)
4. `/manage` and `/analytics` pages render matching their Stitch designs
5. All existing tests pass

**Plans:** 3 plans

Plans:
- [x] 08.2-01-PLAN.md -- Review page overhaul: advisor LLM reasoning capture, aiInsight->submissionHistory rename, promote v2 as default, per-field confidence bars, Extracted Claim Information card
- [x] 08.2-02-PLAN.md -- Category inference pipeline: migration 008, ORM update, system prompt category classification, submitClaim wiring, MCP DB server
- [x] 08.2-03-PLAN.md -- Manage + Analytics pages: new reviewer-only pages with filters/bulk actions/KPIs, sidebar nav update, category display fix

---

### Phase 10: Browser E2E Tests

**Goal:** A Playwright test suite covers the happy path through all 4 pages and one escalation path -- all tests use sentinel elements and `waitForSelector` (never `waitForTimeout`), run against a live uvicorn server in a background thread, and pass reliably in CI.

**Depends on:** Phase 8

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
v2.0 phases execute in order: 6 -> 7 -> 6.1 -> 6.2 -> 6.3 -> 8 -> 8.1 -> 8.2 -> 10

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 6. FastAPI Scaffold + Static Shell | 3/3 | Complete (v2 redo) | 2026-04-02 |
| 7. SSE Streaming + Full Chat Page | 3/3 | Complete | 2026-04-02 |
| 6.1. Model Upgrade + UX Fixes | 2/2 | Complete | 2026-04-04 |
| 6.2. Chat UI Refresh + Employee ID Fix | 4/4 | Complete | 2026-04-05 |
| 6.3. User Auth + Dual Roles + Reviewer Pages | 6/6 | Complete | 2026-04-05 |
| 8. Compliance, Fraud + Advisor Agents | 5/5 | Complete | 2026-04-06 |
| 8.1. Bug Fixes + UX Polish | 0/4 | In progress | -- |
| 8.2. Advisor Refactor + Schema Alignment | 3/3 | Complete | 2026-04-08 |
| 10. Browser E2E Tests | 0/2 | Not started | -- |

**v2.0 total:** 26/32 plans complete

**v1.0 (archived):** 24/26 plans complete (see MILESTONES.md)
