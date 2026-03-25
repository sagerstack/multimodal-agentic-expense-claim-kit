# Agentic Expense Claims

Multi-agent multimodal system that automates SUTD expense claim processing. Replaces the manual SAP Concur workflow (15-25 min per claim) with an AI-driven pipeline targeting <3 min submission time and >95% field extraction accuracy.

Four LangGraph agents process claims through a pipeline: **Intake** (receipt parsing, policy validation) -> **Compliance** + **Fraud** (parallel post-submission checks) -> **Advisor** (decision routing). Chainlit provides the chat UI, PostgreSQL persists state, Qdrant stores policy embeddings.

## Running the App

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Poetry (package manager)

### Quick Start (Docker Compose)

```bash
# Start all 7 services (app, postgres, qdrant, 4 MCP servers)
docker compose up -d --build

# Verify all services are healthy
docker compose ps
# All 7 should show (healthy): app, postgres, qdrant, mcp-rag, mcp-db, mcp-currency, mcp-email

# Run database migrations
docker compose exec app poetry run alembic upgrade head

# Ingest policy documents into Qdrant
python scripts/ingest_policies.py

# Open the UI
open http://localhost:8000
```

### Common Commands

```bash
# Run tests (from host, not Docker)
poetry run pytest tests/ -v

# Run tests with coverage
poetry run pytest --cov=agentic_claims --cov-report=term-missing

# Lint
poetry run ruff check src/ tests/

# Format
poetry run ruff format src/ tests/

# Stop services (preserves data)
docker compose down

# Stop and remove volumes (full reset - wipes Postgres + Qdrant data)
docker compose down -v

# Rebuild a specific service after code change
docker compose up -d --build mcp-rag

# View logs for a specific service
docker compose logs -f mcp-rag
```

### Running Without Docker (Local Dev)

```bash
# Requires Postgres and Qdrant running locally
poetry install
poetry run alembic upgrade head
python scripts/ingest_policies.py
poetry run chainlit run src/agentic_claims/app.py --host 0.0.0.0 --port 8000
```

## Configuration

All configuration is loaded from environment files via pydantic-settings (`src/agentic_claims/core/config.py`). No hardcoded values in source code.

| File | Purpose | Git tracked? |
|------|---------|-------------|
| `.env.example` | Template with placeholder values | Yes |
| `.env.local` | Local development values | No (gitignored) |
| `tests/.env.test` | Test configuration values | Yes |

### Required Environment Variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `POSTGRES_HOST` | `localhost` | PostgreSQL host (overridden to `postgres` in Docker) |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `agentic_claims` | Database name |
| `POSTGRES_USER` | `agentic` | Database user |
| `POSTGRES_PASSWORD` | `agentic_password` | Database password |
| `CHAINLIT_HOST` | `0.0.0.0` | Chainlit bind address |
| `CHAINLIT_PORT` | `8000` | Chainlit port |
| `APP_ENV` | `local` | Environment (local/prod) |
| `OPENROUTER_API_KEY` | `sk-or-...` | OpenRouter API key |
| `OPENROUTER_MODEL_LLM` | `qwen/qwen-2.5-72b-instruct` | Text LLM model (agent reasoning) |
| `OPENROUTER_MODEL_VLM` | `qwen/qwen-2.5-vl-72b-instruct` | Vision LLM model (receipt extraction) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base |
| `OPENROUTER_MAX_RETRIES` | `3` | LLM retry count |
| `OPENROUTER_RETRY_DELAY` | `2.0` | Seconds between retries |
| `QDRANT_HOST` | `localhost` | Qdrant host (overridden to `qdrant` in Docker) |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `SMTP_HOST` | `mailhog` | SMTP host (mailhog = local stub) |
| `SMTP_PORT` | `1025` | SMTP port |
| `SMTP_USER` | _(empty)_ | SMTP username (optional for local) |
| `SMTP_PASSWORD` | _(empty)_ | SMTP password (optional for local) |

### Docker Compose Host Overrides

The `.env.local` file uses `localhost` for Postgres/Qdrant (for local dev and running tests from the host). Docker Compose overrides these inside containers:

