# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-23)

**Core value:** Claimant uploads a receipt and gets a validated, policy-compliant expense claim submitted in under 3 minutes
**Current focus:** Phase 2.5: Reasoning Panel + Model Upgrade

## Current Position

Phase: 2.5 of 9 (Reasoning Panel + Model Upgrade)
Plan: 3 of 5 in current phase
Status: In progress
Last activity: 2026-03-28 -- Completed 02.5-03 (Progressive streaming with Type A+B reasoning)

Progress: [████████████████████░] 22/49 plans complete (45% complete)

## Performance Metrics

**Velocity:**
- Total plans completed: 22
- Average duration: 8 min
- Total execution time: 2.97 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation Infrastructure | 2 | 7 min | 4 min |
| 2. Supporting Infrastructure | 2 | 42 min | 21 min |
| 2.1. Intake Agent | 3 | 21 min | 7 min |
| 2.2. Intake Agent Gap Closure | 5 | 85 min | 17 min |
| 2.3. Intake Agent UAT Fix | 5 | 10 min | 2 min |
| 2.4. CoT Thinking Panel + Bug Fixes | 4 | 14 min | 4 min |
| 2.5. Reasoning Panel + Model Upgrade | 3 | 14 min | 5 min |

**Recent Trend:**
- Last 5 plans: 3min, 2min, 3min, 8min, 3min
- Trend: UI streaming changes consistently 2-3min, system prompt longer (8min)

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
- 02.3-01: Agent-to-MCP adapter pattern with explicit field mapping dictionaries (CLAIM_FIELD_MAP, RECEIPT_FIELD_MAP)
- 02.3-01: Auto-generation of required MCP fields (claimNumber CLAIM-NNN, receiptNumber REC-NNN, status 'pending')
- 02.3-01: Receipt fields use MCP's actual parameter names without blind 'receipt' prefix (merchant not receiptMerchant)
- 02.3-02: Filter third-party loggers globally in setupLogging() (openai, httpx, httpcore, urllib3, asyncio to WARNING)
- 02.3-02: Detect 402 errors via multiple signals (status code "402", "credits", or "quota" keywords in error message)
- 02.3-02: Fallback model selection via useFallback parameter in getIntakeAgent() (clean separation without duplication)
- 02.3-02: Log fallback events with structured extra fields (primary_model, fallback_model, error for Seq queries)
- 02.3-03: Narration pattern before ALL tool calls (agent speaks before tool executes, creates transparency)
- 02.3-03: No bracket-notation placeholders in prompt (agent waits for tool results before presenting data)
- 02.3-03: Mandatory visible policy check message (user sees which policies were checked and result before summary)
- 02.3-03: Claim ID pre-generation in Step 10 (user sees claim number in summary before confirming)
- 02.3-03: Self-diagnosis protocol for tool errors (agent reads error, attempts self-correction, explains in user terms)
- 02.3-04: astream_events(version="v2") for streaming (event-based hooks for tool calls and LLM tokens)
- 02.3-04: Per-tool Step elements (open Step on on_tool_start, close with elapsed time on on_tool_end)
- 02.3-04: Real-time token streaming via cl.Message.stream_token() (no batch delay)
- 02.3-04: Interrupt detection via aget_state() after streaming (astream_events doesn't expose __interrupt__)
- 02.3-04: Fallback for nested graph (extract last AI message from state if eventCount == 0)
- 02.3-05: ConversationRunner uses ainvoke() not astream_events() for testing reliability (synchronous execution, simpler state management)
- 02.3-05: TurnResult dataclass captures messages, tool steps (StepRecords), and interrupt state for test assertions
- 02.3-05: Structural E2E assertions (tool ordering, CLAIM-NNN pattern, concept keywords) handle LLM non-determinism
- 02.3-05: .env.e2e uses localhost:8001-8004 MCP URLs matching Docker Compose port mappings for host-based CLI execution
- 02.3-05: E2E test handles both interrupt (askHuman) and non-interrupt agent behavior for robustness
- 02.4-01: certifi upgrade after poetry dependencies install (not before) to avoid build-time SSL issues
- 02.4-01: Reset claim_number_seq gracefully (DO $$ exception handling) to support missing sequence
- 02.4-03: pendingToolCalls counter tracks active tool executions (robust finalResponse detection, fixes BUG-011)
- 02.4-03: Last-wins strategy for finalResponse assignment (intermediate generations safely overwritten)
- 02.4-03: Thinking panel summary shows tool count: "Thought for 5s · 3 tools" (prepares for reasoning token display)
- 02.4-04: E2E test now asserts CLAIM-NNN in Phase 3 (after submitClaim) not Phase 2 (agent no longer generates claim numbers)
- 02.5-01: QwQ-32B as primary LLM via OpenRouter (qwen/qwq-32b provides Type B reasoning tokens for thinking panel)
- 02.5-01: Temperature configurable per model type (0.3 for reasoning models, lower than 0.7 for conversational)
- 02.5-01: Max tokens increased to 8192 for QwQ (reasoning models produce verbose output with explicit thinking)
- 02.5-01: getClaimSchema tool for dynamic schema discovery (queries information_schema.columns for claims and receipts metadata)
- 02.5-01: getClaimSchema as first tool in agent (signals schema awareness is foundational for schema-driven prompting)
- 02.5-02: System prompt v2 calls getClaimSchema first every turn (schema-driven field mapping replaces hardcoded list)
- 02.5-02: Convert ALL monetary values individually via convertCurrency (total AND tax, never batch or manual calculations)
- 02.5-02: Capture justification for policy violations in summary and intakeFindings (audit trail for compliance)
- 02.5-02: Capture remarks from upload description in summary and intakeFindings (preserves user context)
- 02.5-03: Type A reasoning captured (tokenBuffer before tool calls) instead of discarding (provides visibility into agent reasoning)
- 02.5-03: Type B reasoning tokens captured from chunk.additional_kwargs or chunk.response_metadata (QwQ reasoning_content field)
- 02.5-03: Chronological thinkingEntries list replaces flat toolCalls (mixed-type list preserves temporal relationship: reasoning → tool → reasoning)
- 02.5-03: Progressive UX via placeholder message (create "Thinking...", update with full content after streaming — Chainlit limitation)
- 02.5-03: HTML escape all reasoning text (_escapeHtml) to prevent XSS from LLM-generated content
- 02.5-02: Immediate acknowledgment at turn start (user sees feedback while thinking panel streams)
- 02.5-04: Type A reasoning uses gray border (neutral), Type B uses purple (model-specific identity)
- 02.5-04: Type B includes "Model reasoning" label via ::before pseudo-element for clarity
- 02.5-04: Border opacity differs between themes (0.3 dark, 0.4 light) for optimal contrast

### Pending Todos

None yet.

### Blockers/Concerns

- REQUIREMENTS.md listed 37 v1 requirements but actual count is 49 -- corrected in traceability section
- Phase 1 CONTEXT.md gathered -- scope narrowed from full infra to orchestration-only foundation
- 01-01 BLOCKER RESOLVED: Docker daemon started, all services verified healthy
- 01-02 CONCERN: Python 3.14 + langchain-core Pydantic V1 compatibility warning (tests pass, monitor for issues)
- 02.1-03 CONCERN: LangGraph deprecation warning for create_react_agent (moved to langchain.agents, will migrate when stable)
- 02.3-01 BLOCKER RESOLVED: submitClaim field mapping fixed, 14-validation-error bug resolved
- 02.3-02 ISSUE F RESOLVED: Third-party logger noise in Seq eliminated via logger filtering
- 02.3-02 ISSUE H RESOLVED: Automatic OpenRouter 402 quota fallback prevents workflow death
- 02.3-03 ISSUE B RESOLVED: Agent now self-diagnoses tool errors with ERROR HANDLING protocol
- 02.3-03 ISSUE C RESOLVED: Policy check results now visible to user via mandatory Step 9 message
- 02.3-03 ISSUE D RESOLVED: Currency conversion ordering fixed (narrate → tool → result, no placeholders)
- 02.3-03 ISSUE E RESOLVED: Summary table placeholders removed, descriptive text used instead
- 02.3-04 ISSUE C RESOLVED: Empty Step panel replaced with per-tool Steps showing real-time progress
- 02.3-04 ISSUE D RESOLVED: Real-time token streaming eliminates batch delay
- 02.3-04 ISSUE E RESOLVED: Natural message/Step interleaving creates conversational rhythm
- 02.4-01 BUG-006 RESOLVED: Docker SSL certificate verification working via ca-certificates + certifi upgrade + REQUESTS_CA_BUNDLE
- 02.4-01 BUG-007 RESOLVED: Thinking panel visible in light mode via @media (prefers-color-scheme) CSS
- 02.4-03 BUG-011 RESOLVED: finalResponse detection now robust via pendingToolCalls tracking (intermediate generations no longer cause fragility)
- 02.4-02 BUG-008 RESOLVED: Duplicate submissions prevented via ON CONFLICT idempotent pattern with natural key
- 02.4-02 BUG-009 RESOLVED: Claim number collisions eliminated via PostgreSQL sequence (claim_number_seq)

## Session Continuity

Last session: 2026-03-28 13:21:33Z
Stopped at: Completed 02.5-03-PLAN.md (Progressive streaming with Type A+B reasoning)
Resume file: None

### Roadmap Evolution

- Phase 2.3 planned with 4 plans addressing 8 UAT-2 issues (Issues A-H) from Phase 2.2 verification
- Plan 02.3-05 added: CLI ConversationRunner + E2E intake narrative test with DIG receipt, enables programmatic testing of the full conversation flow without Chainlit
- Phase 2.4 scope expanded: Combined original reasoning tokens scope with 6 open bugs from Phase 2.3 UAT (BUG-006 through BUG-011). Bugs: SSL cert failure in Docker, thinking panel invisible in light mode, submitClaim double-call, CLAIM-NNN collisions, post-submission agent visibility (expected stub), finalResponse buffer fragility. See docs/project_notes/bugs.md for full details.
- Phase 2.4 UAT closed: 2 passed (Docker startup, SSL), 5 deferred to Phase 2.5. UAT surfaced 9 issues requiring architectural changes beyond 2.4 scope.
- Phase 2.5 inserted: Reasoning Panel + Model Upgrade. Scope: QwQ-32B model switch, Type A+B reasoning capture, progressive streaming, schema-driven intake prompt with getClaimSchema tool, system prompt redesign, deferred 2.4 tests. 9 issues total from UAT analysis.
