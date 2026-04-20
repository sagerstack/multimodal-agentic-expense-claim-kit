# Agentic Expense Claims

Multi-agent multimodal system that automates corporate expense claim processing. Replaces the manual SAP Concur workflow (15–25 min per claim) with an AI-driven pipeline targeting <3 min submission time and >95% field extraction accuracy.

An employee uploads a receipt, chats briefly with the Intake agent, and the system handles the rest: VLM extraction, currency conversion, policy retrieval, submission, fraud scoring, compliance review, and final routing (auto-approve / return / escalate).

## How It Works

Four LangGraph agents process claims through a pipeline:

```
Receipt Upload -> Intake -> [Compliance || Fraud] -> Advisor -> Decision
```

- **Intake Agent** — Parses receipts via VLM, validates against policy, handles currency conversion, confirms ambiguous fields with the user
- **Compliance Agent** — Post-submission policy compliance checks
- **Fraud Agent** — Anomaly detection and fraud scoring against claim history
- **Advisor Agent** — Final routing decision (auto-approve / return / escalate)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agents | LangGraph (Python) |
| LLM / VLM | OpenRouter (Qwen3 235B + Gemini 2.0 Flash) |
| Web UI | FastAPI + Jinja2 + HTMX + Tailwind |
| Database | PostgreSQL 16 |
| Vector Store | Qdrant (policy embeddings) |
| MCP Servers | FastMCP (RAG, DB, Currency, Email) |
| Observability | Seq (structured logs) |
| Evaluation | DeepEval + GPT-4o judge |
| Package Manager | Poetry |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ and Poetry (for running tests and evals from host)
- An `.env.local` file (copy from `.env.example` and fill in your values)

```bash
cp .env.example .env.local
# Edit .env.local with your OPENROUTER_API_KEY and other settings
```

### Launch

```bash
# Normal startup (preserves existing data)
./scripts/startup.sh

# Clean restart (wipes volumes, re-ingests policies, truncates tables)
./scripts/startup.sh --reset
```

The script brings the entire stack up in one command:

1. Stops any running containers
2. Handles volume reset (if `--reset`)
3. Builds and starts all 8 services
4. Waits for health checks to pass
5. Runs Alembic migrations
6. Truncates tables (if `--reset`)
7. Ingests policy documents into Qdrant
8. Verifies routes and MCP endpoints

Then it tails the app logs. `Ctrl+C` stops the tail; services keep running.

### Service URLs

| Service | URL |
|---------|-----|
| App UI | http://localhost:8000 |
| Seq Logs | http://localhost:5341 |
| PostgreSQL | localhost:5432 |
| Qdrant | http://localhost:6333 |

### Stopping

```bash
docker compose down        # preserves data
docker compose down -v     # wipes all volumes
```

## User Roles

| Role | Landing Page | Capabilities |
|------|--------------|--------------|
| Employee | `/` | Submit claims, upload receipts, track status |
| Reviewer | `/manage` | Review claims, approve / reject / escalate, analytics |

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

## Project Structure

```
agentic-expense-claims/
├── src/agentic_claims/          # Main application package
│   ├── core/                    # Graph topology, state, config, image store
│   ├── agents/                  # One package per agent (vertical slice + DDD)
│   │   ├── intake/              # Receipt parsing, policy validation, conversation
│   │   ├── compliance/          # Post-submission policy compliance checks
│   │   ├── fraud/               # Anomaly detection and fraud scoring
│   │   ├── advisor/             # Final routing decision
│   │   └── shared/              # Cross-agent tools and utilities
│   ├── infrastructure/          # DB models, OpenRouter client (no domain logic)
│   ├── policy/                  # Expense policy markdown documents (5 files)
│   └── web/                     # FastAPI app, routers, SSE helpers, auth
│
├── mcp_servers/                 # FastMCP servers (each a Docker container)
│   ├── rag/                     # Qdrant-backed policy search
│   ├── db/                      # PostgreSQL claim CRUD
│   ├── currency/                # Frankfurter API currency conversion
│   └── email/                   # SMTP / stubbed email notifications
│
├── eval/                        # DeepEval evaluation harness
│   ├── run_eval.py              # Pipeline orchestrator (capture → score → report)
│   ├── src/                     # Benchmarks, metrics, scoring, report generation
│   │   ├── capture/             # Browser-based agent output capture
│   │   └── metrics/             # Deterministic + G-Eval metric definitions
│   ├── templates/               # Jinja HTML report template
│   ├── scripts/                 # Standalone CLIs (generate_report, build_excel)
│   ├── invoices/                # 10 ground-truth receipt images
│   └── results/                 # Per-benchmark JSON + expense-ai-deepeval-report.html
│
├── tests/                       # Pytest suite (unit + integration)
├── alembic/                     # Database migrations
├── scripts/                     # Operational scripts (startup.sh, ingest_policies.py)
├── static/ + templates/         # Frontend assets and Jinja templates
├── docs/                        # Project documentation and notes
├── .planning/                   # Roadmap, phase plans, requirements, research
├── artifacts/                   # Sample receipts for manual testing
├── archived/                    # Deprecated code kept for reference (Chainlit UI, old agent prototypes)
├── docker-compose.yml           # 8-service orchestration
├── Dockerfile                   # App image (uvicorn + FastAPI)
└── pyproject.toml               # Poetry dependencies and tool config
```

Architecture follows **Vertical Slice + DDD**: each agent owns its node, prompts, tools, and utilities as a single package. Agent nodes never import infrastructure directly — all external I/O flows through MCP tools or is passed via graph state.

## Evaluation

A DeepEval-based harness exercises the running app with 20 test cases across 16 benchmarks, spanning 5 weighted categories: Classification (15%), Extraction (25%), Reasoning (30%), Workflow (10%), Safety (20%). Each case is scored via deterministic, semantic (LLM-as-judge), hallucination, or safety G-Eval metrics and rolled up into a single overall score. Ground truth is anchored to 10 real receipt images — clean, blurry, handwritten, multi-currency, and deliberately ambiguous.

```bash
# Full pipeline: capture -> load -> enrich -> score -> HTML report
poetry run python eval/run_eval.py

# Re-score existing captures (skip browser runs)
poetry run python eval/run_eval.py --skip-capture

# Run a single benchmark
poetry run python eval/run_eval.py --benchmark ER-005

# Regenerate just the HTML report from existing scored results
poetry run python eval/scripts/generate_report.py
```

Outputs:

- `eval/results/ER-XXX.json` — per-benchmark capture + scores
- `eval/results/expense-ai-deepeval-report.html` — standalone HTML report (dark theme, matches app design system)

Judge model defaults to GPT-4o via OpenRouter. Configure via environment variables in `.env.local`.

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

### Running the App Without Docker

Requires PostgreSQL and Qdrant running locally:

```bash
poetry install
poetry run alembic upgrade head
python scripts/ingest_policies.py
poetry run uvicorn agentic_claims.web.main:app --host 0.0.0.0 --port 8000 --reload
```

### Database Migrations

```bash
# Inside Docker
docker compose exec app poetry run alembic upgrade head

# From host (POSTGRES_HOST=localhost)
poetry run alembic upgrade head

# Create new migration from model changes
poetry run alembic revision --autogenerate -m "description"
```
