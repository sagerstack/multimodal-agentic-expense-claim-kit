# Feature Research

**Domain:** AI-powered expense claims web application — multi-page custom UI
**Researched:** 2026-03-30
**Confidence:** HIGH
**Scope:** NEW milestone research only. This file covers the 4 custom web pages being added in v2.0. Features already built (VLM extraction, policy RAG, currency conversion, LangGraph pipeline, PostgreSQL persistence) are not re-researched here.

---

## Page 1: AI Chat Submission

The primary claimant-facing page. Replaces Chainlit with a custom FastAPI + HTMX interface. Chat is the interaction model; receipt upload and data display are panels alongside it.

### Table Stakes

Features users assume exist. Missing these = submission feels broken or untrustworthy.

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|--------------------|
| **SSE-streamed AI responses** | Users expect token-by-token streaming from AI chat. Static "wait and load" feels broken in 2026. | MEDIUM | LangGraph graph invocation via SSE endpoint; FastAPI EventSourceResponse |
| **Drag-and-drop receipt upload** | Industry standard for file upload since 2018. Every modern expense tool (Expensify, Ramp, Concur) leads with receipt photo capture. Users expect to drop a file, not navigate a file picker. | MEDIUM | Existing imageStore; multipart POST to FastAPI |
| **Inline image preview in chat** | After dropping a receipt, users expect to see it rendered in the message thread, not just a filename. Establishes that the upload succeeded. | LOW | Base64 from imageStore |
| **Visible AI "thinking" state** | During processing (VLM extraction, policy check), users need feedback that something is happening. A pulsing indicator or "Analyzing..." message is baseline. The design shows an `intelligence-pulse` CSS animation. | LOW | SSE event type: `thinking` vs `message` |
| **Clarification prompt display** | When the Intake Agent triggers a LangGraph interrupt (low-confidence field, policy question), the question must appear in chat and pause the input field until answered. Users expect a clear ask-and-answer pattern. | MEDIUM | Existing interrupt/resume mechanism from v1.0 |
| **Confirm/Edit quick-reply buttons** | After extraction, offering "Yes, looks correct" and "Edit details" buttons in the chat is the dominant pattern across AI expense tools (Expensify Concierge, Emburse). Avoids free-text for binary confirmations. | LOW | HTMX hx-post targeting chat endpoint |
| **Submission Summary right panel** | Shows current session total, item count, and category breakdown. Users need a running tally — submitting without visibility on what's being claimed feels risky. The Stitch design has this as a right-column panel (`Submission Summary`). | MEDIUM | Derived from extractedReceipt in ClaimState; refreshed via HTMX polling or SSE |
| **Batch details list** | Below the summary, the individual items in the current session (e.g., "Starbucks - $45.20 - Apr 22"). Users expect to see what they've submitted so far in this session. | LOW | ClaimState receipts list |
| **Warning/flags count in summary** | If any item has a policy flag, the summary panel must surface the count ("1 Flagged"). Users who don't see this will be surprised at rejection. | LOW | violations from ClaimState |

### Differentiators

