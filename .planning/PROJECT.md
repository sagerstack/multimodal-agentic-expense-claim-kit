# Agentic Expense Claims

## What This Is

A multi-agent multimodal system that automates SUTD expense claim processing. Four AI agents (Intake, Compliance, Fraud, Advisor) orchestrated by LangGraph process receipt images, validate against policies, detect fraud, and route claims to auto-approve, return, or human review — through a custom FastAPI + HTMX web application with the "Neon Nocturne" dark theme design system.

## Core Value

Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes — replacing a 15-25 minute manual process with frequent rejections.

## Current Milestone: v2.0 UX Redesign + Full Pipeline

**Goal:** Replace Chainlit with a custom FastAPI + Jinja2 + HTMX frontend using Stitch-generated designs, migrate all validated intake functionality, then build the remaining agents (Compliance, Fraud, Advisor) and reviewer interface to complete the full claim processing pipeline.

**Target features:**
- Custom web UI with 4 pages: AI Chat Submission, Approver Dashboard, Audit & Transparency Log, Claim Review (Escalation)
- "Neon Nocturne" dark theme (Tailwind CSS, Manrope + Inter fonts, Material Symbols icons)
- SSE streaming for real-time chat, HTMX for dynamic page updates, Alpine.js for local state
- Compliance Agent (parallel post-submission policy audit)
- Fraud Agent (parallel duplicate detection)
- Advisor Agent (decision synthesis + approval routing)
- Reviewer interface with escalated claims, risk summary, approve/reject/return actions
- Audit trail with full agent decision transparency
- Email notifications for status changes
- Playwright browser E2E tests alongside existing ConversationRunner backend tests

## Requirements

### Validated

- ✓ EXTR-01: Claimant uploads receipt image via chat interface — v1.0
- ✓ EXTR-02: VLM extracts structured fields (merchant, date, amount, currency, line items, tax, payment method) — v1.0
- ✓ EXTR-03: Per-field confidence scores for VLM extractions — v1.0
- ✓ EXTR-04: Low-confidence fields trigger clarification request — v1.0
- ✓ EXTR-05: Claimant can confirm or correct extracted fields — v1.0
- ✓ EXTR-06: Foreign currency detection and conversion to SGD — v1.0
- ✓ EXTR-07: Claim stores both original and converted amounts — v1.0
- ✓ EXTR-08: Blurry/low-resolution image rejection with re-upload guidance — v1.0
- ✓ POLV-01: Synthetic SUTD expense policies covering meal caps, transport, GL codes — v1.0
- ✓ POLV-02: Policy documents embedded in Qdrant via RAG MCP server — v1.0
- ✓ POLV-03: Semantic search retrieves relevant policy clauses — v1.0
- ✓ POLV-04: Intake Agent validates claim against policies before submission — v1.0
- ✓ POLV-05: Policy violations flagged with cited clause and section reference — v1.0
- ✓ POLV-06: Spending limits, meal caps, category restrictions checked — v1.0
- ✓ POLV-07: Claimant can justify violations or correct claim — v1.0
- ✓ ORCH-01: LangGraph state machine with shared ClaimState — v1.0
- ✓ ORCH-02: Intake Agent implements ReAct + Evaluator Gate — v1.0
- ✓ ORCH-08: PostgreSQL checkpointer persists state after each node — v1.0
- ✓ DATA-01: Claims, receipts persisted to PostgreSQL via DB MCP server — v1.0
- ✓ DATA-04: Receipt images stored externally, path references in database — v1.0
- ✓ INFR-01: Docker Compose orchestrates all services — v1.0
- ✓ INFR-02: OpenRouter model client with configurable models via .env — v1.0
- ✓ INFR-03: All configuration from .env files, no hardcoded values — v1.0
- ✓ INFR-04: MCP servers as separate Docker services using FastMCP — v1.0

### Active

