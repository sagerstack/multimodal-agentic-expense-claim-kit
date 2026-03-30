# Milestones

## v1.0: Intake Agent + Foundation (Archived)

**Completed:** 2026-03-30
**Phases:** 1, 2, 2.1, 2.2, 2.3, 2.4, 2.5 (closed early — 3/5 plans)
**Plans executed:** 24 of 26 (2 skipped in 2.5)

### What Shipped

- LangGraph orchestration with 4 stub agent nodes and parallel fan-out
- Docker Compose (app, Postgres, Qdrant, 4 MCP servers) with health checks
- PostgreSQL schema (claims, receipts, audit_log) with Alembic async migrations
- OpenRouter LLM/VLM client with retry and 402 fallback
- Qdrant policy ingestion (5 synthetic SUTD policies, semantic chunking)
- 4 MCP servers: RAG (Qdrant), DB (Postgres), Currency (Frankfurter), Email (SMTP stub)
- Intake Agent (ReAct + Evaluator Gate): VLM receipt extraction, image quality gate, policy validation, currency conversion, claim submission, human-in-the-loop
- Chainlit chat UI with streaming, per-tool-call thinking panel, interrupt/resume
- QwQ-32B model with Type A+B reasoning tokens in thinking panel
- Progressive streaming architecture
- Schema-driven intake prompt with getClaimSchema tool
- ConversationRunner for headless E2E testing
- Structured JSON logging with Seq

### Validated Requirements

EXTR-01 through EXTR-08, POLV-01 through POLV-07, ORCH-01, ORCH-02, ORCH-08, DATA-01, DATA-04, INFR-01 through INFR-04, CHAT-01, CHAT-03, CHAT-04

### Key Decisions

- Chainlit for UI (now being replaced in v2.0)
- LangGraph for orchestration (continues)
- OpenRouter via OpenAI SDK (continues)
- FastMCP with Streamable HTTP transport (continues)
- Vertical slice architecture per agent (continues)
- CamelCase naming throughout (continues)

### Skipped

- 02.5-04: CSS reasoning block styles (Chainlit-specific, replaced by new UI)
- 02.5-05: E2E browser verification (deferred to v2.0 with Playwright)

---
*Archived: 2026-03-30*
