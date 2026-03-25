# Requirements: Agentic Expense Claims

**Defined:** 2026-03-23
**Core Value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes

## v1 Requirements

Requirements for the course project deliverable. Each maps to roadmap phases.

### Receipt Extraction

- [x] **EXTR-01**: Claimant uploads receipt image via Chainlit chat interface
- [x] **EXTR-02**: VLM extracts structured fields from receipt image (merchant, date, amount, currency, line items, tax, payment method)
- [x] **EXTR-03**: System provides per-field confidence scores for VLM extractions
- [x] **EXTR-04**: Low-confidence fields trigger clarification request to claimant in conversational loop
- [x] **EXTR-05**: Claimant can confirm or correct extracted fields before submission
- [x] **EXTR-06**: System detects foreign currency from receipt and converts to SGD via Frankfurter API
- [x] **EXTR-07**: Claim stores both original currency amount and converted SGD amount
- [x] **EXTR-08**: System rejects blurry or low-resolution images with guidance to re-upload

### Policy Validation

- [x] **POLV-01**: Synthetic SUTD expense policies created covering meal caps, transport allowances, overseas travel, GL codes, approval thresholds
- [x] **POLV-02**: Policy documents embedded and stored in Qdrant via RAG MCP server
- [x] **POLV-03**: System retrieves relevant policy clauses given claim context (semantic search)
- [x] **POLV-04**: Intake Agent validates claim against retrieved policies BEFORE submission
- [x] **POLV-05**: Policy violations flagged with cited policy clause and section reference
- [x] **POLV-06**: System checks claim against spending limits, meal caps, and category restrictions
- [x] **POLV-07**: Claimant can provide justification for flagged violations or correct the claim

### Fraud Detection

- [ ] **FRAD-01**: Fraud Agent queries historical claims database for duplicate receipts (match on date + amount + vendor)
- [ ] **FRAD-02**: Duplicate receipt detected triggers fraud flag with evidence (original claim reference)
- [ ] **FRAD-03**: Fraud findings stored in ClaimState with fraud/legit determination per receipt

### Multi-Agent Orchestration

- [x] **ORCH-01**: LangGraph state machine with shared ClaimState TypedDict orchestrates 4 agent nodes
- [x] **ORCH-02**: Intake Agent implements ReAct pattern with Evaluator Gate for pre-submission validation
- [ ] **ORCH-03**: Compliance Agent implements Evaluator pattern for post-submission policy audit
- [ ] **ORCH-04**: Fraud Agent implements Tool Call pattern for post-submission duplicate detection
- [ ] **ORCH-05**: Advisor Agent implements Reflection + Routing pattern for decision synthesis
- [ ] **ORCH-06**: Compliance and Fraud agents execute in parallel (LangGraph fan-out)
- [ ] **ORCH-07**: Advisor Agent waits for both Compliance and Fraud before synthesizing
- [x] **ORCH-08**: PostgreSQL checkpointer persists state after each node execution (crash recovery)

### Approval Routing

- [ ] **APRV-01**: Advisor Agent routes clean claims (no violations, no fraud) to auto-approve
- [ ] **APRV-02**: Advisor Agent routes policy violations to return-to-claimant with correction instructions and cited clauses
- [ ] **APRV-03**: Advisor Agent routes suspicious claims (fraud flags, agent disagreement) to human reviewer with evidence summary
- [ ] **APRV-04**: Claim status updated in database (pending, approved, returned, escalated)

### Reviewer Interface

- [ ] **REVW-01**: Reviewer persona in Chainlit sees list of escalated claims
- [ ] **REVW-02**: Reviewer sees risk summary, compliance findings, fraud evidence, and policy citations per claim
- [ ] **REVW-03**: Reviewer can approve, reject, or return claim with comments
- [ ] **REVW-04**: Reviewer decision updates claim status in database

### Email Notifications

- [ ] **NOTF-01**: Email MCP server sends notification to claimant when claim is returned with correction instructions
- [ ] **NOTF-02**: Email MCP server sends notification to reviewer when claim is escalated
- [ ] **NOTF-03**: Email MCP server sends notification to claimant when claim is approved or rejected

### Data Persistence

- [x] **DATA-01**: Claims, receipts, and line items persisted to PostgreSQL via DBHub MCP server
- [ ] **DATA-02**: Historical claims queryable for fraud detection
- [ ] **DATA-03**: Audit trail logs all agent decisions, state changes, and routing outcomes
- [x] **DATA-04**: Receipt images stored externally (filesystem), path references in database

### Infrastructure

- [x] **INFR-01**: Docker Compose orchestrates all services (Chainlit app, Postgres, Qdrant, 4 MCP servers)
- [x] **INFR-02**: OpenRouter model client abstracts VLM and LLM calls with configurable model names via .env
- [x] **INFR-03**: All configuration loaded from .env files (no hardcoded values)
- [x] **INFR-04**: MCP servers implemented as separate Docker services using FastMCP

