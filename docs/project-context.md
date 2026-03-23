# Code Context: Agentic Expense Claims
Date: 2026-03-23

## Objective

Build a multi-agent multimodal system that automates SUTD expense claim processing. The system replaces the manual SAP Concur workflow (15-25 min per claim, up to 2 months for reimbursement) with an AI-driven pipeline targeting <3 min submission time and >95% field extraction accuracy.

### Key Results
- Submission time < 3 minutes (from receipt upload to completed claim)
- Field-level extraction accuracy > 95% on structured fields
- Full 4-agent pipeline working end-to-end locally
- Claimant and reviewer personas functional in Chainlit UI

## Architecture

```
                         Chainlit UI
                    (Claimant / Reviewer)
                            |
                      LangGraph Engine
                     (Shared ClaimState)
                            |
        ----------------------------------------
        |                                      |
   PRE-SUBMISSION                        POST-SUBMISSION
        |                                      |
  [Intake Agent]                    [Compliance]  [Fraud]
   ReAct + Gate                      Evaluator   Tool Call
   |  |  |  |                           |           |
  VLM RAG DB FX                        RAG         DB
        |                                      |
        |                              [Advisor Agent]
        |                            Reflection + Routing
        |                                   |
        |                              Email MCP
        |                                   |
        +----- auto-approve / return / escalate ------+

Docker Compose:
  - chainlit-app (Python)
  - postgres (16)
  - qdrant (vector store)
  - rag-mcp-server
  - dbhub-mcp-server
  - frankfurter-mcp-server
  - email-mcp-server
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language | Python throughout | LangGraph and Chainlit are Python-native |
| Orchestration | LangGraph | Native state machine with conditional routing, parallel execution, ReAct support |
| UI | Chainlit | Conversational AI interface with image upload, supports personas |
| Model access | OpenRouter API | Toggle between free VLM/LLM models, no self-hosting complexity |
| Database | Postgres (new schema) | Relational data for claims, receipts, line items, history |
| Vector store | Qdrant | High-performance, runs as Docker service, production-ready |
| Currency API | frankfurter.app | Free, no API key, covers major currencies |
| MCP servers | Separate Docker services | Clean separation, independent scaling, team can work in parallel |
| Policy data | Synthetic policies | Created for development and demo; real SUTD policies not available |
| Deploy target | Local first (Docker Compose), cloud later | Course project demo runs locally; AWS deployment deferred |

### Team Approach
Shared foundation (Milestone 1), then parallel agent development across 4 team members. Clean interfaces between agents via LangGraph shared state.

## Implementation Plan

### Milestone 1: Local Foundation + Shared Infrastructure
- **Delivers**: Project skeleton, Docker Compose (Postgres, Qdrant), OpenRouter model client, LangGraph stub graph with shared state, Chainlit UI. Team can clone and run.
- **Why Now**: Everything depends on this. Enables parallel agent work after.
- **Success Criteria**: `docker compose up` starts all services; Chainlit UI opens in browser; test message flows through stub LangGraph graph; OpenRouter returns a model response; Postgres schema is migrated and queryable.

#### Phase 1.1: Project Skeleton
- **Delivers**: Poetry project, folder structure, dependency management, base configuration
- **Definition of Done**:
  - Poetry project initialized with Python 3.11+
  - Vertical slice folder structure for agents
  - `.env.local` with OpenRouter API key, DB connection, Qdrant URL
  - `.env.test` under `tests/`
- **Success Criteria**:
  - `poetry install` succeeds
  - Project structure follows vertical slice pattern

#### Phase 1.2: Docker Compose + Database Schema
- **Delivers**: Docker Compose with Postgres and Qdrant running; claims database schema migrated
- **Definition of Done**:
  - `docker-compose.yml` with Postgres 16 and Qdrant containers
  - Alembic migrations for core claims schema (claims, receipts, line_items tables)
  - Seed script for synthetic test data
- **Success Criteria**:
  - `docker compose up` starts Postgres + Qdrant
  - Migrations run successfully
  - Can query empty claims table

#### Phase 1.3: OpenRouter Model Client
- **Delivers**: Abstracted model client that routes to OpenRouter for both VLM and LLM calls
- **Definition of Done**:
  - Model client with `complete_text()` and `extract_from_image()` methods
  - Model name configurable via `.env.local` (toggle free models)
  - Retry logic with exponential backoff
- **Success Criteria**:
  - Unit tests pass with mocked responses
  - Integration test sends a real request to OpenRouter and gets a response

#### Phase 1.4: LangGraph Shared State + Stub Graph
- **Delivers**: LangGraph state machine with shared ClaimState definition and stub nodes for all 4 agents
- **Definition of Done**:
  - ClaimState TypedDict with all fields needed across agents
  - Graph with 4 stub nodes (Intake, Compliance, Fraud, Advisor)
  - Conditional routing edges (pre-submission to post-submission to advisor)
  - Parallel fan-out for Compliance + Fraud
- **Success Criteria**:
  - Graph compiles without errors
  - A test claim flows through all stub nodes end-to-end
  - State is correctly passed between nodes

#### Phase 1.5: Chainlit UI + Graph Integration
- **Delivers**: Chainlit app connected to LangGraph stub graph; claimant can send a message and see a stub response
- **Definition of Done**:
  - Chainlit app with message handler
  - Image upload capability (receipt images)
  - Connected to LangGraph graph execution
  - Basic persona routing (claimant vs reviewer)
- **Success Criteria**:
  - `chainlit run` opens UI in browser
  - Sending a message triggers graph execution
  - Uploading an image is received by the app
  - Stub response appears in chat

### Milestone 2: Intake Agent (Pre-submission)
- **Delivers**: Claimant uploads receipt -> VLM extracts fields -> validates against policy (RAG) -> converts currency -> persists claim. Full pre-submission loop working E2E.
- **Why Now**: Core user-facing value. Produces the claim data all other agents consume.
- **Success Criteria**: Receipt upload triggers extraction, policy validation with cited clauses, currency conversion for foreign receipts, claim persisted to Postgres, claimant sees structured summary and can confirm.

### Milestone 3: Post-submission Agents (Compliance + Fraud)
- **Delivers**: Compliance Agent audits claim against org-level policies. Fraud Agent checks historical claims for duplicates/anomalies. Both run in parallel via LangGraph fan-out.
- **Why Now**: Depends on Milestone 2 producing claim data. Can be built in parallel by two team members.
- **Success Criteria**: Submitted claim triggers parallel Compliance + Fraud checks; Compliance produces pass/fail with cited policy clauses; Fraud detects duplicate receipts and anomalous patterns; results stored in ClaimState for Advisor.

### Milestone 4: Advisor Agent + Reviewer Flow
- **Delivers**: Advisor synthesizes compliance + fraud findings, routes to auto-approve/return/escalate. Email notifications. Reviewer persona in Chainlit sees escalated claims and can act on them. Full pipeline E2E.
- **Why Now**: Depends on Milestone 3 outputs. Completes the end-to-end flow.
- **Success Criteria**: Advisor produces risk assessment from compliance + fraud findings; auto-approves clean claims; escalates suspicious claims to reviewer; reviewer sees escalated claims with full evidence in Chainlit; reviewer can approve/reject/return.

### Milestone 5: Evaluation + Demo Polish
- **Delivers**: Test dataset (sample receipts + ground truth), evaluation framework measuring submission time and field accuracy, baseline comparisons, demo-ready presentation.
- **Why Now**: Course deliverable requires evaluation results. Needs working pipeline from Milestone 4.
- **Success Criteria**: Evaluation runs against test dataset; submission time and accuracy metrics calculated; results compared against baselines (single-prompt pipeline, manual workflow); demo runs smoothly end-to-end.

### Milestone 6: AWS Deployment (Deferred)
- **Delivers**: Terraform infrastructure, Secrets Manager, cloud deployment.
- **Why Now**: Not needed for course demo. Future milestone if project continues beyond course.
- **Success Criteria**: System runs in AWS with same behavior as local.

## E2E Tests

### E2E Test 1: Happy Path - Claimant Submits Valid Claim
**Preconditions:**
- Postgres running, synthetic policies loaded in Qdrant, OpenRouter reachable

**Steps:**
1. Claimant opens Chainlit UI
2. Uploads a clear receipt image (SGD, within policy limits)
3. Intake Agent extracts fields, validates against policy, shows summary
4. Claimant confirms submission
5. Compliance Agent passes the claim
6. Fraud Agent finds no issues
7. Advisor Agent auto-approves

**Expected Outcome:**
- Claim status is "approved" in database
- No escalation to reviewer

### E2E Test 2: Foreign Currency Claim
**Preconditions:**
- Same as E2E Test 1

**Steps:**
1. Claimant uploads a receipt in USD
2. Intake Agent extracts fields, detects foreign currency
3. Frankfurter MCP converts USD to SGD
4. Policy validation runs against SGD amount
5. Claim submitted with converted amount

**Expected Outcome:**
- Claim persisted with both original (USD) and converted (SGD) amounts
- Pipeline continues normally

### E2E Test 3: Policy Violation - Returned to Claimant
**Preconditions:**
- Synthetic policy has meal cap of $50/day

**Steps:**
1. Claimant uploads receipt for $85 meal (single person, no justification)
2. Intake Agent flags policy violation with cited clause
3. Claimant resubmits with justification or corrected amount
4. If still non-compliant post-submission, Advisor returns to claimant with correction instructions

**Expected Outcome:**
- Claim status is "returned"
- Claimant sees specific policy violation and instructions

### E2E Test 4: Fraud Detection - Escalated to Reviewer
**Preconditions:**
- A duplicate receipt already exists in the database

**Steps:**
1. Claimant uploads the same receipt a second time
2. Intake Agent processes normally
3. Fraud Agent detects duplicate receipt in historical data
4. Advisor Agent escalates to human reviewer with fraud finding

**Expected Outcome:**
- Claim status is "escalated"
- Reviewer sees claim with fraud flag and evidence

### E2E Test 5: Reviewer Processes Escalated Claim
**Preconditions:**
- An escalated claim exists from E2E Test 4

**Steps:**
1. Reviewer opens Chainlit UI (reviewer persona)
2. Sees escalated claim with risk summary, compliance findings, fraud findings, policy citations
3. Reviewer approves, rejects, or returns with comments

**Expected Outcome:**
- Claim status updated to reviewer's decision
- If email MCP active, claimant is notified

### E2E Test 6: Low-Quality Receipt - Clarification Loop
**Preconditions:**
- Same as E2E Test 1

**Steps:**
1. Claimant uploads a blurry/crumpled receipt
2. VLM extracts fields with low confidence
3. Intake Agent asks claimant to confirm or correct specific fields
4. Claimant provides corrections
5. Claim proceeds with corrected data

**Expected Outcome:**
- Claim persisted with claimant-confirmed values
- Low-confidence fields are logged

## Decisions Made

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Model hosting | OpenRouter API (free model toggle) | No self-hosting complexity, flexible model selection |
| 2 | Database | Postgres, new schema from scratch | Relational fits claims data well, team designs schema |
| 3 | Vector store | Qdrant | Production-ready, Docker-native, high performance |
| 4 | MCP server architecture | Separate Docker services | Clean separation for parallel team development |
| 5 | Policy data | Synthetic | Real SUTD policies not available; synthetic sufficient for demo |
| 6 | Currency API | frankfurter.app (free) | No API key needed, good for course project |
| 7 | Team approach | Shared foundation, then parallel | Milestone 1 shared, then agents split across team members |
| 8 | Deploy strategy | Local first, cloud deferred | Course demo runs locally; Milestone 6 (AWS) only if project continues |
| 9 | Scope | Full 4-agent pipeline, Intake first | Build incrementally, Intake is MVP |