```yaml
# docker-compose.yml - app service
environment:
  POSTGRES_HOST: postgres    # Docker network hostname
  QDRANT_HOST: qdrant        # Docker network hostname
```

The `Settings` class in `src/agentic_claims/core/config.py` loads from `.env.local` by default. Tests override this with `tests/.env.test` via the `testSettings` fixture in `conftest.py`.

## Infrastructure (Docker Compose)

7 services orchestrated via `docker-compose.yml`:

| Service | Image | Host Port | Container Port | Purpose |
|---------|-------|-----------|----------------|---------|
| `app` | Built from `./Dockerfile` | 8000 | 8000 | Chainlit UI + LangGraph agents |
| `postgres` | `postgres:16-alpine` | 5432 | 5432 | Claims DB, LangGraph checkpointer |
| `qdrant` | `qdrant/qdrant:latest` | 6333 | 6333 | Vector store for policy embeddings |
| `mcp-rag` | Built from `./mcp_servers/rag` | 8001 | 8000 | Policy search MCP server |
| `mcp-db` | Built from `./mcp_servers/db` | 8002 | 8000 | Database operations MCP server |
| `mcp-currency` | Built from `./mcp_servers/currency` | 8003 | 8000 | Currency conversion MCP server |
| `mcp-email` | Built from `./mcp_servers/email` | 8004 | 8000 | Email notification MCP server |

All MCP servers use **Streamable HTTP** transport (MCP spec 2025-03-26 standard) with `FASTMCP_HOST: 0.0.0.0` for Docker port mapping. Health checks use `curl` against the `/mcp` endpoint (returns 406 for bare GET, confirming the server is up).

### Dependency Chain

```
postgres (healthy) ──┬── mcp-db (healthy) ──┐
                     │                       │
qdrant (healthy) ────┼── mcp-rag (healthy) ──┤
                     │                       ├── app
                     ├── mcp-currency (healthy)
                     │                       │
                     └── mcp-email (healthy) ─┘
```

The `app` service waits for all 6 dependencies to be healthy before starting.

### Volumes

| Volume | Mounted At | Purpose |
|--------|-----------|---------|
| `postgres_data` | `/var/lib/postgresql/data` | Persists database across restarts |
| `qdrant_data` | `/qdrant/storage` | Persists vector embeddings across restarts |
| `./src` | `/app/src` (app only) | Live reload of source code in dev |

## Database (PostgreSQL + Alembic)

### Models

Defined in `src/agentic_claims/infrastructure/database/models.py`:

| Table | Role | Key Columns |
|-------|------|-------------|
| `claims` | Aggregate root | claim_number, employee_id, status, total_amount, currency (default SGD) |
| `receipts` | Child of claim | merchant, date, total_amount, currency, image_path, line_items (JSONB), original_amount, original_currency, exchange_rate, converted_amount |
| `audit_log` | Event log | action, old_value, new_value, actor, timestamp |
| `alembic_version` | Migration tracking | version_num |

**Dual currency columns** on `receipts`: `original_amount`, `original_currency`, `exchange_rate`, `converted_amount` (all nullable — existing claims without conversion data preserved).

### Alembic Migrations

```bash
# Run migrations (inside Docker)
docker compose exec app poetry run alembic upgrade head

# Run migrations (local, needs POSTGRES_HOST=localhost)
poetry run alembic upgrade head

# Check current migration version
poetry run alembic current

# Create new migration from model changes
poetry run alembic revision --autogenerate -m "description"

# Downgrade one step
poetry run alembic downgrade -1

# Stamp existing schema (when tables exist but Alembic wasn't tracking)
poetry run alembic stamp head
```

**File locations**: `alembic.ini` (config), `alembic/env.py` (runtime config, loads Settings), `alembic/versions/` (migration scripts). Current head: `002_add_dual_currency_columns.py`.

The `alembic/env.py` imports `Settings` from the app and uses `postgres_dsn_async` (psycopg driver) for async migrations.

## Policy RAG (Qdrant + Ingestion Script)

### Policy Documents

