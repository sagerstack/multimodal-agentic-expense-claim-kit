# Phase 2: Supporting Infrastructure - Research

**Researched:** 2026-03-24
**Domain:** Infrastructure services (Database, MCP servers, Vector store, Model client)
**Confidence:** HIGH

## Summary

Phase 2 establishes the supporting infrastructure that all expense claim agents depend on: database schema with migrations, MCP servers for tool access, OpenRouter model client for LLM/VLM calls, and Qdrant vector store for policy retrieval. The research reveals a mature ecosystem of off-the-shelf MCP servers, well-established patterns for async Postgres with Alembic, and production-ready tools for vector search.

**Key findings:**
- **MCP Servers**: Multiple off-the-shelf options exist for all 4 required capabilities (Qdrant RAG, Postgres CRUD, Frankfurter currency, SMTP email). All can be deployed as Docker containers with FastMCP or existing implementations.
- **Alembic + Async Postgres**: Well-supported pattern using `alembic init -t async` with psycopg3. Existing project already has `langgraph-checkpoint-postgres` which uses psycopg3 async.
- **Qdrant**: Official Docker image, straightforward Docker Compose setup. sentence-transformers/all-MiniLM-L6-v2 (384 dimensions, cosine distance) is the standard embedding model for document retrieval.
- **OpenRouter**: OpenAI-compatible API at `https://openrouter.ai/api/v1/chat/completions`. Supports both text and vision (VLM) calls with same endpoint. Free tier available with rate limits.
- **Docker Compose**: Standard health check patterns with `depends_on: condition: service_healthy` for orchestrating 5+ services. Each service needs service-specific health check (pg_isready, HTTP endpoint checks).

**Primary recommendation:** Use off-the-shelf MCP servers where possible (Qdrant official server, Postgres MCP Pro, Frankfurter MCP, SMTP MCP server), deploy each as separate Docker container with SSE or streamable-HTTP transport, and implement health checks for proper startup ordering.

## Standard Stack

The established libraries/tools for this infrastructure domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastMCP | 3.1+ | MCP server framework | Official framework, Pythonic decorators, auto-schema generation. Downloaded 1M times/day. |
| Alembic | 1.18+ | Database migrations | De facto standard for SQLAlchemy migrations, supports async with psycopg3 |
| psycopg | 3.0+ | Postgres async driver | Modern async driver, already in project via langgraph-checkpoint-postgres |
| Qdrant | latest | Vector database | High-performance vector search, official Docker image, mature ecosystem |
| sentence-transformers | 3.1+ | Embedding models | 15,000+ pre-trained models on HuggingFace, standard for semantic search |
| openai (SDK) | 1.0+ | OpenRouter client | OpenRouter is OpenAI-compatible, reuse existing SDK patterns |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| qdrant-client | latest | Qdrant Python SDK | Programmatic collection management, ingestion pipeline |
| asyncpg | 0.29+ | Alternative Postgres driver | If psycopg3 has issues, but psycopg3 preferred for consistency with LangGraph |
| requests | 2.31+ | HTTP client for OpenRouter | If not using OpenAI SDK, simple retry logic |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastMCP | Raw MCP Python SDK | More boilerplate, no auto-schema generation. FastMCP is simpler. |
| sentence-transformers/all-MiniLM-L6-v2 | pplx-embed-v1 (Feb 2026) | Newer (Perplexity MIT), but MiniLM is proven, widely deployed, sufficient for policy docs |
| Qdrant | pgvector (Postgres extension) | Simpler stack (one less service), but Qdrant has better performance, official MCP server |
| psycopg3 | asyncpg | asyncpg is faster, but psycopg3 has better SQLAlchemy integration (Alembic requirement) |

**Installation:**
```bash
# MCP server dependencies
poetry add fastmcp

# Database dependencies (Alembic, psycopg already via langgraph-checkpoint-postgres)
poetry add alembic

# Vector store dependencies
poetry add qdrant-client sentence-transformers

# Model client (OpenAI SDK for OpenRouter)
poetry add openai

# Optional: If building custom MCP servers
poetry add httpx  # For async HTTP in MCP servers
```