### Conversational UI

- [x] **CHAT-01**: Chainlit app supports claimant persona (receipt upload, claim submission, status)
- [ ] **CHAT-02**: Chainlit app supports reviewer persona (escalated claim review, decision)
- [x] **CHAT-03**: Claimant receives real-time streaming responses during claim processing
- [x] **CHAT-04**: Chainlit handles image uploads and passes to LangGraph for VLM processing

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Fraud

- **FRAD-04**: Anomaly flagging based on spending pattern deviation from claimant history
- **FRAD-05**: AI-generated receipt detection using image forensics (EXIF, grayscale patterns, clone-stamping)
- **FRAD-06**: Behavioral pattern analysis across department and time periods

### Multi-Language

- **LANG-01**: Multi-language receipt OCR beyond English
- **LANG-02**: Policy document translation for cross-language validation

### Advanced Analytics

- **ANLT-01**: Dashboard showing claim processing metrics (volume, approval rate, processing time)
- **ANLT-02**: VLM extraction accuracy tracking over time

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Travel booking integration | SAP Concur territory, not core to expense claims processing |
| Corporate card issuance | Requires banking license, payment processing infrastructure |
| Accounting system integration | Complex, vendor-specific (QuickBooks/Xero/SAP ERP). Export CSV/JSON instead |
| Mobile app | Doubles development effort. Web UI via Chainlit sufficient |
| Reimbursement payment processing | Requires bank integration. End at "approved for payment" |
| Multi-tenant SaaS | Single-tenant for SUTD. Policies in config, not UI |
| Advanced reporting/BI | Not core to AI agent value proposition |
| Vendor management | Orthogonal to claim processing. Extract vendor name, don't manage lifecycle |
| Budgeting tools | Separate finance function. Read budget limits from config |
| Real-time push notifications | Email sufficient. No SMTP/Twilio infrastructure needed beyond Email MCP |
| Authentication/authorization | Not needed for course demo |
| AWS/cloud deployment | Local-only for course project (Milestone 6 deferred) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTR-01 | Phase 2.1 | Complete |
| EXTR-02 | Phase 2.1 | Complete |
| EXTR-03 | Phase 2.1 | Complete |
| EXTR-04 | Phase 2.1 | Complete |
| EXTR-05 | Phase 2.1 | Complete |
| EXTR-06 | Phase 2.1 | Complete |
| EXTR-07 | Phase 2.1 | Complete |
| EXTR-08 | Phase 2.1 | Complete |
| POLV-01 | Phase 2 | Complete |
| POLV-02 | Phase 2 | Complete |
| POLV-03 | Phase 2.1 | Complete |
| POLV-04 | Phase 2.1 | Complete |
| POLV-05 | Phase 2.1 | Complete |
| POLV-06 | Phase 2.1 | Complete |
| POLV-07 | Phase 2.1 | Complete |
| FRAD-01 | Phase 3 | Pending |
| FRAD-02 | Phase 3 | Pending |
| FRAD-03 | Phase 3 | Pending |
| ORCH-01 | Phase 1 | Complete |
| ORCH-02 | Phase 2.1 | Complete |
| ORCH-03 | Phase 3 | Pending |
| ORCH-04 | Phase 3 | Pending |
| ORCH-05 | Phase 4 | Pending |
| ORCH-06 | Phase 3 | Pending |
| ORCH-07 | Phase 4 | Pending |
| ORCH-08 | Phase 1 | Complete |
| APRV-01 | Phase 4 | Pending |
| APRV-02 | Phase 4 | Pending |
| APRV-03 | Phase 4 | Pending |
| APRV-04 | Phase 4 | Pending |
| REVW-01 | Phase 4 | Pending |
| REVW-02 | Phase 4 | Pending |
| REVW-03 | Phase 4 | Pending |
| REVW-04 | Phase 4 | Pending |
| NOTF-01 | Phase 4 | Pending |
| NOTF-02 | Phase 4 | Pending |
| NOTF-03 | Phase 4 | Pending |
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 3 | Pending |
| DATA-03 | Phase 3 | Pending |
| DATA-04 | Phase 2 | Complete |
| INFR-01 | Phase 2 | Complete |
| INFR-02 | Phase 2 | Complete |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 2 | Complete |
| CHAT-01 | Phase 2.1 | Complete |
| CHAT-02 | Phase 4 | Pending |
| CHAT-03 | Phase 2.1 | Complete |
| CHAT-04 | Phase 2.1 | Complete |

**Coverage:**
- v1 requirements: 49 total
- Mapped to phases: 49
- Unmapped: 0

---
*Requirements defined: 2026-03-23*
*Last updated: 2026-03-23 after roadmap creation (corrected count from 37 to 49, full traceability added)*
