# Roadmap: Agentic Expense Claims

## Overview

This roadmap delivers a multi-agent expense claim processing system in 6 phases, moving from orchestration skeleton through incremental agent delivery to a demo-ready evaluation. Phase 1 establishes the minimal orchestration foundation (project skeleton, LangGraph stub graph with 4 agent nodes, Docker Compose with Chainlit + Postgres). Phase 2 delivers the supporting infrastructure: DB schema, MCP servers, OpenRouter client, Qdrant policy ingestion. Phase 2.1 builds the Intake Agent with receipt upload, VLM extraction, policy validation, and the conversational claim submission loop. Phase 3 adds post-submission Compliance and Fraud agents running in parallel. Phase 4 completes the pipeline with the Advisor Agent, reviewer interface, email notifications, and approval routing. Phase 5 produces evaluation results and demo polish for the course deliverable.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Inserted phases split from existing scope

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation Infrastructure** - Project skeleton, LangGraph orchestration with 4 stub agents, Docker Compose (Chainlit + Postgres)
- [x] **Phase 2: Supporting Infrastructure** - DB schema, MCP servers, OpenRouter client, Qdrant policy ingestion
- [x] **Phase 2.1: Intake Agent + Receipt Processing** - VLM extraction, policy validation, conversational claim submission loop, claimant UI
- [x] **Phase 2.2: Intake Agent Gap Closure** - Fix submitClaim blocker, structured agent output, prompt improvements, startup script, re-test blocked UAT cases
- [ ] **Phase 3: Compliance + Fraud Agents** - Post-submission parallel policy audit and duplicate detection
- [ ] **Phase 4: Advisor Agent + Reviewer Flow** - Decision synthesis, approval routing, reviewer UI, email notifications
- [ ] **Phase 5: Evaluation + Demo** - Test dataset, evaluation framework, baseline comparisons, demo polish

## Phase Details

### Phase 1: Foundation Infrastructure
**Goal**: Team can clone the repo, run `docker compose up`, and have Chainlit + Postgres running with a stub LangGraph graph that flows a test claim through 4 placeholder agent nodes (with parallel fan-out for Compliance + Fraud) and state persisted to PostgreSQL checkpointer
**Depends on**: Nothing (first phase)
**Requirements**: ORCH-01, ORCH-08, INFR-03
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts Chainlit app and Postgres, both pass health checks
  2. A test claim flows through the stub LangGraph graph (Intake -> [Compliance || Fraud] -> Advisor) with ClaimState passed correctly between nodes and persisted to PostgreSQL checkpointer
  3. All 4 stub agent nodes execute and return "Hello world" messages appended to state
  4. Parallel fan-out for Compliance + Fraud executes both nodes in the same LangGraph superstep
  5. All configuration loaded from .env files (no hardcoded values)
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — Project skeleton, Docker Compose (Chainlit + Postgres), configuration from .env
- [x] 01-02-PLAN.md — ClaimState definition, LangGraph stub graph with Postgres checkpointer and parallel fan-out

### Phase 2: Supporting Infrastructure
**Goal**: All supporting services are running and tested: Postgres with claims schema (Alembic-managed), MCP servers (off-the-shelf where possible), OpenRouter model client, and Qdrant with synthetic expense policies embedded and searchable
**Depends on**: Phase 1
**Requirements**: INFR-01, INFR-02, INFR-04, DATA-01, DATA-04, POLV-01, POLV-02
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts all services (Chainlit app, Postgres, Qdrant, MCP servers) and all pass health checks
  2. Alembic migrations create `claims` and `receipts` tables in Postgres (line items as JSON in receipts), with audit_log table for status change tracking, and a test record can be inserted and queried
  3. OpenRouter model client returns a response from a configured model when given a text prompt, with model name from .env and simple retry (3 retries, 2s delay)
  4. Synthetic SUTD expense policies (markdown files from `src/policy/`) are embedded in Qdrant and a semantic search query returns relevant policy clauses
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md — Database schema (claims, receipts, audit_log) with Alembic async migrations, OpenRouter model client with retry, Qdrant Docker service
- [x] 02-02-PLAN.md — 4 MCP servers (RAG, DB, Currency, Email) as Docker services, synthetic policy documents, Qdrant policy ingestion