## Architecture Patterns

### Recommended Project Structure
```
src/agentic_claims/
├── core/
│   ├── config.py           # Existing pydantic-settings config
│   ├── state.py            # Existing LangGraph state
│   └── graph.py            # Existing graph setup
├── infrastructure/
│   ├── database/
│   │   ├── models.py       # SQLAlchemy models (claims, receipts, audit_log)
│   │   └── session.py      # Async session factory
│   ├── openrouter/
│   │   └── client.py       # OpenRouter client with retry
│   └── qdrant/
│       ├── client.py       # Qdrant client wrapper
│       └── ingestion.py    # Policy embedding pipeline
├── policy/                  # Markdown policy files (ingested into Qdrant)
│   ├── meals.md
│   ├── transport.md
│   ├── accommodation.md
│   └── office_supplies.md
└── agents/                  # Existing agent stubs

alembic/                     # Alembic migrations directory
├── env.py                   # Async migration environment
├── script.py.mako
└── versions/
    └── 001_initial_schema.py

mcp_servers/                 # MCP server configurations (if building custom)
├── rag_server.py           # Wrapper for Qdrant official server (if needed)
├── db_server.py            # Wrapper for Postgres MCP (if needed)
└── requirements.txt        # MCP server deps (fastmcp, etc.)

docker-compose.yml           # All services: app, postgres, qdrant, 4 MCP servers
```

### Pattern 1: Alembic Async Migrations
**What:** Initialize Alembic with async template, use psycopg3 for migrations
**When to use:** Any project with async Postgres (like this one with AsyncPostgresSaver)
**Example:**
```python
# Initialize Alembic with async template
# Terminal:
# alembic init -t async alembic

# alembic/env.py (key sections)
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
import asyncio

# Import your models
from agentic_claims.infrastructure.database.models import Base

config = context.config
target_metadata = Base.metadata

def do_run_migrations(connection: Connection) -> None:
    """Run migrations in 'online' mode (against database)."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Create async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Pattern 2: FastMCP Server Structure
**What:** Declarative MCP server using FastMCP decorators
**When to use:** Building custom MCP servers (if off-the-shelf doesn't fit)
**Example:**
```python
# mcp_servers/rag_server.py
# Source: https://github.com/jlowin/fastmcp (FastMCP official docs)
from fastmcp import FastMCP
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

mcp = FastMCP("Qdrant RAG Server")

# Initialize Qdrant client and embedding model
qdrant = QdrantClient(url="http://qdrant:6333")
encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

@mcp.tool
def search_policies(query: str, limit: int = 5) -> list[dict]:
    """Search expense policies by semantic similarity."""
    query_vector = encoder.encode(query).tolist()
    results = qdrant.search(
        collection_name="expense_policies",
        query_vector=query_vector,
        limit=limit,
    )
    return [{"text": hit.payload["text"], "score": hit.score} for hit in results]

if __name__ == "__main__":
    # For Docker: use SSE transport on 0.0.0.0
    mcp.run(transport="sse", host="0.0.0.0", port=8000)
```

### Pattern 3: Docker Compose Health Checks
**What:** Service health checks with startup dependency ordering
**When to use:** Multi-service Docker Compose with 5+ containers
**Example:**
```yaml
# docker-compose.yml
# Source: https://docs.docker.com/compose/how-tos/startup-order/
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: expense_claims
      POSTGRES_USER: claims_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U claims_user -d expense_claims"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:6333/healthz || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  mcp-rag:
    build: ./mcp_servers/rag
    environment:
      QDRANT_URL: http://qdrant:6333
    depends_on:
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s

  app:
    build: .
    env_file: .env.local
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      mcp-rag:
        condition: service_healthy
    ports:
      - "8080:8080"

volumes:
  postgres_data:
  qdrant_data:
```

### Pattern 4: OpenRouter Client with Retry
**What:** OpenAI-compatible client for OpenRouter with simple retry logic
**When to use:** Any OpenRouter integration (text or vision calls)
**Example:**
```python
# src/agentic_claims/infrastructure/openrouter/client.py
# Source: https://openrouter.ai/docs/api/reference/overview
from openai import AsyncOpenAI
from pydantic_settings import BaseSettings
import asyncio
from typing import Optional