Features that go beyond baseline and make the demo memorable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Thinking panel with step labels** | Instead of a generic spinner, showing step names ("Extracting fields...", "Checking policy...", "Converting currency...") makes the multi-agent architecture visible. This is the course project's research contribution. | MEDIUM | SSE event names map to LangGraph node names; each node emits a named event |
| **Completion progress bar in summary** | The Stitch design shows "65% Complete" with a progress bar in the summary panel. Communicates that submission is a multi-step flow with a defined end, not an open-ended conversation. | LOW | Computed from claimSubmitted state and steps completed |
| **Inline field confidence display** | Showing per-field confidence (e.g., merchant: 99%, amount: 94%, date: 72%) directly in the chat response ties the AI output to the underlying evidence. This is the demo differentiator — users see *why* the AI is asking for clarification on low-confidence fields. | MEDIUM | extractedReceipt.confidence_scores passed through SSE stream |
| **Policy citation in chat response** | When a violation is found, the chat message names the specific policy clause ("Exceeds SUTD meal cap: $30.00/person per Section 3.1"). Users see the rule, not just the rejection. | LOW | violations[].clause already in ClaimState from v1.0 |
| **Voice and camera quick-actions** | The Stitch design shows "Capture", "Voice", and "Recent" shortcuts below the input. These signal intent (mobile-style capture) even if voice isn't implemented. Capture can link to the file picker as a fallback. | LOW | Capture: triggers file input click; Voice/Recent: deferred or non-functional stubs |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **WebSocket instead of SSE** | WebSocket adds bidirectional complexity, requires connection lifecycle management, and is harder to debug. SSE is sufficient for unidirectional streaming from server to client. HTMX has a native SSE extension. Out of scope per PROJECT.md. | Use FastAPI EventSourceResponse + HTMX `hx-ext="sse"` |
| **Batch submission workflow** | The Stitch design shows batch details, but implementing true batch (multi-receipt, single claim) adds state complexity that isn't core to the agent demonstration. The batch display in the summary panel is cosmetic — showing it as a list is table stakes, but wiring multi-receipt batch submission is scope creep. | Show batch as current session list. Submit one claim per conversation. |
| **Real-time input validation as-you-type** | Validating free text against policy as the user types (before submitting) adds latency and LLM cost with marginal UX benefit. The AI does this after upload, not before. | Validate on submit, not on keypress |
| **Auto-scroll suppression** | Chat UIs that scroll to the newest message but allow the user to scroll up mid-stream, then jump back — this is surprisingly complex to implement correctly. Simple auto-scroll to bottom on new message is sufficient. | Always scroll to bottom on new AI message |
| **Multi-session history in chat** | Showing previous conversations in the chat panel (like a ChatGPT sidebar) requires conversation management UI that's orthogonal to the demo. | Single session per page load. History lives in the Claims History page (if built). |

---

## Page 2: Approver Dashboard

The primary approver-facing page. Shows KPI cards, pending claims, AI efficiency metrics, and a filterable claims table.

### Table Stakes

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|--------------------|
| **KPI cards: Total Pending, Auto-Approved, Escalated** | Every approval dashboard in every enterprise system starts with a summary row of key counts. These three metrics from the Stitch design (142 pending, 1,204 auto-approved, 18 escalated) are the minimum "situational awareness" an approver needs before doing anything else. Missing these = approver has no context. | LOW | SQL count queries against claims table by status |
| **Recent Claims table with status column** | A list of recent claims with employee name, category, amount, and status (Pending / Auto-Approved / Escalated) is the core workhorse of the page. Approvers scan this to prioritize. | MEDIUM | JOIN query: claims + receipts |
| **Claim row navigation to review page** | Clicking a row navigates to the Claim Review page (Page 4) for that specific claim. Without this, the dashboard is a dead end. The Stitch design uses an arrow button (`arrow_forward_ios`) on each row. | LOW | HTMX `hx-get` or anchor href to `/claims/{id}/review` |
| **Status filter button** | Approvers need to narrow to "Pending only" or "Escalated only". The Stitch design shows a "Filters" button. A basic status filter is table stakes — without it, a mixed list is overwhelming. | LOW | HTMX form with filter param triggering hx-get to refresh table |
| **AI efficiency metric panel** | The Stitch design dedicates a column to an "AI Efficiency" bar chart (showing auto-approval rate trend by week). Approvers need to know if the AI is performing correctly — if auto-approval suddenly drops, something is wrong. | MEDIUM | Query auto-approved vs total counts by week; rendered as server-side SVG or simple CSS bars |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Auto-Approval Threshold toggle** | The Stitch design shows an "Auto-Approval Threshold: $500.00" control in the header with a toggle switch. This is a compelling demo feature — the approver can see and adjust the threshold that drives AI routing. Makes the AI decision boundary visible and controllable. | MEDIUM | Threshold stored in config or DB; updating it via HTMX PATCH endpoint; Advisor Agent reads this value |
| **Weekly efficiency trend chart** | The bar chart in the "AI Efficiency" panel (showing Mon-Sat bars) communicates that the system is improving over time. This is the course project's multi-agent value story in a single visual. | MEDIUM | Simple CSS bar chart driven by query results; no JS charting library needed |
| **Stacked approver avatars with "Agents monitoring" caption** | The Stitch design shows 2 avatar initials under the efficiency panel with "2 Agents monitoring AI accuracy". For a demo this signals the human-in-the-loop oversight model explicitly. | LOW | Static or session-based; no real agent tracking needed |
| **Per-row WoW delta badge** | The "+12% vs last wk" badge on the Total Pending KPI card is a differentiator — it contextualizes the absolute number. Static KPI counts are less useful than trending counts. | LOW | Previous week count query; percentage computed in Python |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Full BI dashboard (charts for everything)** | Building chart components for all metrics (spend by category, by department, by week) is scope creep. The course demo needs one compelling AI metric, not a full finance dashboard. | One AI efficiency bar chart. Everything else is counts in KPI cards. |
| **Bulk approve/reject actions** | Batch action checkboxes on table rows add state complexity (select all, partial select, confirm dialog). Not needed when the demo has a handful of claims. | Single-row navigation to review page only |
| **Real-time claim feed with WebSocket** | Live-updating the dashboard as new claims arrive is impressive but complex. The demo approver session is controlled — HTMX polling at 30s intervals is sufficient. | HTMX `hx-trigger="every 30s"` on the claims table section |
| **Export to CSV** | The Stitch design shows an "Export" button. Don't wire this up. CSV generation adds a download endpoint with no demo value. | Placeholder button that does nothing, or remove entirely |