### Phase 2.1: Intake Agent + Receipt Processing (INSERTED)
**Goal**: Claimant uploads a receipt image in Chainlit, sees extracted fields with confidence scores, gets policy violations flagged with cited clauses, confirms or corrects fields, and submits a validated claim -- all in a conversational loop under 3 minutes
**Depends on**: Phase 2
**Requirements**: EXTR-01, EXTR-02, EXTR-03, EXTR-04, EXTR-05, EXTR-06, EXTR-07, EXTR-08, POLV-03, POLV-04, POLV-05, POLV-06, POLV-07, ORCH-02, CHAT-01, CHAT-03, CHAT-04
**Success Criteria** (what must be TRUE):
  1. Claimant uploads a receipt image in Chainlit and sees structured extracted fields (merchant, date, amount, currency, line items, tax, payment method) with per-field confidence scores within seconds
  2. Uploading a blurry or low-resolution image returns a rejection message with guidance to re-upload a clearer image
  3. Foreign currency receipts are automatically detected, converted to SGD via Frankfurter API, and the claim stores both original and converted amounts
  4. Policy violations (e.g., meal over cap, missing GL code) are flagged with the specific policy clause and section reference, and claimant can provide justification or correct the claim
  5. Low-confidence VLM extractions trigger a clarification prompt, claimant can confirm or correct extracted fields, and the confirmed claim is submitted and persisted to Postgres
**Plans**: 3 plans

Plans:
- [x] 02.1-01-PLAN.md — Foundation: ClaimState/Settings expansion, image quality gate, MCP client utility, VLM receipt extraction tool (TDD)
- [x] 02.1-02-PLAN.md — MCP tools: policy search, currency conversion, claim submission, askHuman interrupt, dual currency Alembic migration (TDD)
- [x] 02.1-03-PLAN.md — Agent wiring: intakeNode with create_react_agent, Chainlit image/interrupt handling, Evaluator Gate

### Phase 2.2: Intake Agent Gap Closure (INSERTED)
**Goal**: All Phase 2.1 UAT gaps are resolved -- submitClaim tool works end-to-end in Chainlit runtime, agent output is structured step-by-step (not chain-of-thought), prompt catches description-receipt mismatches and numeric policy errors, and a single startup script brings the system to ready state
**Depends on**: Phase 2.1
**Requirements**: EXTR-01, EXTR-06, POLV-03, POLV-05, CHAT-01, CHAT-03, ORCH-02, INFR-03
**Success Criteria** (what must be TRUE):
  1. submitClaim tool successfully creates both claim and receipt records in the database when invoked through the full Chainlit -> LangGraph -> MCP pipeline (not just in direct test)
  2. Agent output to the user is structured step-by-step (perform action -> report result -> state next step -> proceed), with no raw chain-of-thought or intermediate tool reasoning visible
  3. Agent cross-references user's text description against VLM-extracted receipt data and flags contradictions (e.g., "hotel" description but restaurant receipt) before proceeding
  4. Agent correctly evaluates numeric conditions in retrieved policy clauses (e.g., SGD 98.56 does NOT exceed SGD 100 threshold)
  5. `scripts/startup.sh` runs docker compose, waits for health checks, runs Alembic migrations, and runs RAG policy ingestion in a single command
  6. Previously blocked UAT tests (human clarification, evaluator gate routing, end-to-end intake flow) pass after fixes
**Plans**: 5 plans (3 original + 2 gap closure)

Plans:
- [x] 02.2-01-PLAN.md — Structured JSON logging with Seq, merge insertReceipt into atomic insertClaim, intakeFindings persistence (ClaimState + Alembic JSONB migration)
- [x] 02.2-02-PLAN.md — 12-step strict checklist system prompt, Chainlit Step elements for collapsible CoT, output filtering
- [x] 02.2-03-PLAN.md — Startup script (docker + health checks + migrations + ingestion) and blocked UAT re-test
- [x] 02.2-04-PLAN.md — Seq log ingestion fix (SeqHandler CLEF HTTP POST) and unified logging consolidation
- [x] 02.2-05-PLAN.md — Conversational UX rewrite (two-layer model), message deduplication, CoT capture, conditional cross-reference