- [ ] Replace Chainlit with FastAPI + Jinja2 + HTMX web application
- [ ] AI Chat Submission page with SSE streaming, file upload, thinking panel, interrupt/resume
- [ ] Approver Dashboard page with KPIs, recent claims, AI efficiency metrics
- [ ] Audit & Transparency Log page with claim timeline and agent decision trail
- [ ] Claim Review (Escalation) page with risk summary, receipt display, approve/reject/return actions
- [ ] Shared layout: sidebar navigation, system status, "Neon Nocturne" Tailwind theme
- [ ] Compliance Agent (Evaluator pattern) for post-submission org-level policy audit
- [ ] Fraud Agent (Tool Call pattern) for duplicate receipt detection against historical data
- [ ] Compliance and Fraud execute in parallel (same LangGraph superstep)
- [ ] Advisor Agent (Reflection + Routing) synthesizes compliance/fraud findings into risk assessment
- [ ] Auto-approve clean claims, return violations to claimant, escalate suspicious to reviewer
- [ ] Reviewer can approve, reject, or return claims with comments
- [ ] Email notifications for returns, escalations, and final decisions
- [ ] Audit trail logs all agent decisions, state changes, routing outcomes
- [ ] Historical claims queryable for fraud detection
- [ ] Playwright browser E2E tests for all 4 pages
- [ ] ConversationRunner backend regression tests preserved

### Out of Scope

- Light theme / theme toggle — dark only for this milestone, revisit later
- Mobile responsive design — desktop only (Stitch designs are 1280px+ desktop)
- Real-time WebSocket — SSE is sufficient for streaming, simpler architecture
- React/Vue/SPA framework — vanilla HTMX + Alpine.js keeps stack Python-only
- Authentication/authorization — not needed for course demo
- AWS/cloud deployment — local-only for course project
- Behavioral pattern analysis — requires historical data seeding beyond course scope
- AI-generated receipt detection — high complexity, low demo value

## Context

This is a course project for SUTD 51.511 Multimodal Generative AI (March 2026). Team of 4 members: Nguyen Thanh Tung, Josiah Lau, James Oon, Sagar Pratap Singh.

v1.0 delivered a working intake pipeline with Chainlit UI. v2.0 replaces Chainlit with a custom multi-page web application using Google Stitch-generated designs, then completes the remaining 3 agents and reviewer interface.

The 4 Stitch HTML designs are in `docs/ux/` — self-contained HTML + Tailwind CSS with the full "Neon Nocturne" design system (colors, fonts, spacing). These serve as pixel-perfect templates for the Jinja2 conversion.

Backend architecture (LangGraph, MCP servers, Postgres, Qdrant) is unchanged from v1.0. Only the presentation layer (`app.py`) is being replaced.

Evaluation targets: submission time < 3 min, field accuracy > 95%. Baselines: single-prompt pipeline (Gemini) and manual SAP Concur workflow.

## Constraints

- **Tech stack**: Python throughout — LangGraph, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind CSS
- **UI source**: Stitch HTML designs in `docs/ux/` are the design spec — match them
- **Theme**: "Neon Nocturne" dark theme only (no light mode this milestone)
- **Models**: OpenRouter API with free model toggle — no self-hosting
- **Database**: Postgres 16 + Qdrant — schema extends from v1.0 via Alembic
- **MCP servers**: Same 4 Docker services from v1.0 (RAG, DB, Currency, Email)
- **Budget**: Zero cost — all free-tier services and models
- **Timeline**: Course project with demo deadline
- **No Chainlit**: Complete removal — FastAPI replaces all Chainlit functionality

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph for orchestration | Native state machine with conditional routing, parallel execution | ✓ Good (v1.0) |
| OpenRouter for models | Toggle between free VLM/LLM models, no self-hosting | ✓ Good (v1.0) |
| Postgres for claims data | Relational fits claims data, Alembic migrations | ✓ Good (v1.0) |
| Qdrant for vector store | Docker-native, high performance for RAG | ✓ Good (v1.0) |
| MCP servers as Docker services | Clean separation, independent scaling | ✓ Good (v1.0) |
| Chainlit for UI | Quick prototyping but limited to chat-only | ⚠️ Replaced in v2.0 |
| FastAPI + Jinja2 + HTMX for UI | Full multi-page app, Stitch designs as templates, Python-only stack | — Pending |
| SSE for chat streaming | Simpler than WebSocket, HTMX has native SSE extension | — Pending |
| Alpine.js for local state | Lightweight, no build step, handles upload progress and panel toggles | — Pending |
| Playwright for browser E2E | Industry standard, Python API, headless mode for CI | — Pending |
| Dark theme only | Reduces scope, "Neon Nocturne" is the primary design | — Pending |

---
*Last updated: 2026-03-30 after milestone v2.0 initialization*