---

## Page 3: Audit and Transparency Log

The audit/compliance page. Shows a filterable list of decided claims on the left, and a detailed decision pathway for a selected claim on the right.

### Table Stakes

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|--------------------|
| **Claim list (left panel) with status badges** | A list of recent claim decisions with claim number, claimant name, status badge (Approved / Rejected / Escalated), and amount. Auditors need to select a claim to inspect. Without this list, the page has no navigation. | LOW | Claims query ordered by updated_at DESC |
| **Decision pathway timeline (right panel)** | The core feature of the page. A vertical timeline showing each processing step: Upload -> AI Extraction -> Policy Check -> Final Decision, each with a timestamp and icon. This is the "explainability" story for the course project. | MEDIUM | audit_log table events mapped to timeline steps; existing audit_log table already captures state changes |
| **Per-step timestamps** | Each timeline node shows a timestamp (the Stitch design uses `font-mono` `10:42:01 AM` format). Auditors need to verify when decisions were made. | LOW | audit_log.timestamp |
| **AI extraction confidence score display** | The Stitch design shows a confidence score bar (`99.4%`) in the AI Extraction step. This is the evidence that the AI's extraction was reliable. Critical for auditors questioning AI decisions. | LOW | extractedReceipt.confidence_scores from claims table |
| **Policy citation with "View Policy Reference" link** | The Policy Check step shows "Matches: Travel Policy v4.2" with a clickable "View Policy Reference" text. Auditors need to verify *which* policy was applied. | LOW | violations[].clause + policy source from RAG; link can open the policy markdown file or a modal |
| **Claim detail header with claim number, description, amount** | At the top of the right panel: claim number, description ("International Travel - Tokyo Q3"), amount. Basic identification. | LOW | claims + receipts JOIN |
| **"View Receipt" action in detail header** | The Stitch design shows a "View Receipt" button. Auditors must be able to see the original receipt image alongside the audit trail. | LOW | Serve receipt image from stored path |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **"Download Log" button** | The Stitch design shows a "Download Log" button in the detail header. Exporting the decision trail as JSON or PDF is compelling for compliance demos — it shows the audit trail is exportable for external review. | LOW | FastAPI response with JSON dump of audit_log events for that claim_id |
| **Anomaly Detection and Cost Benchmark bento cards** | The Stitch design shows two bottom-row bento cards below the timeline: "Anomaly Detection" (flagged/clear) and "Cost Benchmark" (compares claim to historical average for that category). These make the Fraud Agent's output visible in the audit trail. | MEDIUM | Requires Fraud Agent output stored in audit_log or claims table; cost benchmark needs historical average query |
| **Clickable policy reference** | "View Policy Reference" as an actual link (opens policy markdown in modal or new tab) rather than dead text demonstrates that the AI's policy search is grounded in real documents. | LOW | Policy files in `src/agentic_claims/policy/` are accessible; FastAPI static route or modal |
| **Intelligence-pulse animation on active step** | While a claim is being processed (live), the current step node pulses. For a demo where claims are submitted live, this makes the pipeline visible in real time. | LOW | CSS pulse animation already in Stitch designs; SSE event triggers class swap via HTMX |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Full-text search across audit logs** | Full-text search with indexing is engineering overhead with no demo value. Auditors in the demo know which claim they're looking for. | Scroll/filter by status in the left panel. No search box. |
| **Log export in multiple formats (PDF, CSV, Excel)** | Multi-format export is scope creep. JSON is sufficient to demonstrate the audit trail is machine-readable. | One "Download Log" button that returns JSON |
| **Pagination with server-side sorting** | For a demo with 10-20 claims, pagination adds complexity with zero benefit. | Render all claims; scroll within the left panel. |
| **Immutable log enforcement** | True audit immutability (append-only, signed entries) is a compliance engineering concern beyond a course demo. | Insert-only audit_log table is sufficient. No deletion UI. Don't add update endpoints for audit rows. |

