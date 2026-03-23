# Phase 2: Supporting Infrastructure - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the supporting infrastructure that all agents depend on: database schema with Alembic migrations, MCP server setup (preferring off-the-shelf where possible), OpenRouter model client, Qdrant vector store with synthetic policy ingestion. No agent logic — just the foundation services and data layer.

This phase was split from the original Phase 2 scope. The Intake Agent user-facing work (VLM extraction, conversational flow, policy validation, receipt handling) moves to Phase 2.1.

</domain>

<decisions>
## Implementation Decisions

### DB Schema Design
- 2 tables: `claims` and `receipts`. Line items embedded as JSON array in receipts (not a separate table)
- Full audit trail: `created_at`, `updated_at` timestamps on all tables, plus a separate `audit_log` table tracking every status change with timestamp and actor
- Claims are never deleted — only transitioned through statuses (draft -> submitted -> approved/returned/escalated)
- Alembic migrations from day one. Versioned up/down scripts for all schema changes

### MCP Server Architecture
- MCP server stubs from the start — agents interact via MCP protocol, not direct library calls
- Prefer off-the-shelf MCP servers where possible. Only build custom if no existing server fits
  - RAG (Qdrant semantic search): check for existing MCP servers first
  - DBHub (claims DB access): check for existing MCP servers first
  - Frankfurter (currency conversion): use existing HTTP/API MCP server
  - Email (notifications): use existing email MCP server
- Each MCP server runs as its own Docker container (separate services in docker-compose.yml)
- Research phase should investigate available MCP servers for all 4 capabilities

### OpenRouter Model Client
- Single client class, model name loaded from `.env.local` config
- Supports both text (LLM) and image (VLM) calls through the same interface
- Simple retry with fixed delay (3 retries, 2-second delay between each)
- No fallback model strategy — just retry the configured model

### Policy Data Structure
- Source: Markdown files stored in `src/policy/` folder
- Core expense categories only: meals, transport, accommodation, office supplies
- Mix of hard caps and soft guidelines:
  - Some categories have explicit numerical caps (e.g., meals: $50/day)
  - Others have soft guidelines requiring justification (e.g., entertainment: "reasonable with approval")
- RAG ingestion pipeline reads from `src/policy/` and embeds into Qdrant
- Chunking strategy: Claude's discretion during research/planning

### Claude's Discretion
- Exact Qdrant collection configuration (dimensions, distance metric)
- Chunking strategy for policy documents
- OpenRouter client internal structure
- Alembic migration naming conventions
- Docker health check implementation for MCP servers
- Audit log table exact schema

</decisions>

<specifics>
## Specific Ideas

- Policy files live in `src/policy/` as markdown — the RAG ingestion pipeline reads from this folder
- Off-the-shelf MCP servers strongly preferred over custom builds

</specifics>

<deferred>
## Deferred Ideas

- Intake Agent UX (VLM extraction, conversational flow, policy validation, receipt handling) — moved to Phase 2.1
- Specific model selection (which OpenRouter models to use) — decided when Intake Agent needs them
- Policy content depth beyond core categories — expand if needed for E2E tests

</deferred>

---

*Phase: 02-intake-agent-receipt-processing*
*Context gathered: 2026-03-23*