class OpenRouterConfig(BaseSettings):
    openrouter_api_key: str
    openrouter_model_llm: str = "meta-llama/llama-3.1-8b-instruct:free"
    openrouter_model_vlm: str = "meta-llama/llama-3.2-11b-vision-instruct:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    class Config:
        env_file = ".env.local"

class OpenRouterClient:
    """OpenRouter client with retry logic for LLM and VLM calls."""

    def __init__(self, config: OpenRouterConfig):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.openrouter_api_key,
            base_url=config.openrouter_base_url,
        )

    async def call_with_retry(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ) -> str:
        """Call OpenRouter with simple retry logic."""
        model = model or self.config.openrouter_model_llm

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(retry_delay)

        raise RuntimeError(f"Failed after {max_retries} retries")

    async def call_vlm(self, text: str, image_url: str) -> str:
        """Call vision-language model with image."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
        return await self.call_with_retry(messages, model=self.config.openrouter_model_vlm)
```

### Pattern 5: Qdrant Policy Ingestion
**What:** Embed markdown policy documents and store in Qdrant collection
**When to use:** Initial setup, policy updates
**Example:**
```python
# src/agentic_claims/infrastructure/qdrant/ingestion.py
# Source: Context7 (sentence-transformers patterns)
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from pathlib import Path
import hashlib

def chunk_markdown(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Chunk markdown with overlap (tokens approximated by words * 1.3)."""
    words = text.split()
    chunk_words = int(chunk_size / 1.3)
    overlap_words = int(overlap / 1.3)

    chunks = []
    for i in range(0, len(words), chunk_words - overlap_words):
        chunk = " ".join(words[i:i + chunk_words])
        chunks.append(chunk)

    return chunks

async def ingest_policies(policy_dir: Path, qdrant_url: str):
    """Ingest markdown policies from policy_dir into Qdrant."""
    client = QdrantClient(url=qdrant_url)
    encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    # Create collection if not exists
    try:
        client.create_collection(
            collection_name="expense_policies",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    except Exception:
        pass  # Collection exists

    points = []
    point_id = 0

    for policy_file in policy_dir.glob("*.md"):
        content = policy_file.read_text()
        chunks = chunk_markdown(content)

        for chunk in chunks:
            vector = encoder.encode(chunk).tolist()
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk,
                        "file": policy_file.name,
                        "hash": hashlib.md5(chunk.encode()).hexdigest(),
                    },
                )
            )
            point_id += 1

    client.upsert(collection_name="expense_policies", points=points)
    print(f"Ingested {len(points)} chunks from {policy_dir}")