---

## Page 4: Claim Review (Escalation)

The page an approver sees after clicking a flagged/escalated claim. Focused on one claim: shows the receipt image, extracted fields, AI flag reason, and approve/reject/return actions.

### Table Stakes

| Feature | Why Expected | Complexity | Backend Dependency |
|---------|--------------|------------|--------------------|
| **Receipt image display** | The approver must see the original receipt to make an informed decision. The Stitch design shows a full receipt image in the left column with zoom-in/out controls. Without it, the approver is making a blind decision. | LOW | Serve image from stored path; `<img>` tag in template |
| **Extracted field display (read-only)** | Merchant, date, amount, category, submitter. The fields the AI extracted, shown as labeled read-only cards. Approvers need to verify what the AI captured. | LOW | claims + receipts JOIN; Jinja2 template rendering |
| **AI flag reason card** | The right panel shows "Flag Reason" with the AI's explanation and confidence score ("Duplicate receipt found in June 2024... AI Confidence: 98%"). This is the core feature — without it, the approver doesn't know why the claim was escalated. | LOW | Advisor Agent decision + Fraud Agent output stored in claims or audit_log table |
| **Approve and Reject action buttons** | The two primary actions. Must be impossible to miss. The Stitch design uses full-width buttons with strong color contrast (error red for Reject, secondary teal for Approve). | LOW | HTMX hx-post to `/claims/{id}/approve` or `/claims/{id}/reject` |
| **Reviewer notes textarea** | The approver must be able to add internal notes explaining their decision. Required for audit trail completeness — a naked approve/reject with no human reasoning is insufficient. | LOW | POST body includes notes field; audit_log records human decision + notes |
| **Rejection reason radio buttons** | Pre-defined rejection reasons (Duplicate submission, Incomplete receipt details, Policy violation: Alcohol) from the Stitch design. Forces structured rejection codes rather than free text only. Downstream reporting can bucket rejections. | LOW | Enum or hardcoded list in template; stored in audit_log |
| **Claim navigation (Previous / Next)** | The Stitch design shows Previous/Next navigation buttons at the bottom. When reviewing a queue of escalated claims, approvers need to move between them without returning to the dashboard. | LOW | Query: previous/next claim_id by escalated_at ordering |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **AI Insight card ("Luminous Intelligence Insight")** | The right panel bottom shows an AI-generated contextual note: "User Marcus Vance has a high accuracy rating (94%) across 128 previous submissions. This duplication may be an accidental resubmission..." This is the Advisor Agent's behavioral context surfaced to the human reviewer. It doesn't override the decision but informs it. | MEDIUM | Requires Advisor Agent to generate this text and store in claims.advisor_notes or audit_log; needs employee submission history query |
| **Confidence score on page subtitle** | The Stitch page subtitle reads "AI extraction confidence score: 42%." — the overall confidence is surfaced at the page header level, not buried. Approvers immediately know how reliable the AI extraction was before reviewing details. | LOW | extractedReceipt overall confidence (min or average of field scores) |
| **Linked duplicate reference** | In the flag reason, "#EXP-88120" is clickable/underlined, linking to the original claim that was duplicated. Approvers can verify the duplicate without leaving the context. | LOW | Fraud Agent stores matched_claim_id; render as link to that claim's audit detail |
| **Receipt image zoom controls** | The Stitch design shows zoom-in/out buttons on the receipt image. Approvers reviewing a blurry or small receipt need to zoom. Alpine.js manages zoom state locally — no server round-trip. | LOW | Alpine.js x-data with zoom level; CSS transform: scale() |