### Phase 3: Compliance + Fraud Agents
**Goal**: After a claim is submitted, Compliance and Fraud agents execute in parallel -- Compliance audits against org-level policies with cited clauses, Fraud detects duplicate receipts against historical data -- and their findings are stored in ClaimState for the Advisor
**Depends on**: Phase 2.1
**Requirements**: ORCH-03, ORCH-04, ORCH-06, FRAD-01, FRAD-02, FRAD-03, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):
  1. Submitting a claim triggers both Compliance and Fraud agents executing in the same LangGraph superstep (parallel fan-out), not sequentially
  2. Compliance Agent audits the submitted claim against org-level policies via RAG and produces pass/fail findings with cited policy clauses and section references
  3. Submitting a duplicate receipt (same date + amount + vendor as an existing claim) triggers a fraud flag with evidence linking to the original claim
  4. All agent decisions, state changes, and routing outcomes are logged in the audit trail and queryable
**Plans**: TBD

Plans:
- [ ] 03-01: Compliance Agent (Evaluator pattern, RAG integration, org-level policy audit)
- [ ] 03-02: Fraud Agent (Tool Call pattern, duplicate detection queries, fraud findings in ClaimState) and parallel execution wiring

### Phase 4: Advisor Agent + Reviewer Flow
**Goal**: Advisor Agent synthesizes Compliance and Fraud findings into a risk assessment, routes claims to auto-approve, return-to-claimant, or escalate-to-reviewer -- and the reviewer can see escalated claims with full evidence and take action through a dedicated Chainlit persona
**Depends on**: Phase 3
**Requirements**: ORCH-05, ORCH-07, APRV-01, APRV-02, APRV-03, APRV-04, REVW-01, REVW-02, REVW-03, REVW-04, NOTF-01, NOTF-02, NOTF-03, CHAT-02
**Success Criteria** (what must be TRUE):
  1. A clean claim (no compliance violations, no fraud flags) is auto-approved by the Advisor Agent and its status is updated to "approved" in the database
  2. A claim with policy violations is returned to the claimant with correction instructions citing specific policy clauses, and the claimant receives an email notification
  3. A suspicious claim (fraud flags or agent disagreement) is escalated to the reviewer with a risk summary, and the reviewer receives an email notification
  4. Reviewer opens the Chainlit reviewer persona, sees a list of escalated claims with risk summary, compliance findings, fraud evidence, and policy citations, and can approve, reject, or return a claim with comments
  5. Reviewer decisions update the claim status in the database and trigger email notification to the claimant
**Plans**: TBD

Plans:
- [ ] 04-01: Advisor Agent (Reflection + Routing pattern, synthesis logic, conditional routing to approve/return/escalate)
- [ ] 04-02: Reviewer interface (Chainlit reviewer persona, escalated claim list, risk summary display, reviewer actions)
- [ ] 04-03: Email notifications (Email MCP server integration, notification triggers for returns, escalations, final decisions)

### Phase 5: Evaluation + Demo
**Goal**: System is evaluated against quantitative targets (submission time < 3 min, field accuracy > 95%) with baseline comparisons, and a smooth end-to-end demo is ready for course presentation
**Depends on**: Phase 4
**Requirements**: None (course deliverable, not functional requirements)
**Success Criteria** (what must be TRUE):
  1. Evaluation framework runs against a test dataset of sample receipts with ground truth, producing submission time and field-level extraction accuracy metrics
  2. Metrics are compared against two baselines: single-prompt pipeline (Gemini) and manual SAP Concur workflow
  3. End-to-end demo runs all 6 E2E test scenarios (happy path, foreign currency, policy violation, fraud detection, reviewer flow, low-quality receipt) without failures
**Plans**: TBD

Plans:
- [ ] 05-01: Test dataset creation (sample receipts with ground truth) and evaluation framework
- [ ] 05-02: Baseline comparisons, demo polish, and E2E test validation

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 2.1 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|---------------|--------|-----------|
| 1. Foundation Infrastructure | 2/2 | Complete | 2026-03-23 |
| 2. Supporting Infrastructure | 2/2 | Complete | 2026-03-24 |
| 2.1. Intake Agent + Receipt Processing | 3/3 | Complete | 2026-03-25 |
| 2.2. Intake Agent Gap Closure | 5/5 | Complete | 2026-03-26 |
| 3. Compliance + Fraud Agents | 0/2 | Not started | - |
| 4. Advisor Agent + Reviewer Flow | 0/3 | Not started | - |
| 5. Evaluation + Demo | 0/2 | Not started | - |