```

### Anti-Patterns to Avoid
- **Hardcoded database schema in code**: Use Alembic migrations from day one. Schema changes must be versioned.
- **Building custom MCP servers when off-the-shelf exists**: Research existing servers first. Custom servers add maintenance burden.
- **No health checks in Docker Compose**: Services start in wrong order, race conditions, hard-to-debug failures.
- **Synchronous Alembic with async app**: Creates engine lifecycle mismatches. Use `alembic init -t async`.
- **No retry logic in OpenRouter client**: Network failures are common. Simple retry (3 attempts, 2s delay) prevents spurious errors.
- **Hand-rolling embedding models**: sentence-transformers has 15,000+ pre-trained models. Don't train from scratch.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP server framework | Raw socket handling, JSON-RPC protocol | FastMCP | Auto-schema generation, transport negotiation, protocol lifecycle. 1M downloads/day standard. |
| Database migrations | Manual SQL scripts, version tracking | Alembic | Async support, up/down migrations, autogenerate from models, SQLAlchemy integration. |
| Postgres async driver | Custom connection pooling | psycopg3 (already in project) | Already used by langgraph-checkpoint-postgres. Proven async support. |
| Vector database | In-memory numpy arrays, manual similarity | Qdrant | Production-ready, Docker support, official MCP server, HNSW indexing for speed. |
| Embedding models | Training transformer from scratch | sentence-transformers/all-MiniLM-L6-v2 | 384 dims, 80M downloads, proven for semantic search. 5x faster than mpnet, good quality. |
| OpenRouter HTTP client | Manual requests with custom retry | OpenAI SDK + simple retry wrapper | OpenRouter is OpenAI-compatible. Reuse proven SDK patterns. |
| Document chunking | Character-based splitting | RecursiveCharacterTextSplitter (LangChain) | Vectara study: chunking strategy impacts recall as much as embedding model choice. |
| Docker health checks | Process checks (container running?) | Service-specific checks (pg_isready, HTTP /health) | Process running ≠ service ready. Health checks prevent race conditions. |

**Key insight:** MCP ecosystem matured rapidly in 2025-2026. Off-the-shelf servers exist for most needs. Custom MCP servers should be exception, not default. FastMCP makes custom servers trivial if needed, but check availability first.

## Common Pitfalls

### Pitfall 1: Alembic env.py Not Async-Aware
**What goes wrong:** Run `alembic init` (default template), but app uses async Postgres. Migrations fail with "coroutine was never awaited" or "object is not callable" errors.

**Why it happens:** Default Alembic template uses synchronous SQLAlchemy engine. App uses async engine (AsyncPostgresSaver). Engine type mismatch.

**How to avoid:** Use `alembic init -t async alembic` to generate async-compatible env.py from start. Or manually update existing env.py to use `async_engine_from_config` and `asyncio.run()`.

**Warning signs:**
- Alembic commands work but app fails, or vice versa
- "RuntimeError: coroutine was never awaited" in alembic upgrade
- Migrations block event loop

### Pitfall 2: Docker Compose Service Dependency Without Health Checks
**What goes wrong:** App starts before Postgres is ready. Connection refused errors. App crashes on startup. Race conditions where "it works sometimes."

**Why it happens:** `depends_on` (without condition) only waits for container to start, not for service inside container to be ready. Postgres container starts instantly, but Postgres server takes 5-10 seconds to accept connections.

**How to avoid:** Add `healthcheck` to all services, use `depends_on: { condition: service_healthy }` for dependent services. Use service-specific health checks: `pg_isready` for Postgres, `curl /healthz` for Qdrant, HTTP endpoint for MCP servers.

**Warning signs:**
- "Connection refused" errors on first startup, disappear on retry
- Services work when started manually (docker compose up -d postgres && sleep 10 && docker compose up app)
- Flaky integration tests

### Pitfall 3: Wrong Qdrant Collection Configuration (Dimensions)
**What goes wrong:** Embed documents with sentence-transformers/all-MiniLM-L6-v2 (384 dims) but create collection with 768 dims (mpnet default). Upload fails with "dimension mismatch."

**Why it happens:** Different embedding models have different output dimensions. all-MiniLM-L6-v2 is 384, all-mpnet-base-v2 is 768. Collection dimensions must match model dimensions.

**How to avoid:** Check embedding model docs for output dimensions before creating collection. For all-MiniLM-L6-v2: `VectorParams(size=384, distance=Distance.COSINE)`. Test with single embedding first.

**Warning signs:**
- "Vector dimension mismatch" errors on upsert
- Collection creation succeeds, ingestion fails
- Qdrant client raises ValueError

### Pitfall 4: MCP Server Transport Misconfiguration
**What goes wrong:** Build MCP server with stdio transport (default), try to connect from Chainlit app running in different Docker container. Connection fails silently or "no response" errors.

**Why it happens:** stdio transport is for same-process communication (Claude Desktop, local CLI). Docker containers need network transport (SSE or streamable-HTTP). MCP servers default to stdio if not specified.

**How to avoid:** Explicitly configure transport for Docker deployment: `mcp.run(transport="sse", host="0.0.0.0", port=8000)`. Use 0.0.0.0 to bind to all interfaces (not localhost/127.0.0.1 which only accepts local connections). Document transport choice in docker-compose.yml.

**Warning signs:**
- MCP server container runs, but clients can't connect
- Health checks fail with "connection refused"
- Works locally, fails in Docker

### Pitfall 5: OpenRouter Rate Limits on Free Tier
**What goes wrong:** Use free OpenRouter models for testing. Hit rate limit (20 req/min) during dev or testing. Requests fail with 429 errors.

**Why it happens:** Free tier has 20 req/min limit. Purchase $10+ credits increases to 1000 :free requests/day. Easy to hit limit during active development or test suite runs.

**How to avoid:**
- Purchase $10 minimum credits ($10 = 1000 free requests/day)
- Implement retry with exponential backoff for 429 errors
- Use paid models for tests (avoid :free suffix)
- Cache responses during development
- Rate limit test suite (pytest-ratelimit or manual delays)

**Warning signs:**
- 429 Too Many Requests errors
- Requests succeed early in test run, fail later
- Works in production (paid tier), fails in dev (free tier)

### Pitfall 6: No Postgres Init Scripts for Schema Bootstrap
**What goes wrong:** Alembic migrations require tables to exist, but first startup has empty database. "relation does not exist" errors when app tries to query.

**Why it happens:** Alembic creates application tables, but LangGraph checkpoint tables (from AsyncPostgresSaver.setup()) need to exist first. Chicken-and-egg problem.

**How to avoid:** Two options:
1. Mount init script to `/docker-entrypoint-initdb.d/01-init.sql` that runs AsyncPostgresSaver.setup() equivalent SQL
2. Add startup logic in app to run checkpointer.setup() before first use
3. Alembic migration that runs checkpointer.setup() (not recommended, mixes concerns)

Prefer option 2 (app startup logic) for flexibility.

**Warning signs:**
- Fresh database startup fails
- "relation langgraph_checkpoint does not exist"
- Works after manual setup, fails on fresh deploy

## Code Examples

Verified patterns from official sources:

### Docker Compose with All Services
```yaml
# docker-compose.yml
# Full multi-service setup for Phase 2
version: '3.8'