### Anti-Features

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Inline receipt image editing** | Some tools allow annotating or redacting receipt images. This is out of scope and requires a canvas/image library. | Display only. No editing. |
| **"Return to Claimant" as a third action** | The Stitch design only shows Approve and Reject. "Return with comments" is a legitimate workflow action (advisor routes returns back to claimant), but it adds a state (returned) that requires the claimant to re-enter the chat flow. For the demo, Reject is sufficient to demonstrate the full rejection path. If Return is implemented, it must trigger an email notification and set claims.status = "returned". | Start with Approve/Reject. Add Return if time permits — it requires email MCP integration. |
| **Approver assignment / claim locking** | In multi-approver systems, claims are locked to prevent concurrent review. For a demo with one approver persona, this is unnecessary complexity. | No locking. Single approver assumed. |
| **Comment threading / back-and-forth with claimant** | Some systems allow the approver to ask the claimant follow-up questions from the review page. This creates a bidirectional messaging system. | Notes are internal-only. Claimant communication is through the return email notification only. |

---

## Feature Dependencies

```
[SSE streaming endpoint]
    └──required by──> [AI Chat: streaming responses]
    └──required by──> [AI Chat: thinking panel]

[ClaimState.extractedReceipt]
    └──required by──> [Chat: inline confidence display]
    └──required by──> [Chat: submission summary panel]
    └──required by──> [Audit Log: AI extraction step in timeline]
    └──required by──> [Claim Review: extracted fields display]

[ClaimState.violations]
    └──required by──> [Chat: policy citation in response]
    └──required by──> [Chat: warnings count in summary]
    └──required by──> [Audit Log: policy check step in timeline]

[Compliance Agent output]
    └──required by──> [Audit Log: full decision pathway]

[Fraud Agent output (matched_claim_id, risk_score)]
    └──required by──> [Claim Review: flag reason card]
    └──required by──> [Claim Review: linked duplicate reference]
    └──required by──> [Audit Log: anomaly detection bento card]

[Advisor Agent output (routing decision, advisor_notes)]
    └──required by──> [Claim Review: AI Insight card]
    └──required by──> [Approver Dashboard: escalated count KPI]
    └──required by──> [Audit Log: final decision step]

[audit_log table (existing)]
    └──required by──> [Audit Log: timeline timestamps]
    └──required by──> [Claim Review: reviewer notes storage]

[claims.status field]
    └──required by──> [Approver Dashboard: KPI card counts]
    └──required by──> [Approver Dashboard: status filter]
    └──required by──> [Audit Log: left panel status badges]
```

### Dependency Notes

- **Compliance + Fraud + Advisor agents must be built before Page 3 and Page 4 are fully functional.** Pages 3 and 4 can be scaffolded with placeholder data, but the flag reason card and anomaly detection bento require Fraud Agent output, and the AI Insight card requires Advisor Agent output.
- **Page 1 (Chat) is the only page that can be fully functional with only the Intake Agent.** All Intake Agent features (streaming, upload, extraction, clarification, policy citation, submission summary) are available because ClaimState is fully populated by the Intake Agent.
- **Page 2 (Dashboard) requires only database queries.** No agent output beyond what's already in claims.status. Can be built in parallel with agent work.
- **The "Return to Claimant" action on Page 4 creates a dependency on the Email MCP server.** If Return is deferred, Pages 3 and 4 have no email dependencies.

---

## MVP Definition

### Launch With (v1 — what gets built in this milestone)

These are the features required for a complete demo walkthrough of the happy path and one escalation path.

