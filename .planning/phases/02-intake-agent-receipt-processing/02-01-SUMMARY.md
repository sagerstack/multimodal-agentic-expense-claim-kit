---
phase: 02-supporting-infrastructure
plan: 01
subsystem: infrastructure
status: complete
completed: 2026-03-24
duration: 8min

tags:
  - database
  - sqlalchemy
  - alembic
  - openrouter
  - qdrant
  - docker

tech-stack:
  added:
    - alembic>=1.18
    - sqlalchemy>=2.0[asyncio]
    - openai>=1.0
    - qdrant/qdrant:latest (Docker)
  patterns:
    - SQLAlchemy 2.0 Mapped ORM with async support
    - Alembic async migrations with psycopg3
    - OpenRouter via OpenAI SDK with base_url override
    - Retry pattern with asyncio.sleep
    - Docker Compose health checks with service dependencies

key-files:
  created:
    - src/agentic_claims/infrastructure/database/models.py
    - src/agentic_claims/infrastructure/openrouter/client.py
    - alembic/env.py
    - alembic/versions/001_initial_schema.py
    - tests/test_database.py
    - tests/test_openrouter.py
  modified:
    - src/agentic_claims/core/config.py
    - docker-compose.yml
    - pyproject.toml
    - .env.example
    - tests/.env.test

requires:
  - 01-01: Settings with pydantic-settings pattern
  - 01-02: Docker Compose setup with Postgres

provides:
  - database-schema: 3 tables (claims, receipts, audit_log) with Alembic migrations
  - openrouter-client: Async client with retry for LLM and VLM calls
  - qdrant-service: Vector database container for policy RAG

affects:
  - 02-02: MCP server setup will use these database models and Qdrant service
  - All future agent phases: Will use OpenRouterClient for model calls
  - All future agent phases: Will use database models for persistence

decisions:
  - use-camelcase-python-snake-db: Use CamelCase for Python attributes with explicit name= for snake_case DB columns (maintains consistency with project convention while following SQL naming standards)
  - alembic-async-from-start: Initialize Alembic with async template to match psycopg3 async driver used by LangGraph
  - openrouter-via-openai-sdk: Use OpenAI SDK with base_url override rather than raw HTTP client (leverages proven SDK patterns, maintains compatibility)
  - retry-config-from-settings: Load retry count and delay from Settings rather than hardcoding (no default values, fail-fast configuration)
  - qdrant-in-compose-now: Add Qdrant service in this plan rather than waiting for 02-02 (enables parallel development, service available when needed)
---

# Phase 2 Plan 01: Database Schema & Infrastructure Summary

Database schema with Alembic migrations, OpenRouter client with retry, and Qdrant vector database service.

## What Was Built

### Database Layer
- **3 SQLAlchemy ORM models** with SQLAlchemy 2.0 Mapped style:
  - `Claim`: Aggregate root with claim_number, employee_id, status, amounts, dates
  - `Receipt`: Line items stored as JSONB array, links to Claim via FK
  - `AuditLog`: Full audit trail with action, old/new values, actor, timestamp
- **CamelCase Python attributes** with explicit `name=` parameter for snake_case DB columns
- **Bidirectional relationships** with cascade delete (receipts and audit logs delete when claim is deleted)
- **Alembic async migrations** initialized with `-t async` template for psycopg3 compatibility
- **Initial migration (001)** creates all 3 tables with indexes and foreign keys

### OpenRouter Client
- **OpenRouterClient class** using OpenAI SDK with `base_url` override
- **callLlm method**: Accepts messages array, returns text response, retries on failure
- **callVlm method**: Builds multimodal message with text and image_url, delegates to callLlm
- **Configurable retry logic**: max_retries and retry_delay loaded from Settings (not hardcoded)
- **Model override support**: Both methods accept optional model parameter

### Infrastructure Services
- **Qdrant container** added to docker-compose.yml with health check
- **Service dependencies**: App container depends on both postgres and qdrant being healthy
- **Volume persistence**: Both postgres_data and qdrant_data volumes created

### Configuration
- **Settings extended** with 8 new fields:
  - OpenRouter: api_key, model_llm, model_vlm, base_url, max_retries, retry_delay
  - Qdrant: host, port
- **Computed properties**: postgres_dsn_async, qdrant_url
- **No hardcoded defaults**: All config fields use `Field(...)` to fail fast if missing

### Tests
- **7 database model tests**: Model structure, relationships, JSONB column type
- **7 OpenRouter client tests**: Instantiation, API call construction, retry logic, exhaustion, VLM message format, custom model overrides
- **All tests pass**: 17 total tests (including existing test_graph.py)

## Implementation Decisions

### Decision 1: CamelCase Python, snake_case Database
**Context**: Project uses CamelCase everywhere, but SQL convention is snake_case.

**Options considered**:
1. CamelCase everywhere (breaks SQL conventions)
2. snake_case everywhere (breaks project conventions)
3. CamelCase Python with explicit name= for DB columns (hybrid approach)

