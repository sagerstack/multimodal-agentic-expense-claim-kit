# Requirements: Agentic Expense Claims v2.0

**Defined:** 2026-03-30
**Core Value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes — now through a custom multi-page web application

## v2.0 Requirements

Requirements for the UX redesign milestone. Each maps to roadmap phases.

### UI Foundation

- [x] **UIFN-01**: FastAPI application replaces Chainlit as the web server, serving all 4 pages via Jinja2 templates
- [x] **UIFN-02**: Shared base template (`base.html`) with sidebar navigation, top bar, and "Neon Nocturne" dark theme matching Stitch designs
- [x] **UIFN-03**: Tailwind v3 build pipeline via pytailwindcss (not CDN) for production-ready CSS
- [x] **UIFN-04**: HTMX 2.0.8 + SSE extension 2.2.4 loaded on all pages for dynamic interactions
- [x] **UIFN-05**: Alpine.js v3 loaded on all pages for client-side reactive state (upload progress, panel toggles, zoom)
- [x] **UIFN-06**: Material Symbols icons and Google Fonts (Manrope, Inter) loaded matching Stitch designs
- [x] **UIFN-07**: Active page indicator in sidebar navigation highlights the current page
- [x] **UIFN-08**: System status indicator in sidebar shows service health (intelligence pulse animation)
- [x] **UIFN-09**: Docker Compose `app` service updated to run FastAPI via uvicorn instead of Chainlit
- [x] **UIFN-10**: SessionMiddleware for per-conversation state (thread_id, claim_id) without authentication

### V1 Migration (Regression)

- [ ] **MIGR-01**: All v1.0 Intake Agent capabilities (VLM extraction, policy validation, currency conversion, claim submission, human-in-the-loop) work through the new FastAPI UI
- [x] **MIGR-02**: LangGraph graph invocation and checkpointer lifecycle managed via FastAPI lifespan (singleton, not per-session)
- [ ] **MIGR-03**: Receipt image upload via new UI stores base64 in imageStore and triggers VLM extraction identically to v1.0
- [ ] **MIGR-04**: SSE streaming delivers token-by-token AI responses to the chat interface matching v1.0 streaming behavior
- [ ] **MIGR-05**: LangGraph interrupt/resume for human-in-the-loop clarification works through the new chat UI (askHuman tool)
- [ ] **MIGR-06**: Thinking panel displays Type A (agent reasoning) and Type B (QwQ reasoning tokens) interleaved with tool call summaries
- [ ] **MIGR-07**: QwQ-32B model with reasoning tokens, temperature settings, and fallback behavior preserved from v1.0
- [ ] **MIGR-08**: Schema-driven intake prompt with getClaimSchema tool works identically to v1.0
- [x] **MIGR-09**: ConversationRunner (headless E2E) continues working after migration — backend is unchanged
- [x] **MIGR-10**: All 54 existing unit/integration tests pass without modification

### Chat Page (Page 1)

- [ ] **CHAT-01**: SSE-streamed AI responses display token-by-token in the chat message area
- [ ] **CHAT-02**: Drag-and-drop receipt image upload with inline preview in chat thread
- [ ] **CHAT-03**: Visible AI "thinking" state with intelligence pulse animation during processing
- [ ] **CHAT-04**: Clarification prompts from LangGraph interrupt display in chat and pause input until answered
- [ ] **CHAT-05**: Confirm/Edit quick-reply buttons appear after extraction for binary confirmations
- [ ] **CHAT-06**: Submission Summary right panel shows current total, item count, category breakdown
- [ ] **CHAT-07**: Batch details list below summary shows individual receipt items in current session
- [ ] **CHAT-08**: Warning/flags count surfaces in summary panel when policy violations exist
- [ ] **CHAT-09**: Thinking panel with named step labels ("Extracting fields...", "Checking policy...", "Converting currency...")
- [ ] **CHAT-10**: Inline per-field confidence scores displayed in extraction response (merchant: 99%, date: 72%)
- [ ] **CHAT-11**: Policy violations show specific cited clause in chat response ("Exceeds SUTD meal cap per Section 3.1")

### Approver Dashboard (Page 2)

- [ ] **DASH-01**: KPI cards display Total Pending, Auto-Approved, and Escalated claim counts
- [ ] **DASH-02**: Recent Claims table shows claim number, employee, category, amount, and status with color-coded badges
- [ ] **DASH-03**: Clicking a claim row navigates to the Claim Review page for that claim
- [ ] **DASH-04**: Status filter buttons narrow the claims table by status (Pending, Approved, Escalated)
- [ ] **DASH-05**: AI Efficiency panel shows auto-approval rate metric (static value acceptable for stub agents)