5 markdown files in `src/agentic_claims/policy/`:

| File | Category | Content |
|------|----------|---------|
| `meals.md` | meals | Meal expense rules, daily caps |
| `transport.md` | transport | Transport expense rules |
| `accommodation.md` | accommodation | Accommodation rules |
| `office_supplies.md` | office_supplies | Office supply rules |
| `general.md` | general | General expense policies |

### Ingestion Script

`scripts/ingest_policies.py` — reads policies, chunks by `## Section` headers, embeds with SentenceTransformer, stores in Qdrant.

```bash
# Run from host (requires Qdrant on localhost:6333)
python scripts/ingest_policies.py

# Run with custom Qdrant URL (e.g., Docker internal)
QDRANT_URL=http://localhost:6333 python scripts/ingest_policies.py
```

**What it does**:
1. Connects to Qdrant, deletes and recreates the `expense_policies` collection
2. Reads all `.md` files from `src/agentic_claims/policy/`
3. Splits into chunks on `## Section` headers (max 400 words, 50-word overlap for long sections)
4. Embeds chunks using `sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors)
5. Upserts points to Qdrant with metadata: `{text, file, category, section}`

**Configuration** (via env vars or defaults):

| Variable | Default | Purpose |
|----------|---------|---------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant connection URL |
| `COLLECTION_NAME` | `expense_policies` | Qdrant collection name |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | SentenceTransformer model |

**Output**: ~35 points in `expense_policies` collection, 384-dim vectors, cosine distance.

### Verify Ingestion

```bash
# Check collection exists and has points
curl http://localhost:6333/collections/expense_policies | python -m json.tool
# Look for: points_count > 0, vector size 384, status "green"
```

## MCP Servers

All 4 MCP servers use [FastMCP](https://github.com/jlowin/fastmcp) with **Streamable HTTP** transport. Each runs as a separate Docker container exposing tools via the MCP protocol on port 8000 (mapped to different host ports).

### MCP RAG Server (port 8001)

**File**: `mcp_servers/rag/server.py`

Semantic search over policy embeddings in Qdrant.

| Tool | Signature | Purpose |
|------|-----------|---------|
| `searchPolicies` | `(query: str, limit: int = 5) -> list[dict]` | Semantic search, returns `{text, file, category, section, score}` |
| `getPolicyByCategory` | `(category: str) -> list[dict]` | Filter by category (meals, transport, etc.) |

**Resource**: `qdrant://health` — connection status and point count.

**Env vars** (set in docker-compose.yml):
- `QDRANT_URL`: `http://qdrant:6333`
- `COLLECTION_NAME`: `expense_policies`
- `EMBEDDING_MODEL`: `sentence-transformers/all-MiniLM-L6-v2`

**Note**: Uses `platform: linux/amd64` in docker-compose because sentence-transformers has issues on ARM.

### MCP DB Server (port 8002)

**File**: `mcp_servers/db/server.py`

Structured database operations for claims management.

| Tool | Signature | Purpose |
|------|-----------|---------|
| `executeQuery` | `(query: str) -> list[dict]` | Read-only SQL (SELECT only) |
| `insertClaim` | `(claimNumber, employeeId, status, totalAmount, currency="SGD") -> dict` | Create new claim |
| `updateClaimStatus` | `(claimId, newStatus, actor) -> dict` | Update status + audit log entry |
| `getClaimWithReceipts` | `(claimId) -> dict` | Fetch claim with nested receipts |

**Resource**: `postgres://health` — connection status and Postgres version.

**Env vars** (set in docker-compose.yml):
- `DATABASE_URL`: `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}`

### MCP Currency Server (port 8003)

**File**: `mcp_servers/currency/server.py`

