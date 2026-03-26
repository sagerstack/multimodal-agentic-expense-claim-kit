# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Phase 2.2: Intake Agent Gap Closure

## Current Position

Phase: 2.2 of 7 (Intake Agent Gap Closure)
Plan: 5 of 6 in current phase
Status: In progress
Last activity: 2026-03-26 -- Completed 02.2-05-PLAN.md (Intake Agent UX Redesign)

Progress: [███████████......] 65% (11/17 plans complete, Phase 2.2 gap closure in progress)

## Performance Metrics

**Velocity:**
- Total plans completed: 11
- Average duration: 13 min
- Total execution time: 2.47 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation Infrastructure | 2 | 7 min | 4 min |
| 2. Supporting Infrastructure | 2 | 42 min | 21 min |
| 2.1. Intake Agent | 3 | 21 min | 7 min |
| 2.2. Intake Agent Gap Closure | 4 | 77 min | 19 min |

**Recent Trend:**
- Last 5 plans: 4min, 65min, 4min, 4min
- Trend: Infrastructure changes take longer (19min avg Phase 2.2), UX/prompt changes very fast (4min)

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
- 02.1-02: submitClaim dual-call pattern (insertClaim -> insertReceipt with FK link ensures no orphaned receipts)
- 02.1-02: Dual currency columns nullable (existing claims without conversion data preserved during migration)
- 02.1-02: askHuman uses LangGraph interrupt() synchronously (blocks agent until user responds, standard HITL primitive)
- 02.1-03: ChatOpenAI replaces OpenRouterClient (langchain_openai.ChatOpenAI with base_url override provides better LangChain integration)
- 02.1-03: Intermediate postSubmission node for evaluator gate fan-out (LangGraph conditional edges don't support list values in routing dict)
- 02.1-03: Base64 encoding in HumanMessage content (Chainlit provides binary image data, agent tools expect base64 strings)
- 02.1-03: intakeNode detects submitClaim success by scanning ToolMessages in result (tools don't mutate state directly in LangGraph)
- 02.2-01: Atomic claim+receipt submission via merged insertClaim MCP tool (single transaction prevents partial state, eliminates FK race conditions)
- 02.2-01: Structured JSON logging with python-json-logger (standardized fields enable log aggregation and correlation)
- 02.2-01: Seq dashboard for local log viewing (zero-config Docker image, excellent UI for structured logs)
- 02.2-01: intakeFindings JSONB column with GIN index (schema-free agent observations, queryable for audit trail)
- 02.2-02: System prompt structure SUCCESS CRITERIA first (LLM focuses on first content, makes criteria higher priority)
- 02.2-02: Few-shot examples only for complex steps (keeps prompt under token limit while providing clear format guidance)
- 02.2-02: Chainlit Step wrapping for collapsible CoT (cot="tool_call" shows Steps collapsed, user sees clean output)
- 02.2-02: Message filtering in Chainlit app (only send AI messages with content, skip ToolMessages and empty messages)
- 02.2-04: Separate seq_ingestion_url for Docker-internal Seq access (seq_url is for browser, app needs http://seq/api/events/raw)
- 02.2-04: SeqHandler formats CLEF directly without JsonFormatter (Seq requires specific @t, @l, @mt keys)
- 02.2-04: Centralized logging setup in core/logging.py (app.py imports setupLogging, no inline duplicate)
- 02.2-05: Two-layer conversational model (USER-FACING OUTPUT + INTERNAL REASONING sections in system prompt)
- 02.2-05: Conditional step execution (cross-reference only runs if user provided description)
- 02.2-05: Message count tracking before graph invoke (slice result['messages'] by pre-invoke count for deduplication)
- 02.2-05: CoT separation (cotEntries captured in Step.output, userFacingMessages sent to main chat)
- 02.2-05: Confidence bucketing (High/Medium/Low instead of raw 0.95 scores for user-facing output)
- 02.2-05: Chainlit config.ui.cot="full" (show all Step elements by default, user can collapse)

### Pending Todos

None yet.

### Blockers/Concerns

- REQUIREMENTS.md listed 37 v1 requirements but actual count is 49 -- corrected in traceability section
- Phase 1 CONTEXT.md gathered -- scope narrowed from full infra to orchestration-only foundation
- 01-01 BLOCKER RESOLVED: Docker daemon started, all services verified healthy
- 01-02 CONCERN: Python 3.14 + langchain-core Pydantic V1 compatibility warning (tests pass, monitor for issues)
- 02.1-03 CONCERN: LangGraph deprecation warning for create_react_agent (moved to langchain.agents, will migrate when stable)

## Session Continuity

Last session: 2026-03-26
Stopped at: Completed 02.2-05-PLAN.md (Intake Agent UX Redesign)
Resume file: None
