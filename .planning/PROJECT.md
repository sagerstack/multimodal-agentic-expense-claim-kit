# Agentic Expense Claims

## What This Is

A multi-agent multimodal system that automates SUTD expense claim processing. Four AI agents (Intake, Compliance, Fraud, Advisor) orchestrated by LangGraph process receipt images, validate against policies, detect fraud, and route claims to auto-approve, return, or human review — all through a Chainlit conversational interface.

## Core Value

Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes — replacing a 15-25 minute manual process with frequent rejections.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Claimant uploads receipt image and gets structured fields extracted via VLM (merchant, date, amount, currency, line items)
- [ ] System validates extracted data against expense policies with cited policy clauses via RAG
- [ ] Foreign currency amounts are converted to SGD using live exchange rates
- [ ] Low-confidence VLM extractions trigger clarification questions to claimant
- [ ] Claimant can confirm or correct extracted fields before submission
- [ ] Submitted claims are audited against org-level policies (budgets, spending limits, approval thresholds)
- [ ] Submitted claims are checked for duplicate receipts and anomalous patterns against historical data
- [ ] Compliance and fraud checks run in parallel post-submission
- [ ] Advisor agent synthesizes compliance and fraud findings into risk assessment
- [ ] Clean claims are auto-approved; suspicious claims are escalated to human reviewer
- [ ] Policy violations trigger return to claimant with correction instructions and cited policy clauses
- [ ] Reviewer sees escalated claims with risk summary, compliance findings, fraud evidence, and policy citations
- [ ] Reviewer can approve, reject, or return claims with comments
- [ ] Email notifications sent to claimants (returns, status updates) and reviewers (escalations)
- [ ] Claim data persisted to Postgres (claims, receipts, line items, history)
- [ ] System runs locally via Docker Compose (Chainlit app, Postgres, Qdrant, 4 MCP servers)

### Out of Scope

- Real SUTD policy documents — using synthetic policies for development and demo
- AWS/cloud deployment — local-only for course project; deferred to future milestone
- Authentication/authorization — not needed for course demo
- Mobile app — web-only via Chainlit
- SAP Concur integration — standalone system, no integration with existing SAP

## Context

This is a course project for SUTD 51.511 Multimodal Generative AI (March 2026). Team of 4 members: Nguyen Thanh Tung, Josiah Lau, James Oon, Sagar Pratap Singh.

The project proposal (NeurIPS format) is in `project-reports/proposal.tex`. It defines a 4-agent architecture with specific agentic design patterns per agent:
- Intake Agent: ReAct + Evaluator Gate (user-facing, pre-submission)
- Compliance Agent: Evaluator pattern (post-submission)
- Fraud Agent: Tool call pattern (post-submission)
- Advisor Agent: Reflection + Routing (post-submission)

Team approach: shared foundation first, then parallel agent development across team members. Clean interfaces between agents via LangGraph shared state (ClaimState TypedDict).

Previous planning context exists in `docs/project-context.md` with detailed phase breakdowns and 6 E2E test definitions.

Evaluation targets: submission time < 3 min, field accuracy > 95%. Baselines: single-prompt pipeline (Gemini) and manual SAP Concur workflow.

## Constraints

- **Tech stack**: Python throughout — LangGraph (orchestration), Chainlit (UI), OpenRouter (model API)
- **Models**: OpenRouter API with free model toggle — no self-hosting
- **Database**: Postgres 16 (new schema from scratch) + Qdrant (vector store for RAG)
- **MCP servers**: 4 separate Docker services — RAG (rag-mcp-server), DBHub, Frankfurter, Email
- **Currency API**: frankfurter.app (free, no API key)
- **Policy data**: Synthetic policies (SUTD-representative)
- **Budget**: Zero cost — all free-tier services and models
- **Timeline**: Course project with demo deadline

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph for orchestration | Native state machine with conditional routing, parallel execution, ReAct support — no additional SDK needed | — Pending |
| Chainlit for UI | Conversational AI interface with image upload, supports multiple personas | — Pending |
| OpenRouter for models | Toggle between free VLM/LLM models, no self-hosting complexity | — Pending |
| Postgres for claims data | Relational fits claims data well, new schema designed by team | — Pending |
| Qdrant for vector store | Production-ready, Docker-native, high performance for RAG | — Pending |
| MCP servers as separate Docker services | Clean separation for parallel team development, independent scaling | — Pending |
| Synthetic policies | Real SUTD policies not available; synthetic sufficient for demo | — Pending |
| Local-first deployment | Course demo runs locally via Docker Compose; AWS deferred | — Pending |
| Intake Agent first | Build incrementally — Intake is the MVP, all other agents consume its output | — Pending |

---
*Last updated: 2026-03-23 after initialization*