services:
  # Database
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: expense_claims
      POSTGRES_USER: claims_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U claims_user -d expense_claims"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  # Vector database
  qdrant:
    image: qdrant/qdrant:latest
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:6333/healthz || exit 1"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  # MCP Server: RAG (Qdrant semantic search)
  mcp-rag:
    image: qdrant/mcp-server-qdrant:latest  # Official Qdrant MCP server
    environment:
      QDRANT_URL: http://qdrant:6333
      QDRANT_API_KEY: ${QDRANT_API_KEY}
      COLLECTION_NAME: expense_policies
      EMBEDDING_MODEL: sentence-transformers/all-MiniLM-L6-v2
    depends_on:
      qdrant:
        condition: service_healthy
    ports:
      - "8001:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 20s

  # MCP Server: Database (Postgres CRUD)
  mcp-db:
    image: crystaldba/postgres-mcp:latest  # Postgres MCP Pro
    environment:
      DATABASE_URI: postgresql://claims_user:${POSTGRES_PASSWORD}@postgres:5432/expense_claims
      ACCESS_MODE: unrestricted  # Dev mode, change to restricted for prod
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8002:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  # MCP Server: Currency conversion (Frankfurter API)
  mcp-currency:
    build:
      context: ./mcp_servers/currency
      dockerfile: Dockerfile
    environment:
      TRANSPORT: sse
      HOST: 0.0.0.0
      PORT: 8000
    ports:
      - "8003:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  # MCP Server: Email (SMTP notifications)
  mcp-email:
    build:
      context: ./mcp_servers/email
      dockerfile: Dockerfile
    environment:
      SMTP_HOST: ${SMTP_HOST}
      SMTP_PORT: ${SMTP_PORT}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      TRANSPORT: sse
      HOST: 0.0.0.0
      PORT: 8000
    ports:
      - "8004:8000"
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Main application
  app:
    build: .
    env_file: .env.local
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      mcp-rag:
        condition: service_healthy
      mcp-db:
        condition: service_healthy
      mcp-currency:
        condition: service_healthy
      mcp-email:
        condition: service_healthy
    ports:
      - "8080:8080"
    volumes:
      - ./src:/app/src
      - ./receipts:/app/receipts  # Receipt image storage
    command: chainlit run src/agentic_claims/app.py --host 0.0.0.0 --port 8080