- [ ] **Page 1 — Chat**: SSE streaming, drag-and-drop upload, inline image preview, thinking state, clarification prompts, confirm/edit buttons, submission summary panel, batch details list, warning count — all table stakes
- [ ] **Page 1 — Chat differentiator**: Thinking panel with named steps (maps LangGraph node names to readable labels)
- [ ] **Page 1 — Chat differentiator**: Inline field confidence scores in extraction response
- [ ] **Page 2 — Dashboard**: Three KPI cards (Pending, Auto-Approved, Escalated), Recent Claims table with status column, row navigation to review page, status filter
- [ ] **Page 2 — Dashboard differentiator**: Auto-Approval Threshold display (read-only is sufficient; editable is a bonus)
- [ ] **Page 3 — Audit Log**: Claim list with status badges, decision pathway timeline with timestamps, confidence score display, policy citation
- [ ] **Page 3 — Audit Log differentiator**: Download Log as JSON
- [ ] **Page 4 — Claim Review**: Receipt image display, extracted fields, flag reason card, approve/reject buttons, reviewer notes textarea, rejection reason radio buttons, claim navigation
- [ ] **Page 4 — Claim Review differentiator**: AI Insight card (Advisor Agent contextual note)
- [ ] **Shared**: Top navigation bar with active page indicator, sidebar with nav links and system status pulse

### Add After Validation (v1.x)

- [ ] **Return to Claimant action (Page 4)**: Requires Email MCP wiring; add after Approve/Reject is proven
- [ ] **Anomaly Detection + Cost Benchmark cards (Page 3)**: Requires historical data; add after Fraud Agent is complete and seeded data exists
- [ ] **Auto-Approval Threshold editing (Page 2)**: Requires Advisor Agent to read the config value; add after agent is complete
- [ ] **AI Efficiency trend chart (Page 2)**: Requires sufficient historical claims to show a trend; add after demo data seeding

### Future Consideration (v2+)

- [ ] **Voice input on Chat page**: Requires Web Speech API or Whisper integration; out of scope
- [ ] **Receipt zoom on mobile**: Desktop-only per PROJECT.md constraints
- [ ] **Multi-session claim history**: Requires conversation management UI

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| SSE streaming (Page 1) | HIGH | MEDIUM | P1 |
| Drag-and-drop upload (Page 1) | HIGH | MEDIUM | P1 |
| Clarification interrupt/resume (Page 1) | HIGH | MEDIUM | P1 |
| Submission summary panel (Page 1) | HIGH | LOW | P1 |
| KPI cards (Page 2) | HIGH | LOW | P1 |
| Recent Claims table (Page 2) | HIGH | MEDIUM | P1 |
| Decision pathway timeline (Page 3) | HIGH | MEDIUM | P1 |
| Flag reason card (Page 4) | HIGH | LOW | P1 |
| Approve/Reject actions (Page 4) | HIGH | LOW | P1 |
| Thinking panel step labels (Page 1) | MEDIUM | MEDIUM | P2 |
| Field confidence display (Page 1) | MEDIUM | LOW | P2 |
| AI Insight card (Page 4) | MEDIUM | MEDIUM | P2 |
| Download Log button (Page 3) | LOW | LOW | P2 |
| Linked duplicate reference (Page 4) | MEDIUM | LOW | P2 |
| AI Efficiency chart (Page 2) | LOW | MEDIUM | P3 |
| Anomaly Detection bento (Page 3) | MEDIUM | HIGH | P3 |
| Return to Claimant action (Page 4) | MEDIUM | MEDIUM | P3 |
| Auto-Approval Threshold editing (Page 2) | HIGH | MEDIUM | P3 |

**Priority key:**
- P1: Must have for a complete demo walkthrough
- P2: Should have — adds demo depth, moderate cost
- P3: Nice to have — deferred until P1+P2 complete

---

## Competitor Feature Analysis

