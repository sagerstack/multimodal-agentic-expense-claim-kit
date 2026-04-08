# Agentic Expense Claims

Multi-agent multimodal system that automates SUTD expense claim processing. Replaces the manual SAP Concur workflow (15-25 min per claim) with an AI-driven pipeline targeting <3 min submission time and >95% field extraction accuracy.

## How It Works

Four LangGraph agents process claims through a pipeline:

```
Receipt Upload -> Intake Agent -> Compliance + Fraud (parallel) -> Advisor -> Decision
```

- **Intake Agent** - Parses receipts via VLM, validates against policy, handles currency conversion, confirms with user
- **Compliance Agent** - Post-submission policy compliance checks
- **Fraud Agent** - Anomaly detection and fraud scoring
- **Advisor Agent** - Final decision routing (auto-approve / return / escalate)

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agents | LangGraph (Python) |
| LLM/VLM | OpenRouter (Qwen 2.5 72B) |
| Web UI | FastAPI + Jinja2 + HTMX + Tailwind |
| Database | PostgreSQL 16 |
| Vector Store | Qdrant (policy embeddings) |
| MCP Servers | FastMCP (RAG, DB, Currency, Email) |
| Package Manager | Poetry |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- An `.env.local` file (copy from `.env.example` and fill in your values)

```bash
cp .env.example .env.local
# Edit .env.local with your OPENROUTER_API_KEY and other settings
```

### Launch

The startup script brings the entire system from zero to ready in a single command:

```bash
# Normal startup (preserves existing data)
./scripts/startup.sh

# Clean restart (wipes volumes, re-ingests policies, truncates tables)
./scripts/startup.sh --reset
```

The script performs 8 steps automatically:

1. Stops any existing containers
2. Handles volume reset (if `--reset` flag)
3. Builds and starts all Docker Compose services
4. Waits for all 8 services to pass health checks
5. Runs Alembic database migrations
6. Truncates tables for clean state (if `--reset` flag)
7. Ingests policy documents into Qdrant
8. Verifies all routes and MCP server endpoints

Once complete, it follows the app logs. Press `Ctrl+C` to stop log tailing (services keep running).

### Service URLs

| Service | URL |
|---------|-----|
| App UI | http://localhost:8000 |
| Seq Logs | http://localhost:5341 |
| PostgreSQL | localhost:5432 |
| Qdrant | http://localhost:6333 |

### Stopping

```bash
# Stop services (preserves data)
docker compose down

# Stop and wipe all data
docker compose down -v
```

## Development

### Running Tests

```bash
poetry run pytest tests/ -v

# With coverage
poetry run pytest --cov=agentic_claims --cov-report=term-missing
```

### Lint and Format

```bash
poetry run ruff check src/ tests/
poetry run ruff format src/ tests/
```

### Running Without Docker

Requires PostgreSQL and Qdrant running locally:

```bash
poetry install
poetry run alembic upgrade head
python scripts/ingest_policies.py
poetry run chainlit run src/agentic_claims/app.py --host 0.0.0.0 --port 8000
```

## Infrastructure

8 services orchestrated via `docker-compose.yml`:

| Service | Port | Purpose |
|---------|------|---------|
| `app` | 8000 | FastAPI web UI + LangGraph agents |
| `postgres` | 5432 | Claims DB + LangGraph checkpointer |
| `qdrant` | 6333 | Vector store for policy embeddings |
| `mcp-rag` | 8001 | Policy search MCP server |
| `mcp-db` | 8002 | Database operations MCP server |
| `mcp-currency` | 8003 | Currency conversion MCP server |
| `mcp-email` | 8004 | Email notification MCP server |
| `seq` | 5341 | Structured log aggregation |

## User Roles

| Role | Landing Page | Capabilities |
|------|-------------|-------------|
| Employee (user) | `/` | Submit claims, upload receipts, track status |
| Reviewer | `/manage` | Review claims, approve/reject/escalate, view analytics |