### Audit & Transparency Log (Page 3)

- [ ] **AUDT-01**: Left panel lists claims with claim number, status badge, and amount, ordered by most recent
- [ ] **AUDT-02**: Selecting a claim shows decision pathway timeline in right panel with vertical step nodes
- [ ] **AUDT-03**: Each timeline step shows timestamp, step name, and outcome (Upload → AI Extraction → Policy Check → Final Decision)
- [ ] **AUDT-04**: AI Extraction step displays confidence score from VLM extraction
- [ ] **AUDT-05**: Policy Check step shows matched policy reference with "View Policy Reference" link
- [ ] **AUDT-06**: Claim detail header shows claim number, description, and amount
- [ ] **AUDT-07**: "View Receipt" button displays the original receipt image for the selected claim

### Claim Review / Escalation (Page 4)

- [ ] **REVW-01**: Receipt image displayed in left column for reviewer inspection
- [ ] **REVW-02**: Extracted fields shown as read-only labeled cards (merchant, date, amount, category)
- [ ] **REVW-03**: Flag reason card shows AI explanation and confidence score for why claim was escalated
- [ ] **REVW-04**: Approve and Reject action buttons with clear visual distinction
- [ ] **REVW-05**: Reviewer notes textarea for documenting decision rationale
- [ ] **REVW-06**: Pre-defined rejection reason radio buttons (Duplicate, Incomplete, Policy violation)
- [ ] **REVW-07**: Previous/Next navigation between escalated claims without returning to dashboard
- [ ] **REVW-08**: Receipt image zoom controls via Alpine.js (zoom in/out buttons, CSS transform)

### SSE Streaming Architecture

- [ ] **STRE-01**: SSE event taxonomy defined with distinct event types (token, thinking_start, step_name, step_content, thinking_done, done)
- [ ] **STRE-02**: FastAPI SSE endpoint uses native EventSourceResponse to stream LangGraph astream_events output
- [ ] **STRE-03**: POST + SSE decoupled via asyncio.Queue (form POST triggers graph, SSE endpoint reads queue)
- [ ] **STRE-04**: SSE disconnect cleanup cancels running graph tasks when client disconnects
- [ ] **STRE-05**: HTMX sse-connect and sse-swap correctly wired on chat container element

### Browser E2E Testing

- [ ] **TEST-01**: Playwright test infrastructure with live_server fixture (uvicorn in background thread)
- [ ] **TEST-02**: E2E test: claimant uploads receipt, sees extraction, confirms, submits claim through chat page
- [ ] **TEST-03**: E2E test: dashboard displays claim counts and recent claims table
- [ ] **TEST-04**: E2E test: audit log shows decision timeline for a submitted claim
- [ ] **TEST-05**: E2E test: claim review page displays escalated claim with approve/reject actions

## Future Requirements

Deferred to later milestones. Tracked but not in current roadmap.

### Agents (v3.0)

- **ORCH-03**: Compliance Agent implements Evaluator pattern for post-submission policy audit
- **ORCH-04**: Fraud Agent implements Tool Call pattern for post-submission duplicate detection
- **ORCH-05**: Advisor Agent implements Reflection + Routing pattern for decision synthesis
- **ORCH-06**: Compliance and Fraud agents execute in parallel (LangGraph fan-out)
- **ORCH-07**: Advisor Agent waits for both Compliance and Fraud before synthesizing
- **APRV-01**: Advisor routes clean claims to auto-approve
- **APRV-02**: Advisor routes violations to return-to-claimant
- **APRV-03**: Advisor routes suspicious claims to human reviewer
- **APRV-04**: Claim status updated in database by routing decision

### Email Notifications (v3.0)

- **NOTF-01**: Email to claimant when claim returned with correction instructions
- **NOTF-02**: Email to reviewer when claim escalated
- **NOTF-03**: Email to claimant when claim approved or rejected

### Dashboard Enhancements (v2.x)

- **DASH-06**: Auto-Approval Threshold display/editing
- **DASH-07**: Weekly AI efficiency trend chart
- **DASH-08**: Per-row week-over-week delta badges on KPI cards

### Audit Log Enhancements (v2.x)

- **AUDT-08**: Download Log as JSON export
- **AUDT-09**: Intelligence pulse animation on active processing step
- **AUDT-10**: Anomaly Detection and Cost Benchmark bento cards

### Claim Review Enhancements (v2.x)

