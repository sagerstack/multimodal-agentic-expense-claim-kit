# Phase 1: Foundation Infrastructure - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

LangGraph orchestration skeleton with 4 stub agent nodes returning "Hello world", Docker Compose to run the stack (Chainlit app + Postgres for checkpointer), and project structure that enables parallel team development.

**NOT in Phase 1:** MCP servers, Qdrant, OpenRouter model client, full database schema (claims/receipts/line_items), policy ingestion. These move to later phases.

</domain>

<decisions>
## Implementation Decisions

### Scope reduction
- Phase 1 is ONLY orchestration foundation — not the full infrastructure originally scoped in ROADMAP.md
- MCP server stubs, Qdrant policy ingestion, Alembic migrations for claims schema, and OpenRouter client are deferred to Phase 2+
- Success criteria: `docker compose up` starts Chainlit + Postgres; a test claim flows through 4 stub agent nodes via LangGraph with state persisted to Postgres checkpointer

### Database schema & claim lifecycle
- Linear status flow: draft -> submitted -> processing -> approved/rejected/returned
- Agent findings (compliance, fraud) stored in a separate findings table (claim_id, agent, finding_type, details, timestamp) — not on the claims table
- Audit trail: both LangGraph Postgres checkpointer for orchestration replay AND a dedicated audit_events table for business-level queries
- Receipt images stored on filesystem (mounted volume), DB stores file path reference
- NOTE: Full schema (claims, receipts, line_items, findings, audit_events) is NOT built in Phase 1 — only Postgres + checkpointer tables. Schema moves to a later phase.

### Project structure
- Package name: `agentic_claims`
- Vertical slice per agent: `src/agentic_claims/agents/intake/`, `src/agentic_claims/agents/compliance/`, etc. — each with its own tools, node, prompts
- Shared infrastructure in `src/agentic_claims/core/` — graph definition, state, config, db
- MCP servers at `src/mcp/rag/`, `src/mcp/dbhub/`, etc. — sibling to agentic_claims package, not nested inside it
- State definition lives at `src/agentic_claims/core/state.py`

### ClaimState design
- Minimal skeleton for Phase 1: claim_id, status, messages list — expand as each agent phase is built
- Use LangGraph Annotated reducers (e.g., Annotated[list, add_messages]) — not plain TypedDict overwrites
- LangGraph checkpointer: Postgres (langgraph-checkpoint-postgres) — same Postgres instance, production-like from day one

### Graph topology
- Phase 1 includes parallel fan-out: Intake -> [Compliance || Fraud] -> Advisor
- All 4 nodes are stubs returning "Hello world" but the graph proves parallel execution works
- Conditional routing edges wired from the start

### Claude's Discretion
- Docker Compose configuration details (networks, volumes, health checks)
- Hot reload strategy for development
- Exact Chainlit app configuration
- Test structure and fixtures for Phase 1

</decisions>

<specifics>
## Specific Ideas

- "Just create an orchestration across 4 agents that returns Hello world" — keep Phase 1 minimal and focused
- Team needs to clone and `docker compose up` to have a working foundation for parallel agent development

</specifics>

<deferred>
## Deferred Ideas

- Full database schema (claims, receipts, line_items tables) with Alembic migrations — move to Phase 2 or a new pre-Intake phase
- MCP server stubs (RAG, DBHub, Frankfurter, Email) as Docker services — move to Phase 2+
- Qdrant setup and policy ingestion pipeline — move to Phase 2+
- OpenRouter model client with free model toggle — move to Phase 2+
- ROADMAP.md Phase 1 requirements (INFR-01 through POLV-02) need redistribution across updated phases

</deferred>

---

*Phase: 01-foundation-infrastructure*
*Context gathered: 2026-03-23*