**Decision**: Option 3 - Use `Mapped[str] = mapped_column(String(50), name="claim_number")` pattern.

**Rationale**: Maintains project consistency (CamelCase code) while respecting database naming standards (snake_case SQL). Explicit name= parameter makes mapping clear. SQLAlchemy 2.0 supports this pattern natively.

**Impact**: All model attributes use CamelCase in Python, snake_case in database. Queries reference Python names, migrations reference DB names.

### Decision 2: Alembic Async from Start
**Context**: App uses async Postgres (AsyncPostgresSaver from LangGraph), need migrations.

**Options considered**:
1. Default Alembic template (sync)
2. Async template with psycopg3
3. Manual async env.py

**Decision**: Option 2 - `alembic init -t async alembic`

**Rationale**: Official async template generates correct env.py structure. Matches psycopg3 driver used by LangGraph. Avoids engine lifecycle mismatches.

**Impact**: Migrations run async, compatible with app's async engine. env.py imports Settings to load database URL dynamically (no hardcoded connection string).

### Decision 3: OpenRouter via OpenAI SDK
**Context**: OpenRouter API is OpenAI-compatible, need client for LLM/VLM calls.

**Options considered**:
1. OpenAI SDK with base_url override
2. Raw HTTP requests with httpx
3. Custom client wrapper

**Decision**: Option 1 - AsyncOpenAI with base_url parameter.

**Rationale**: OpenRouter maintains OpenAI API compatibility. SDK handles auth, request formatting, error handling. Proven pattern, widely used. Less maintenance than custom client.

**Impact**: OpenRouterClient is thin wrapper around AsyncOpenAI. Retry logic added at wrapper level. VLM calls use same SDK with multimodal message format.

### Decision 4: Retry Config from Settings
**Context**: OpenRouter calls can fail transiently, need retry logic.

**Options considered**:
1. Hardcoded retry values (3 retries, 2s delay)
2. Load from Settings with defaults
3. Load from Settings with no defaults (Field(...))

**Decision**: Option 3 - Settings fields with `Field(...)`, fail fast if missing.

**Rationale**: Consistent with project's "no hardcoded defaults" principle (01-01 decision). Forces explicit configuration. Different environments can tune retry behavior (e.g., tests use 0.1s delay, prod uses 2s).

**Impact**: .env.local and tests/.env.test both require OPENROUTER_MAX_RETRIES and OPENROUTER_RETRY_DELAY. App won't start if missing.

### Decision 5: Qdrant in Compose Now
**Context**: Qdrant needed for Plan 02 MCP server setup.

**Options considered**:
1. Add Qdrant in Plan 02 (when actually needed)
2. Add Qdrant in Plan 01 (this plan)

**Decision**: Option 2 - Add now in infrastructure plan.

**Rationale**: Qdrant is infrastructure, not agent logic. Separates service setup from MCP wiring. Enables parallel development (database work doesn't block Qdrant work). Service available when Plan 02 starts.

**Impact**: docker-compose.yml has 3 services now (app, postgres, qdrant). App depends on both postgres and qdrant health checks. Volume created for Qdrant data persistence.

## Deviations from Plan

### Auto-fixed Issues

**None** - Plan executed exactly as written.

## Testing

All tests pass:
- 7 database model tests (structure, relationships, JSONB)
- 7 OpenRouter client tests (API calls, retry logic, VLM format)
- 3 existing graph tests (from Phase 01)
- **Total: 17 tests, 0 failures**

Manual verification:
- Database tables created (claims, receipts, audit_log)
- Postgres and Qdrant services healthy in Docker Compose
- Test claim inserted successfully (id=1)
- Qdrant health endpoint responds (http://localhost:6333/healthz)

## Performance

- **Duration**: 8 minutes
- **Task breakdown**:
  - Task 1 (Database + Qdrant): 6 minutes
  - Task 2 (OpenRouter client): 2 minutes
- **Commits**: 2 (one per task)

## Next Phase Readiness

**Phase 02 Plan 02 (MCP Server Setup) can proceed immediately:**
- Database schema exists for DBHub MCP server
- Qdrant service running for RAG MCP server
- OpenRouter client ready for agent model calls (if needed in Plan 02)

**Blockers**: None

**Concerns**: None

## Validation Checklist

- [x] 3 database tables exist (claims, receipts, audit_log)
- [x] Alembic migration creates tables with correct schema
- [x] OpenRouter client with retry logic passes all unit tests
- [x] Qdrant service healthy in Docker Compose
- [x] All configuration from .env (zero hardcoded defaults)
- [x] All tests pass: 17/17
- [x] Per-task commits with clear messages
- [x] No authentication gates encountered
- [x] No architectural decisions requiring user input

---

**Execution date**: 2026-03-24
**Completed by**: Claude Opus 4.6 (plan execution agent)
**Commits**:
- a587fef: Database models, Alembic migrations, Qdrant service
- fa41917: OpenRouter client with retry logic