- **REVW-09**: AI Insight card with Advisor Agent contextual note
- **REVW-10**: Linked duplicate reference to original claim
- **REVW-11**: Return to Claimant action with email notification

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Light theme / theme toggle | Dark only this milestone — reduces scope |
| Mobile responsive design | Desktop only — Stitch designs are 1280px+ |
| WebSocket for chat | SSE sufficient, simpler architecture |
| React/Vue/SPA framework | HTMX + Alpine.js keeps stack Python-only |
| Authentication/authorization | Not needed for course demo |
| AWS/cloud deployment | Local-only for course project |
| Batch multi-receipt submission | Single claim per conversation, batch display is cosmetic |
| Real-time dashboard WebSocket feed | HTMX polling at 30s intervals sufficient |
| Full-text search in audit logs | Demo has 10-20 claims, filter by status sufficient |
| Multi-session chat history | Single session per page load |
| Export to CSV/PDF | JSON export only if implemented |
| Inline receipt image editing | Display only, no annotation |
| Comment threading with claimant | Notes are internal-only |
| Approver claim locking | Single approver assumed for demo |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| UIFN-01 | Phase 6 | Pending |
| UIFN-02 | Phase 6 | Pending |
| UIFN-03 | Phase 6 | Pending |
| UIFN-04 | Phase 6 | Pending |
| UIFN-05 | Phase 6 | Pending |
| UIFN-06 | Phase 6 | Pending |
| UIFN-07 | Phase 6 | Pending |
| UIFN-08 | Phase 6 | Pending |
| UIFN-09 | Phase 6 | Pending |
| UIFN-10 | Phase 6 | Pending |
| MIGR-02 | Phase 6 | Pending |
| MIGR-09 | Phase 6 | Pending |
| MIGR-10 | Phase 6 | Pending |
| STRE-01 | Phase 7 | Pending |
| STRE-02 | Phase 7 | Pending |
| STRE-03 | Phase 7 | Pending |
| STRE-04 | Phase 7 | Pending |
| STRE-05 | Phase 7 | Pending |
| MIGR-01 | Phase 7 | Pending |
| MIGR-03 | Phase 7 | Pending |
| MIGR-04 | Phase 7 | Pending |
| MIGR-05 | Phase 7 | Pending |
| MIGR-06 | Phase 7 | Pending |
| MIGR-07 | Phase 7 | Pending |
| MIGR-08 | Phase 7 | Pending |
| CHAT-01 | Phase 7 | Pending |
| CHAT-02 | Phase 7 | Pending |
| CHAT-03 | Phase 7 | Pending |
| CHAT-04 | Phase 7 | Pending |
| CHAT-05 | Phase 7 | Pending |
| CHAT-06 | Phase 7 | Pending |
| CHAT-07 | Phase 7 | Pending |
| CHAT-08 | Phase 7 | Pending |
| CHAT-09 | Phase 7 | Pending |
| CHAT-10 | Phase 7 | Pending |
| CHAT-11 | Phase 7 | Pending |
| DASH-01 | Phase 8 | Pending |
| DASH-02 | Phase 8 | Pending |
| DASH-03 | Phase 8 | Pending |
| DASH-04 | Phase 8 | Pending |
| DASH-05 | Phase 8 | Pending |
| AUDT-01 | Phase 8 | Pending |
| AUDT-02 | Phase 8 | Pending |
| AUDT-03 | Phase 8 | Pending |
| AUDT-04 | Phase 8 | Pending |
| AUDT-05 | Phase 8 | Pending |
| AUDT-06 | Phase 8 | Pending |
| AUDT-07 | Phase 8 | Pending |
| REVW-01 | Phase 9 | Pending |
| REVW-02 | Phase 9 | Pending |
| REVW-03 | Phase 9 | Pending |
| REVW-04 | Phase 9 | Pending |
| REVW-05 | Phase 9 | Pending |
| REVW-06 | Phase 9 | Pending |
| REVW-07 | Phase 9 | Pending |
| REVW-08 | Phase 9 | Pending |
| TEST-01 | Phase 10 | Pending |
| TEST-02 | Phase 10 | Pending |
| TEST-03 | Phase 10 | Pending |
| TEST-04 | Phase 10 | Pending |
| TEST-05 | Phase 10 | Pending |

**Coverage:**
- v2.0 requirements: 61 total (header previously stated 54 — recount corrected)
- Mapped to phases: 61
- Unmapped: 0

**Note on count:** The original header said 54 requirements. The actual enumeration yields 61: UIFN (10) + MIGR (10) + CHAT (11) + DASH (5) + AUDT (7) + REVW (8) + STRE (5) + TEST (5) = 61. All 61 are mapped.

---
*Requirements defined: 2026-03-30*
*Last updated: 2026-03-30 — traceability populated by roadmapper (v2.0 phases 6–10)*