Currency conversion using the [Frankfurter API](https://api.frankfurter.dev) (European Central Bank rates, free, no API key).

| Tool | Signature | Purpose |
|------|-----------|---------|
| `convertCurrency` | `(amount: float, fromCurrency: str, toCurrency: str = "SGD") -> dict` | Convert amount, returns `{originalAmount, convertedAmount, rate, date}` |
| `getSupportedCurrencies` | `() -> list[str]` | List supported currency codes |

**Resource**: `frankfurter://health` — API connectivity check.

**Env vars**: None required (Frankfurter API is public).

### MCP Email Server (port 8004)

**File**: `mcp_servers/email/server.py`

Email notifications for claim status changes.

| Tool | Signature | Purpose |
|------|-----------|---------|
| `sendEmail` | `(to: str, subject: str, body: str) -> dict` | Send email via SMTP |
| `sendClaimNotification` | `(to, claimNumber, status, message) -> dict` | Templated claim notification |

**Resource**: `smtp://health` — config mode (local-stub or production).

**Local dev mode**: Detects `mailhog`/`localhost` as SMTP_HOST and stubs emails (logs to console instead of sending).

**Env vars** (set in docker-compose.yml):
- `SMTP_HOST`: `${SMTP_HOST:-mailhog}`
- `SMTP_PORT`: `${SMTP_PORT:-1025}`
- `SMTP_USER`: `${SMTP_USER:-}`
- `SMTP_PASSWORD`: `${SMTP_PASSWORD:-}`

### Testing MCP Servers

```bash
# Quick connectivity check (406 = healthy, 000 = unreachable)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/mcp  # RAG
curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/mcp  # DB
curl -s -o /dev/null -w "%{http_code}" http://localhost:8003/mcp  # Currency
curl -s -o /dev/null -w "%{http_code}" http://localhost:8004/mcp  # Email
# 406 is expected — Streamable HTTP requires MCP client headers, not bare GET
```

## OpenRouter Client (LLM/VLM)

**File**: `src/agentic_claims/infrastructure/openrouter/client.py`

Async client wrapping OpenAI SDK pointed at OpenRouter.

| Method | Purpose | Default Model |
|--------|---------|---------------|
| `callLlm(messages, model?)` | Text generation with retry | `OPENROUTER_MODEL_LLM` |
| `callVlm(text, imageUrl, model?)` | Vision (image + text) with retry | `OPENROUTER_MODEL_VLM` |

Both methods support retry logic (configurable via `OPENROUTER_MAX_RETRIES` and `OPENROUTER_RETRY_DELAY`). Custom model can be passed per call.

**Usage**:
```python
from agentic_claims.core.config import getSettings
from agentic_claims.infrastructure.openrouter.client import OpenRouterClient

settings = getSettings()
client = OpenRouterClient(settings)

# Text LLM
response = await client.callLlm([{"role": "user", "content": "Summarize this receipt"}])

# Vision LLM (receipt image)
response = await client.callVlm("Extract fields from this receipt", "https://example.com/receipt.jpg")
```

## Graph Topology (LangGraph)

Defined in `src/agentic_claims/core/graph.py`. State in `src/agentic_claims/core/state.py`.

```
START -> intake -> evaluatorGate -> (submitted) -> postSubmission -> [compliance || fraud] -> advisor -> END
                                 -> (pending) -> END
```

- **intake** (`agents/intake/node.py`): ReAct agent with 5 tools. Processes receipt, validates against policy, handles clarifications.
- **evaluatorGate** (`graph.py`): Conditional router. Checks `claimSubmitted` flag — routes to post-submission pipeline or END (if still in conversation).
- **postSubmission**: Pass-through node enabling fan-out to parallel agents.
- **compliance** + **fraud** (`agents/compliance/node.py`, `agents/fraud/node.py`): Parallel fan-out from postSubmission (same LangGraph superstep). Status: stubs.
- **advisor** (`agents/advisor/node.py`): Fan-in node, waits for both, makes final decision. Status: stub.

### ClaimState

```python
class ClaimState(TypedDict):
    claimId: str                                        # Unique claim identifier
    status: str                                         # Lifecycle: draft -> submitted -> approved/returned/escalated
    messages: Annotated[list[AnyMessage], add_messages]  # Conversation history (append-only via reducer)
    extractedReceipt: Optional[dict]                    # VLM extraction output with fields + confidence
    violations: Optional[list[dict]]                    # Policy violations with cited clauses
    currencyConversion: Optional[dict]                  # Original and converted amounts
    claimSubmitted: Optional[bool]                      # Gate flag for routing to compliance/fraud
```

### Checkpointer

`AsyncPostgresSaver` persists graph state to PostgreSQL after each node execution. Creates its own tables in the database. Managed as an async context manager in `app.py` (entered on chat start, exited on chat end).

## Chainlit App

**File**: `src/agentic_claims/app.py`

| Handler | What it does |
|---------|-------------|
| `@cl.on_chat_start` | Creates compiled graph + checkpointer, generates claimId + threadId, stores in session |
| `@cl.on_message` | Handles image upload (base64 -> imageStore), interrupt resume, graph invocation, response streaming |
| `@cl.on_chat_end` | Closes checkpointer DB connection |

Each session gets a unique `thread_id` for checkpointer isolation and a unique `claim_id` for image store lookups.

**Image handling**: Receipt images are extracted from Chainlit `message.elements`, base64-encoded, and stored in the in-memory `imageStore` (keyed by claimId). The LLM only sees a text message referencing the claimId — the VLM tool retrieves the image directly from the store. This avoids embedding ~58K tokens of base64 data into the LLM's context window.

**Interrupt support**: The `askHuman` tool triggers a LangGraph interrupt. The app detects `__interrupt__` in the result, sends the clarification question to the user, and sets `awaiting_clarification = True`. On the next message, it resumes the graph with `Command(resume=...)` containing the user's response.

## Tests

```bash
# Run all 54 tests
poetry run pytest tests/ -v

# Run specific test module
poetry run pytest tests/test_database.py -v
poetry run pytest tests/test_graph.py -v
poetry run pytest tests/test_openrouter.py -v
poetry run pytest tests/test_policy_ingestion.py -v
poetry run pytest tests/test_intake_agent.py -v
poetry run pytest tests/test_intake_tools.py -v

# With coverage
poetry run pytest --cov=agentic_claims --cov-report=term-missing
```

| Module | Tests | What it covers |
|--------|-------|---------------|
| `test_database.py` | 7 | ORM model structure, relationships, JSONB column types, dual currency columns |
| `test_graph.py` | 6 | Graph execution, parallel fan-out, state preservation, evaluator gate routing |
| `test_openrouter.py` | 7 | Client instantiation, LLM/VLM call construction, retry logic |
| `test_policy_ingestion.py` | 5 | Chunking logic, metadata, long section splitting, all files parseable |
| `test_intake_agent.py` | 7 | ReAct agent creation, tool binding, system prompt, intakeNode state updates |
| `test_intake_tools.py` | 10 | searchPolicies, convertCurrency, submitClaim, askHuman MCP/tool invocations |
| `test_extract_receipt_fields.py` | 5 | VLM extraction, image quality gate, blurry rejection, error handling |
| `test_image_quality.py` | 4 | Laplacian blur detection, resolution checks, threshold validation |
| `test_mcp_client.py` | 3 | MCP HTTP client, tool call serialization, error handling |

Test config: `tests/.env.test` (separate DB name, fast retry delay). Fixture: `testSettings` in `conftest.py` loads from `.env.test`.

## Project Structure

```
src/agentic_claims/
├── app.py                                  # Chainlit entry point (image upload, interrupt support)
├── core/
│   ├── config.py                           # Settings (pydantic-settings, loads .env.local)
│   ├── state.py                            # ClaimState TypedDict (with Phase 2.1 fields)
│   ├── graph.py                            # StateGraph + evaluatorGate + checkpointer
│   └── imageStore.py                       # In-memory image store (claimId -> base64)
├── agents/                                 # One package per agent (vertical slice)
│   ├── intake/
│   │   ├── node.py                         # intakeNode() — ReAct agent with 5 tools
│   │   ├── prompts/
│   │   │   ├── agentSystemPrompt.py        # Intake agent system prompt
│   │   │   └── vlmExtractionPrompt.py      # VLM receipt extraction prompt
│   │   ├── tools/
│   │   │   ├── extractReceiptFields.py     # VLM receipt extraction with quality gate
│   │   │   ├── searchPolicies.py           # Policy search via RAG MCP server
│   │   │   ├── convertCurrency.py          # Currency conversion via MCP server
│   │   │   ├── submitClaim.py              # Claim submission via DB MCP server
│   │   │   └── askHuman.py                 # Human-in-the-loop via LangGraph interrupt
│   │   └── utils/
│   │       ├── imageQuality.py             # Laplacian blur + resolution checks
│   │       └── mcpClient.py               # HTTP client for MCP Streamable HTTP calls
│   ├── compliance/node.py                  # complianceNode() — stub
│   ├── fraud/node.py                       # fraudNode() — stub
│   └── advisor/node.py                     # advisorNode() — stub
├── infrastructure/
│   ├── database/models.py                  # SQLAlchemy ORM models (Claim, Receipt, AuditLog)
│   └── openrouter/client.py                # OpenRouter LLM/VLM async client with retry
└── policy/                                 # Expense policy documents (5 markdown files)
    ├── meals.md
    ├── transport.md
    ├── accommodation.md
    ├── office_supplies.md
    └── general.md

mcp_servers/
├── rag/server.py                           # Policy search (Qdrant + SentenceTransformers)
├── db/server.py                            # Database operations (claims CRUD)
├── currency/server.py                      # Currency conversion (Frankfurter API)
└── email/server.py                         # Email notifications (SMTP/stub)

scripts/
└── ingest_policies.py                      # RAG ingestion: policies -> chunks -> embeddings -> Qdrant

alembic/
├── env.py                                  # Migration runtime (loads Settings, async psycopg)
└── versions/
    ├── 001_initial_schema.py               # Initial tables: claims, receipts, audit_log
    └── 002_add_dual_currency_columns.py    # Add original_amount, original_currency, exchange_rate, converted_amount to receipts

tests/
├── .env.test                               # Test environment config
├── conftest.py                             # testSettings fixture
├── test_database.py                        # ORM model tests (7)
├── test_graph.py                           # Graph + evaluator gate tests (6)
├── test_openrouter.py                      # LLM client tests (7)
├── test_policy_ingestion.py                # Chunking/ingestion tests (5)
├── test_intake_agent.py                    # ReAct agent + intakeNode tests (7)
├── test_intake_tools.py                    # MCP tool invocation tests (10)
├── test_extract_receipt_fields.py          # VLM extraction + quality gate tests (5)
├── test_image_quality.py                   # Blur detection + resolution tests (4)
└── test_mcp_client.py                      # MCP HTTP client tests (3)
```

## Intake Agent (Phase 2.1)

**Package**: `src/agentic_claims/agents/intake/`

Fully implemented ReAct agent using `langgraph.prebuilt.create_react_agent`. The LLM (`OPENROUTER_MODEL_LLM`) handles agent reasoning and tool selection. The VLM (`OPENROUTER_MODEL_VLM`) is called only by the `extractReceiptFields` tool — the receipt image never enters the LLM's context window.

### Tools

| Tool | File | MCP Server | Purpose |
|------|------|-----------|---------|
| `extractReceiptFields` | `tools/extractReceiptFields.py` | — (direct VLM call) | Image quality gate + VLM receipt extraction |
| `searchPolicies` | `tools/searchPolicies.py` | `mcp-rag:8001` | Semantic policy search via Qdrant |
| `convertCurrency` | `tools/convertCurrency.py` | `mcp-currency:8003` | Currency conversion via Frankfurter API |
| `submitClaim` | `tools/submitClaim.py` | `mcp-db:8002` | Persist claim + receipt to PostgreSQL |
| `askHuman` | `tools/askHuman.py` | — (LangGraph interrupt) | Human-in-the-loop for field confirmation |

### Image Quality Gate

`utils/imageQuality.py` — OpenCV-based pre-check before VLM call:
- **Blur detection**: Laplacian variance < threshold → reject as blurry
- **Resolution check**: Width < `IMAGE_MIN_WIDTH` or height < `IMAGE_MIN_HEIGHT` → reject

### MCP Client

`utils/mcpClient.py` — HTTP client for calling MCP Streamable HTTP servers. Used by `searchPolicies`, `convertCurrency`, and `submitClaim` tools to call their respective MCP servers.

### Image Store

`core/imageStore.py` — Module-level dict (`claimId -> base64`). The Chainlit app stores the receipt image here; the `extractReceiptFields` tool retrieves it by claimId. This decouples image data from the LLM context window (avoids ~58K token overflow).

## Writing a New Agent Node

Every agent lives in its own package under `src/agentic_claims/agents/`. Follow this pattern:

### 1. Create the package

```
src/agentic_claims/agents/your_agent/
├── __init__.py
└── node.py
```

### 2. Write the node function

```python
"""Your agent node - brief description of purpose."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def yourAgentNode(state: ClaimState) -> dict:
    claimId = state["claimId"]

    # Do your agent's work here
    result = "Your agent's output"

    # Return partial state update
    # messages uses add_messages reducer (APPENDED, not replaced)
    # Other keys (status, claimId) are replaced on write
    return {"messages": [AIMessage(content=result)]}
```

### 3. Wire into the graph

In `src/agentic_claims/core/graph.py`:

```python
from agentic_claims.agents.your_agent.node import yourAgentNode

# Inside buildGraph():
builder.add_node("your_agent", yourAgentNode)
builder.add_edge("some_previous_node", "your_agent")
builder.add_edge("your_agent", "some_next_node")
```

### Key patterns

- **CamelCase naming** for all functions, variables, classes, and tests
- **Async nodes** — all node functions must be `async def`
- **Partial state updates** — only return the keys you want to change
- **Messages accumulate** — the `add_messages` reducer appends new messages to the list
- **Status transitions** — only set `status` if your node changes the claim lifecycle stage
- **No infrastructure imports in agent nodes** — agents should not import config, database, or infrastructure directly. Use tools/MCP or pass data through state.

## Project Phases and Milestones

| Document | Location | Purpose |
|----------|----------|---------|
| Project context | `docs/project-context.md` | Objective, architecture, milestones, decisions |
| Roadmap | `.planning/ROADMAP.md` | Phase breakdown with success criteria and plan status |
| Current state | `.planning/STATE.md` | Which phase is active, overall progress |
| Phase plans | `.planning/phases/{phase}/` | Detailed execution plans per phase |
| Requirements | `.planning/REQUIREMENTS.md` | Full requirements list (49 requirements) |
| Research | `.planning/research/` | Architecture, stack, features, pitfalls research |

### Phase Status

| Phase | Status |
|-------|--------|
| 1. Foundation Infrastructure | Complete |
| 2. Supporting Infrastructure | Complete (UAT passed) |
| 2.1. Intake Agent + Receipt Processing | Complete (UAT passed) |
| 4. Compliance + Fraud Agents | Not started |
| 5. Advisor Agent + Reviewer Flow | Not started |
| 6. Evaluation + Demo | Not started |

## Code Standards

- **Package manager**: Poetry. All commands via `poetry run`. Never use pip, hatchling, or setuptools.
- **Architecture**: Vertical slice + DDD. Each agent is its own package.
- **Naming**: CamelCase everywhere (functions, variables, classes, tests).
- **Testing**: TDD (red-green-refactor). Coverage >= 90%. Tests in `tests/` with `pytest-asyncio`.
- **Configuration**: No hardcoded values. All config from `.env.local` via pydantic-settings.
- **Domain purity**: Agent nodes must not import infrastructure (config, database) directly.
- **Git**: Feature branches per story, merge latest main before push.
- **MCP Transport**: Streamable HTTP (not SSE). All MCP servers use `mcp.run(transport="streamable-http")`.

---

## Project Memory

Agents read and write cross-session knowledge to `docs/project_notes/`:

| File | Read By | Written By |
|------|---------|-----------|
| `bugs.md` | Critical Analyst, Developer, QA | Developer, QA |
| `decisions.md` | BA, Architect, Critical Analyst, Developer | Architect |
| `key_facts.md` | Architect, Developer | Architect, Developer |
| `issues.md` | BA | QA |