| Feature | Expensify | Ramp | AppZen | Our Approach |
|---------|-----------|------|--------|--------------|
| Chat-based submission | Concierge chat | No | No | Native — primary interaction model |
| Streaming AI responses | No | No | No | SSE token streaming — differentiator |
| Thinking step labels | No | No | No | LangGraph node names mapped to UI labels — differentiator |
| Per-field confidence | No | No | AppZen shows audit score | Inline per-field confidence in chat — differentiator |
| Approver dashboard | Yes (forms-based) | Yes (spend analytics) | Yes (audit queue) | KPI cards + AI efficiency metric |
| Decision pathway timeline | No | No | AppZen audit trail | Stitch-designed timeline with named agent steps — differentiator |
| AI Insight card for reviewer | No | No | Partial | Advisor Agent reasoning surfaced to human reviewer — differentiator |

---

## Sources

### Chat UI and SSE Streaming Patterns (MEDIUM confidence — web search verified against HTMX docs)
- [Real-Time UX with the htmx SSE Extension — OpenReplay Blog](https://blog.openreplay.com/real-time-ux-htmx-sse/)
- [Build an Agentic Chatbot with HTMX — Medium, Dec 2025](https://medium.com/data-science-collective/javascript-fatigued-build-an-agentic-chatbot-with-htmx-503569adf2f9)
- [Javascript Fatigue: HTMX Is All You Need to Build ChatGPT — Towards Data Science](https://towardsdatascience.com/javascript-fatigue-you-dont-need-js-to-build-chatgpt-part-2/)

### AI Expense Management Feature Benchmarks (MEDIUM confidence — web search, multiple sources agree)
- [Expensify AI-Powered Expense Management Framework](https://use.expensify.com/blog/expensifys-ai-powered-expense-management-framework)
- [Top 10 AI Tools for Expense Management 2026 — ChatFin](https://chatfin.ai/blog/top-ai-tools-for-cfos/top-10-ai-tools-for-expense-management-2026-edition/)
- [ChatExpense — AI Expense Tracker with chat, image, voice input](https://chatexpense.com/)

### Approver Dashboard UX Patterns (MEDIUM confidence — web search)
- [From Data to Decisions: UX Strategies for Real-Time Dashboards — Smashing Magazine, 2025](https://www.smashingmagazine.com/2025/09/ux-strategies-real-time-dashboards/)
- [Purchase Order Approval Workflow with AI (2025) — Approveit](https://approveit.today/blog/purchase-order-approval-workflow-with-ai-rules-thresholds-templates-(2025)/)
- [Effective Dashboard Design Principles for 2025 — UXPin](https://www.uxpin.com/studio/blog/dashboard-design-principles/)

### AI Audit Trail Requirements (MEDIUM confidence — web search, ISACA/Scrut authoritative)
- [The Growing Challenge of Auditing Agentic AI — ISACA, 2025](https://www.isaca.org/resources/news-and-trends/industry-news/2025/the-growing-challenge-of-auditing-agentic-ai)
- [Audit Trail Requirements for High-Risk AI Systems — Scrut.io](https://www.scrut.io/glossary/audit-trail-for-ai-systems)
- [Audit Logs in AI Systems: What to Track and Why — Latitude](https://latitude.so/blog/audit-logs-in-ai-systems-what-to-track-and-why)
- [The Rise of AI Audit Trails — Aptus Data Labs](https://www.aptusdatalabs.com/thought-leadership/the-rise-of-ai-audit-trails-ensuring-traceability-in-decision-making)

### Explainable AI for Claim Review (MEDIUM confidence — web search)
- [Explainable AI in Finance: Addressing the Needs of Diverse Stakeholders — CFA Institute, 2025](https://rpc.cfainstitute.org/research/reports/2025/explainable-ai-in-finance)
- [Compliance Without the Black Box — Castellum.AI](https://www.castellum.ai/insights/compliance-without-the-black-box-case-for-explainable-ai)
- [AI Explainability Scorecard — Cloud Security Alliance, 2025](https://cloudsecurityalliance.org/blog/2025/12/08/ai-explainability-scorecard)

### Primary Design Source (HIGH confidence — first-party)
- Stitch HTML designs: `docs/ux/01_ai_chat_submission.html`, `02_audit_transparency_log.html`, `03_claim_review_escalation.html`, `04_approver_dashboard.html`

---
*Feature research for: AI-powered expense claims web application — multi-page custom UI (v2.0 milestone)*
*Researched: 2026-03-30*