volumes:
  postgres_data:
  qdrant_data:
```

### Alembic Initial Migration (Schema)
```python
# alembic/versions/001_initial_schema.py
"""Initial schema: claims, receipts, audit_log

Revision ID: 001
Revises:
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Claims table
    op.create_table(
        'claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_number', sa.String(50), nullable=False, unique=True),
        sa.Column('employee_id', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),  # draft, submitted, approved, returned, escalated
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='SGD'),
        sa.Column('submission_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approval_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_claims_employee_id', 'employee_id'),
        sa.Index('ix_claims_status', 'status'),
    )

    # Receipts table (line items as JSON)
    op.create_table(
        'receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('receipt_number', sa.String(50), nullable=False),
        sa.Column('merchant', sa.String(200), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_amount', sa.Numeric(10, 2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('image_path', sa.String(500), nullable=True),  # External filesystem path
        sa.Column('line_items', postgresql.JSONB(), nullable=False),  # [{description, amount, gl_code, category}, ...]
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.Index('ix_receipts_claim_id', 'claim_id'),
    )

    # Audit log table
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),  # status_change, field_update, comment_added
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('actor', sa.String(100), nullable=False),  # employee_id or system
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ondelete='CASCADE'),
        sa.Index('ix_audit_log_claim_id', 'claim_id'),
        sa.Index('ix_audit_log_timestamp', 'timestamp'),
    )

def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('receipts')
    op.drop_table('claims')
```

### Qdrant Ingestion Script
```python
# scripts/ingest_policies.py
"""Ingest synthetic SUTD expense policies into Qdrant."""
import asyncio
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

POLICY_DIR = Path("src/agentic_claims/policy")
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "expense_policies"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 512  # tokens (approx)
OVERLAP = 50  # tokens

def chunk_markdown(text: str) -> list[str]:
    """Recursive chunking with overlap (simplified)."""
    # Approximate tokens as words * 1.3
    words = text.split()
    chunk_words = int(CHUNK_SIZE / 1.3)
    overlap_words = int(OVERLAP / 1.3)

    chunks = []
    for i in range(0, len(words), chunk_words - overlap_words):
        chunk = " ".join(words[i:i + chunk_words])
        if chunk.strip():
            chunks.append(chunk)

    return chunks

def main():
    # Initialize clients
    client = QdrantClient(url=QDRANT_URL)
    encoder = SentenceTransformer(EMBEDDING_MODEL)

    # Create collection (384 dims for all-MiniLM-L6-v2, cosine distance)
    try:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        print(f"Created collection: {COLLECTION_NAME}")
    except Exception as e:
        print(f"Collection exists or error: {e}")

    # Ingest all markdown files
    points = []
    point_id = 0

    for policy_file in POLICY_DIR.glob("*.md"):
        print(f"Processing: {policy_file.name}")
        content = policy_file.read_text()
        chunks = chunk_markdown(content)

        for chunk in chunks:
            vector = encoder.encode(chunk).tolist()
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk,
                        "file": policy_file.name,
                        "category": policy_file.stem,  # meals, transport, etc.
                    },
                )
            )
            point_id += 1

    # Batch upload
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Ingested {len(points)} chunks from {len(list(POLICY_DIR.glob('*.md')))} files")

if __name__ == "__main__":
    main()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MCP stdio only | FastMCP multi-transport (stdio, SSE, HTTP) | FastMCP 2.0 (2025) | Docker deployment viable, remote MCP servers |
| Synchronous Alembic | Async template (`-t async`) | Alembic 1.7+ (2023) | Native async support, no engine mismatch |
| Manual MCP protocol | FastMCP decorators | FastMCP 1.0 → SDK (2024) | 10x less boilerplate, auto-schema |
| asyncpg only | psycopg3 async support | psycopg3 3.0 (2021) | Better SQLAlchemy integration, LangGraph uses it |
| sentence-transformers mpnet | all-MiniLM-L6-v2 default | 2023-2024 shift | 5x faster, 80M downloads, "good enough" for most use cases |
| SSE transport for MCP | Streamable-HTTP preferred | MCP 2025-2026 | SSE deprecated, HTTP more standard |
| pplx-embed (Feb 2026) | sentence-transformers/all-MiniLM-L6-v2 still dominant | Current | pplx-embed newer but MiniLM proven, widely deployed |

**Deprecated/outdated:**
- **SSE transport for MCP servers**: Streamable-HTTP is now preferred. SSE may lose client support. Migrate to `transport="http"`.
- **Manual MCP JSON-RPC**: FastMCP exists. Don't hand-roll protocol implementation.
- **synchronous Alembic env.py with async app**: Use `alembic init -t async` from start.

## Open Questions

Things that couldn't be fully resolved:

1. **Which off-the-shelf MCP servers to use for all 4 capabilities?**
   - What we know: Official Qdrant MCP server exists (FastMCP-based). Postgres MCP Pro supports CRUD. Frankfurter MCP server exists (FastMCP). SMTP MCP servers exist (Node.js-based).
   - What's unclear: Do all 4 servers work together in Docker Compose without conflicts? Are there version compatibility issues? Do they all support SSE/HTTP transport?
   - Recommendation: Test each server individually in Docker Compose first. If any server doesn't fit, build custom FastMCP server (examples exist for all 4 use cases). Document transport choice per server.

2. **Chunking strategy for policy documents**
   - What we know: RecursiveCharacterTextSplitter at 400-512 tokens with 10-20% overlap is the proven default. Markdown-aware chunking (split on headers first) outperforms naive splitting by 5-10% recall. Semantic chunking is expensive and not consistently better.
   - What's unclear: Do SUTD policies have clear section headers? How long are they? Should we chunk per-policy-file or treat all as single corpus?
   - Recommendation: Start with RecursiveCharacterTextSplitter (512 tokens, 50 overlap). If policies have ## headers, implement markdown-aware splitting (LangChain MarkdownTextSplitter). Measure retrieval quality with test queries before committing to strategy.

3. **Alembic vs Docker init scripts for LangGraph checkpoint tables**
   - What we know: LangGraph checkpointer needs tables (langgraph_checkpoint, etc.). AsyncPostgresSaver.setup() creates them. Docker init scripts run once on first startup. Alembic migrations run on every deploy.
   - What's unclear: Should checkpointer.setup() be Alembic migration (versioned with app schema) or Docker init script (infrastructure concern)? What if checkpointer schema changes in LangGraph update?
   - Recommendation: Run checkpointer.setup() in app startup code (first-run detection). Keeps concerns separated. If LangGraph schema changes, app handles it. Alembic only for application schema (claims, receipts, audit_log).

4. **OpenRouter free vs paid models for development**
   - What we know: Free models (:free suffix) have 20 req/min limit (or 1000/day with $10 credit purchase). Paid models have no platform rate limits. Free tier sufficient for initial dev, but test suites may hit limits.
   - What's unclear: Which models to use? Should we use :free for dev and paid for prod? Or buy credits from start?
   - Recommendation: Start with free models (meta-llama/llama-3.1-8b-instruct:free for LLM, llama-3.2-11b-vision-instruct:free for VLM). Purchase $10 credits when hitting limits. Test with free, production with paid. Make model names configurable (.env.local).

## Sources

### Primary (HIGH confidence)
- [FastMCP GitHub](https://github.com/jlowin/fastmcp) - FastMCP 3.1 framework docs, Docker deployment patterns
- [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) - Async migration configuration with psycopg3
- [OpenRouter API Reference](https://openrouter.ai/docs/api/reference/overview) - API format, authentication, VLM support
- [Qdrant Official MCP Server](https://github.com/qdrant/mcp-server-qdrant) - Features, configuration, embedding model support
- [Postgres MCP Pro](https://github.com/crystaldba/postgres-mcp) - CRUD capabilities, access modes
- [Frankfurter MCP](https://github.com/anirbanbasu/frankfurtermcp) - FastMCP implementation, Docker support
- [SMTP MCP Server](https://github.com/samihalawa/mcp-server-smtp) - Email capabilities, Node.js-based
- [Docker Compose docs - Service startup order](https://docs.docker.com/compose/how-tos/startup-order/) - Health checks, depends_on patterns
- [sentence-transformers HuggingFace](https://huggingface.co/sentence-transformers) - Embedding model library, 15,000+ models
- [LangGraph checkpoint-postgres](https://pypi.org/project/langgraph-checkpoint-postgres/) - AsyncPostgresSaver, psycopg3 usage

### Secondary (MEDIUM confidence)
- [FastMCP HTTP Deployment Guide](https://gofastmcp.com/deployment/http) - SSE vs streamable-HTTP transport
- [Qdrant Quickstart](https://qdrant.tech/documentation/quickstart/) - Docker setup, collection configuration
- [Qdrant Distance Metrics](https://qdrant.tech/course/essentials/day-1/distance-metrics/) - Cosine distance, vector dimensions
- [OpenRouter Pricing](https://openrouter.ai/pricing) - Free tier limits, credit pricing
- [OpenRouter Rate Limits](https://openrouter.ai/docs/api/reference/limits) - 20 req/min free, 1000/day with $10
- [Best Chunking Strategies 2026](https://www.firecrawl.dev/blog/best-chunking-strategies-rag) - Recursive 512 tokens, markdown-aware patterns
- [RAG Chunking Benchmark 2026](https://blog.premai.io/rag-chunking-strategies-the-2026-benchmark-guide/) - Vectara study, 400-512 tokens optimal
- [PostgreSQL Docker Init Scripts](https://hub.docker.com/_/postgres/) - /docker-entrypoint-initdb.d pattern
- [Docker Compose Health Checks Guide](https://last9.io/blog/docker-compose-health-checks/) - Best practices, common pitfalls
- [MCP Health Check Endpoint Guide](https://mcpcat.io/guides/building-health-check-endpoint-mcp-server/) - MCP-specific health check patterns

### Tertiary (LOW confidence - WebSearch only, mark for validation)
- [pplx-embed release (Feb 2026)](https://niranjanakella.medium.com/pplx-embed-qdrant-building-production-grade-semantic-search-with-quantization-cea9626b8c7c) - New Perplexity embedding model, MIT license. Not yet widely adopted vs all-MiniLM-L6-v2.
- [Qdrant v1.17 release (Feb 2026)](https://medium.com/@niranjanakella/pplx-embed-qdrant-building-production-grade-semantic-search-with-quantization-cea9626b8c7c) - Production reliability improvements. Not verified against official Qdrant changelog.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - FastMCP, Alembic, psycopg3, Qdrant, sentence-transformers all verified via official docs and GitHub repos
- Architecture: HIGH - Patterns from official Docker Compose docs, Alembic cookbook, FastMCP deployment guides
- MCP server availability: MEDIUM - Off-the-shelf servers exist and are documented, but haven't verified all 4 work together in Docker Compose
- Chunking strategy: MEDIUM - Multiple 2026 benchmarks agree on 400-512 tokens, but optimal strategy depends on actual policy document structure
- Pitfalls: HIGH - Docker health checks, Alembic async, Qdrant dimensions all verified from official sources and GitHub issues
- OpenRouter specifics: MEDIUM - API format verified, but VLM examples sparse in official docs. Rate limits verified.

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (30 days - infrastructure tooling relatively stable, but MCP ecosystem evolving rapidly)

---

**Next steps for planning:**
1. Select specific MCP servers (official Qdrant, Postgres MCP Pro, Frankfurter MCP, SMTP MCP - or build custom if needed)
2. Define Alembic migration strategy (single 001_initial_schema.py vs separate migrations per table)
3. Create sample policy documents (meals, transport, accommodation, office_supplies)
4. Define .env.local configuration schema (all required env vars for 7 services)
5. Plan Docker Compose health check implementation (specific endpoints per service)
6. Design OpenRouter client API (async context manager vs singleton vs dependency injection)
