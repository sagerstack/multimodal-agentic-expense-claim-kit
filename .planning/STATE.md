# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Phase 2.1: Intake Agent + Receipt Processing

## Current Position

Phase: 2.1 of 6 (Intake Agent + Receipt Processing)
Plan: 1 of 3 in current phase
Status: In progress
Last activity: 2026-03-25 -- Completed 02.1-01-PLAN.md (VLM extraction foundation)

Progress: [█████...........] 36% (5/14 plans complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 11 min
- Total execution time: 0.93 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation Infrastructure | 2 | 7 min | 4 min |
| 2. Supporting Infrastructure | 2 | 42 min | 21 min |
| 2.1. Intake Agent | 1 | 6 min | 6 min |

**Recent Trend:**
- Last 5 plans: 5min, 8min, 34min, 6min
- Trend: Stabilizing (pure implementation plans consistently faster than infrastructure setup)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: 6 phases (split Phase 2 into infrastructure + Intake Agent) -- Foundation, Infrastructure, Intake, Compliance+Fraud, Advisor+Reviewer, Evaluation
- Roadmap: Corrected v1 requirement count from 37 to 49 (original REQUIREMENTS.md had wrong count)
- Phase 1 narrowed: Only LangGraph orchestration + 4 stub nodes + Docker Compose (Chainlit + Postgres). DB schema, MCP servers, OpenRouter, Qdrant moved to Phase 2
- Phase 1 plan count reduced from 3 to 2; Phase 2 split into Phase 2 (2 plans, infrastructure) and Phase 2.1 (3 plans, Intake Agent)
- 01-01: Use pydantic-settings for all configuration with zero hardcoded defaults
- 01-01: Vertical slice architecture - separate module per agent
- 01-01: Postgres DSN computed as property (not stored in .env) to avoid duplication
- 01-01: Hot reload via volume mount for development efficiency
- 01-02: Annotated reducers pattern for automatic message list merging (add_messages)
- 01-02: Parallel fan-out topology: Intake -> [Compliance || Fraud] -> Advisor
- 01-02: Checkpointer lifecycle managed per Chainlit chat session
- 01-02: Integration tests use graph.compile() without checkpointer for speed
- 01-02: AsyncPostgresSaver.from_conn_string() is async context manager — enter manually for session-scoped lifecycle
- 02-01: CamelCase Python attributes with explicit name= for snake_case DB columns (maintains project convention while respecting SQL standards)
- 02-01: Alembic async template from start to match psycopg3 async driver (avoids engine lifecycle mismatches)
- 02-01: OpenRouter via OpenAI SDK with base_url override (proven pattern, maintains compatibility)
- 02-01: Retry config from Settings with no defaults (consistent with fail-fast configuration principle)
- 02-01: Qdrant service added in infrastructure plan (enables parallel development, available when needed)
- 02-02: FastMCP for all MCP servers with Streamable HTTP transport (MCP spec 2025-03-26 standard, replaces deprecated SSE)
- 02-02: Section-aware markdown chunking preserves ## Section headers as metadata (agents can cite specific policy sections)
- 02-02: CPU-only PyTorch for RAG embeddings (avoid 10GB+ CUDA dependencies when CPU inference is sufficient)
- 02-02: MCP server health checks use curl against /mcp endpoint (Streamable HTTP returns immediate 406, unlike SSE which hung)
- 02.1-01: Image quality gate before VLM call (reject blurry/low-res early to save API costs and provide clear feedback)
- 02.1-01: Laplacian variance for blur detection (standard OpenCV technique, fast, configurable threshold)
- 02.1-01: Per-field confidence scores from VLM (enables selective human-in-loop for low-confidence fields)
- 02.1-01: MCP client returns content list or error dict (no exceptions for connection failures, graceful error handling)

### Pending Todos

None yet.

### Blockers/Concerns

- REQUIREMENTS.md listed 37 v1 requirements but actual count is 49 -- corrected in traceability section
- Phase 1 CONTEXT.md gathered -- scope narrowed from full infra to orchestration-only foundation
- 01-01 BLOCKER RESOLVED: Docker daemon started, all services verified healthy
- 01-02 CONCERN: Python 3.14 + langchain-core Pydantic V1 compatibility warning (tests pass, monitor for issues)

## Session Continuity

Last session: 2026-03-25T07:08:45Z
Stopped at: Completed 02.1-01-PLAN.md (VLM extraction foundation)
Resume file: None
