# Technology Stack

**Project:** Agentic Expense Claims Processing System
**Researched:** 2026-03-23
**Constraint:** Zero-cost (free-tier services and models only)

## Recommended Stack

### Multi-Agent Orchestration
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| LangGraph | Latest (2026) | Multi-agent workflow orchestration, state management | CONFIRMED: Best choice for 4-agent pipeline with precise control flow. Graph-based architecture handles conditional routing (auto-approve/return/escalate), stateful execution, and agent coordination. LangGraph is trusted by Klarna, Replit, Elastic for production multi-agent systems. Supports parallel execution, error recovery, and durable state persistence. |
| FastMCP (mcp Python SDK) | Latest | MCP server implementation | For building MCP servers (RAG, DBHub, Frankfurter, Email) as Docker services. FastMCP is the official Python SDK for Model Context Protocol, supporting tools, resources, and prompts with async support. |

**Confidence:** HIGH (verified via WebSearch with current 2026 sources)

**Alternatives considered:**
- CrewAI: Role-based agent orchestration. Larger community, simpler API. Not chosen because graph-based control flow fits the intake→compliance→fraud→advisor pipeline better than conversational teams.
- AutoGen/AG2: Conversational multi-agent. Not chosen because the workflow is structured (not multi-turn dialogue).
- OpenAI Agents SDK: Locked to OpenAI models, violates free-tier constraint.

**Sources:**
- [LangGraph: Agent Orchestration Framework](https://www.langchain.com/langgraph)
- [LangGraph Multi-Agent Orchestration Guide 2025](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025)
- [LangGraph Deep Dive 2026](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

---

### UI Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Chainlit | 2.10.0+ | Conversational AI UI, chat interface | CONFIRMED: Purpose-built for LLM chat apps. Automatically handles message history, real-time streaming, file uploads (receipt images), user session management. Native integrations with LangGraph, async support via `@cl.on_message` decorators. Open-source (Apache 2.0), zero cost. Note: Original team stepped back May 2025, now maintained by community under formal agreement. |

**Confidence:** HIGH (verified via official releases, GitHub changelog dated March 5, 2026)

**Alternatives considered:**
- Streamlit: General-purpose UI, not optimized for chat workflows.
- Gradio: Similar to Chainlit but less LangGraph integration.
- Custom FastAPI + React: Higher development cost, defeats "zero cost" time constraint.

**Sources:**
- [Chainlit PyPI](https://pypi.org/project/chainlit/)
- [Chainlit Releases](https://github.com/Chainlit/chainlit/releases)
- [Chainlit LangGraph Integration](https://docs.chainlit.io/integrations/langchain)

---

### LLM & Vision Models
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| OpenRouter API | Latest (2026) | Unified access to free LLM and VLM models | CONFIRMED: 29 free models as of March 2026 (zero cost, zero credit card). Free vision models include Qwen3 VL 235B Thinking, NVIDIA Nemotron Nano 12B VL, Mistral Small 3.1 24B Instruct (multimodal). Rate limits: 20 req/min, 200 req/day (sufficient for expense claims use case). Supports text, images, PDFs, audio, video inputs. Free models subsidized by OpenRouter. |

**Confidence:** HIGH (verified via official OpenRouter collections page, March 2026 listings)

**Receipt OCR approach:**
- Use free VLM models (Qwen3 VL, NVIDIA Nemotron Nano VL) via OpenRouter for receipt text extraction
- VLM-based OCR performs end-to-end processing (image → structured data) in single pass
- No separate OCR library needed (DeepSeek-OCR, PaddleOCR, EasyOCR are alternatives if VLM quality insufficient)

**Sources:**
- [OpenRouter Free Models (March 2026)](https://openrouter.ai/collections/free-models)
- [29 Free AI Models on OpenRouter (March 2026)](https://www.teamday.ai/blog/best-free-ai-models-openrouter-2026)
- [OpenRouter Multimodal Documentation](https://openrouter.ai/docs/guides/overview/multimodal/overview)

---

### Database & Vector Store
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16.13 (latest patch, Feb 26, 2026) | Relational database for claims, history, metadata | Industry-standard, mature, excellent Python support via psycopg. Docker image free. PostgreSQL 16 stable with full async support (via psycopg3). |
| Qdrant | Latest (Python client 1.13.4, March 13, 2026) | Vector database for policy embeddings (RAG) | Lightweight, runs in Docker, zero cost. Python client supports async, local mode (no server for tests), and FastEmbed integration for one-line embedding creation. Ideal for policy document retrieval (RAG MCP server). |

**Confidence:** HIGH (verified via PyPI releases, official PostgreSQL release notes)

**Database migration:**
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| Alembic | Latest | Database schema migrations | De facto standard for SQLAlchemy migrations. Auto-generates migration scripts, supports Postgres transactions, rollback support. |

**Database adapter:**
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| psycopg3 | Latest | PostgreSQL Python driver (async) | Modern async-first driver. psycopg2 remains viable (2.9.11, Oct 2025) but psycopg3 recommended for new projects requiring async support (matches LangGraph/Chainlit async patterns). |
| SQLAlchemy | 2.x | ORM and query builder | Industry standard, supports async (with psycopg3), works seamlessly with Alembic. Provides ORM abstraction while allowing raw SQL when needed. |

**Sources:**
- [PostgreSQL 16.13 Release](https://www.postgresql.org/docs/current/index.html)
- [Qdrant Python Client PyPI](https://pypi.org/project/qdrant-client/)
- [Qdrant Client GitHub](https://github.com/qdrant/qdrant-client)
- [Alembic GitHub](https://github.com/sqlalchemy/alembic)
- [Psycopg3 vs psycopg2 (2026 Guide)](https://leapcell.io/blog/python-postgres-psycopg-orm-guide)

---

### Embeddings
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastEmbed (via Qdrant) | Latest | Generate embeddings for policy documents | Native Qdrant integration, one-line embedding creation, runs locally (zero cost). Default model: sentence-transformers/all-MiniLM-L6-v2 (384-dim vectors, fast inference, small size, strong semantic similarity performance). |

**Confidence:** HIGH (verified via Qdrant documentation)

**Alternative:** sentence-transformers library directly (10,000+ models on Hugging Face Hub, maintained by Hugging Face). FastEmbed preferred for tighter Qdrant integration.

**Sources:**
- [Qdrant FastEmbed](https://github.com/qdrant/fastembed)
- [Qdrant Hybrid Search with FastEmbed](https://qdrant.tech/documentation/beginner-tutorials/hybrid-search-fastembed/)
- [sentence-transformers PyPI](https://pypi.org/project/sentence-transformers/)

---

### External APIs
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Frankfurter API | Latest (2026) | Currency conversion | CONFIRMED: Completely free, no API key, no rate limits, no authentication. Provides ECB exchange rates for 30+ currencies. Updated daily at 16:00 CET. Can self-host with Docker if needed. API endpoint: api.frankfurter.dev |

**Confidence:** HIGH (verified via official Frankfurter site)

**Sources:**
- [Frankfurter Official Site](https://frankfurter.dev/)
- [Frankfurter GitHub](https://github.com/lineofflight/frankfurter)
- [Frankfurter API 2026](https://publicapis.io/frankfurter-api)

---

### MCP Servers (Docker Services)
| Service | Technology | Purpose | Why |
|---------|-----------|---------|-----|
| RAG Server | FastMCP + Qdrant + FastEmbed | Policy document retrieval | Implements RAG for compliance validation. FastMCP provides MCP protocol, Qdrant stores policy embeddings, FastEmbed generates query embeddings. |
| DBHub Server | FastMCP + psycopg3 | Historical claim queries (fraud detection) | Provides MCP interface to PostgreSQL for duplicate/anomaly detection against historical data. |
| Frankfurter Server | FastMCP + httpx | Currency conversion | MCP wrapper for Frankfurter API. httpx chosen for async HTTP client (matches LangGraph async patterns). |
| Email Server | mcp-email-server (0.6.2, March 18, 2026) | Email sending (claim submission, notifications) | Pre-built MCP server with IMAP/SMTP support. Supports Gmail (smtp.gmail.com:587), Outlook, Yahoo. TLS encryption. Python >=3.10. |

**Confidence:** HIGH for RAG/DBHub/Frankfurter (standard pattern), HIGH for Email (verified via PyPI release)

**Email server alternatives:**
- ptbsare/email-mcp-server (FastMCP-based, POP3+SMTP with TLS)
- mcp-server-email (supports Gmail, Outlook, Yahoo preconfigured)
- gmail-mcp-server (Gmail-specific IMAP+SMTP)

**Recommendation:** Use ai-zerolab/mcp-email-server (0.6.2) - most actively maintained, latest release March 18, 2026, supports multiple providers.

**Sources:**
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [mcp-email-server PyPI](https://pypi.org/project/mcp-email-server/)
- [MCP Email Server Implementations](https://mcpservers.org/servers/ai-zerolab/mcp-email-server)

---

### Validation & Data Modeling
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Pydantic | v2 (latest) | Data validation, serialization | 5-50x faster than v1 (Rust core). Native type hints, JSON Schema emission. Used throughout: agent inputs/outputs, LangGraph state, API payloads, database models (via SQLAlchemy integration). Industry standard for Python data validation. |

**Confidence:** HIGH (verified via official docs, 2026 guides)

**Sources:**
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [Pydantic v2 Validation Guide (Jan 2026)](https://oneuptime.com/blog/post/2026-01-21-python-pydantic-v2-validation/view)
- [Pydantic Complete Guide 2026](https://devtoolbox.dedyn.io/blog/pydantic-complete-guide)

---

### HTTP Client (Async)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| httpx | Latest | Async HTTP client for external APIs | Supports both sync and async (unlike aiohttp which is async-only). HTTP/2 support. Slightly slower than aiohttp in pure async benchmarks but more flexible (can mix sync/async). Recent 2026 tests show comparable performance (1.4s vs <2s for aiohttp). Matches LangGraph/Chainlit async patterns. |

**Confidence:** MEDIUM (performance claims vary by benchmark, both httpx and aiohttp viable)

**Alternative:** aiohttp (async-only, generally faster for pure async workloads, WebSocket support). Choose aiohttp if performance bottleneck emerges or WebSocket needed.

**Sources:**
- [httpx vs aiohttp Comparison](https://leapcell.medium.com/comparing-requests-aiohttp-and-httpx-which-http-client-should-you-use-6e3d9ff47b0e)
- [10 Best Python HTTP Clients 2026](https://iproyal.com/blog/best-python-http-clients/)
- [httpx vs aiohttp Performance](https://apidog.com/blog/aiohttp-vs-httpx/)

---

### Testing
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | Latest | Test framework | Industry standard. |
| pytest-asyncio | Latest (docs updated March 23, 2026) | Async test support | Handles event loop, supports async fixtures, `@pytest.mark.asyncio` decorator. Auto mode for asyncio-only projects. Matches async-first architecture (LangGraph, Chainlit, psycopg3, httpx). |
| pytest-docker | Latest | Docker fixture management | For integration tests with Postgres, Qdrant, MCP servers running in Docker. |

**Confidence:** HIGH (pytest-asyncio docs updated today)

**Sources:**
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/)
- [pytest-asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [pytest-asyncio Practical Guide](https://pytest-with-eric.com/pytest-advanced/pytest-asyncio/)

---

### Infrastructure
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | Latest | Service containerization | For MCP servers (RAG, DBHub, Frankfurter, Email), Postgres, Qdrant. |
| Docker Compose | Latest | Multi-service orchestration | 2026 best practices: use profiles for selective services, named volumes for Postgres/Qdrant persistence, secrets via environment files (not hardcoded), health checks with `--interval=30s --timeout=3s --start-period=40s`, network isolation for service pairs. |

**Confidence:** HIGH (Docker Compose best practices verified via 2026 guides)

**Sources:**
- [Docker Compose Best Practices 2026](https://hackmamba.io/engineering/best-practices-when-using-docker-compose/)
- [Mastering Docker Compose 2026](https://medium.com/@adriansyah1230/mastering-docker-compose-a-practical-guide-to-multi-container-applications-c76811010131)
- [Docker Compose Python Multi-Service Guide](https://www.geeksforgeeks.org/devops/docker-compose-for-python-applications/)

---

### Language & Runtime
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.10-3.13 | All services | Chainlit requires Python <4.0, >=3.10. Qdrant client supports 3.10-3.14. LangGraph, FastMCP, pytest-asyncio all support 3.10+. Use Python 3.12 or 3.13 for latest performance improvements. |

**Confidence:** HIGH

---

## Missing Libraries Identified

These were missing from the confirmed stack but are required:

| Category | Library | Version | Purpose |
|----------|---------|---------|---------|
| Database | SQLAlchemy | 2.x | ORM and query builder |
| Database | Alembic | Latest | Schema migrations |
| Database | psycopg3 (or psycopg2-binary) | Latest | PostgreSQL driver |
| Embeddings | FastEmbed (or sentence-transformers) | Latest | Generate policy embeddings |
| HTTP | httpx | Latest | Async HTTP client (Frankfurter API, external calls) |
| Validation | Pydantic | v2 | Data modeling and validation |
| Testing | pytest | Latest | Test framework |
| Testing | pytest-asyncio | Latest | Async test support |
| Testing | pytest-docker | Latest | Docker integration tests |

---

## Installation

```bash
# Core orchestration
pip install langgraph mcp

# UI
pip install chainlit

# Database
pip install sqlalchemy alembic psycopg[binary]  # psycopg3 with binary
# OR for psycopg2 (if needed):
# pip install psycopg2-binary

# Vector store & embeddings
pip install qdrant-client[fastembed]

# Validation
pip install pydantic

# HTTP client
pip install httpx

# Testing
pip install pytest pytest-asyncio pytest-docker

# MCP servers
pip install mcp-email-server

# Infrastructure
# Docker and Docker Compose (install separately, not via pip)
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Orchestration | LangGraph | CrewAI | Role-based teams don't fit structured pipeline as well as graph-based control flow |
| Orchestration | LangGraph | AutoGen/AG2 | Conversational paradigm doesn't match intake→compliance→fraud→advisor workflow |
| Orchestration | LangGraph | OpenAI Agents SDK | Locked to OpenAI models, violates zero-cost constraint |
| UI | Chainlit | Streamlit | Not optimized for chat workflows, no native LangGraph integration |
| UI | Chainlit | Gradio | Less LangGraph integration than Chainlit |
| Database | PostgreSQL 16 | MySQL | PostgreSQL better JSON support, async driver maturity |
| Database | PostgreSQL 16 | SQLite | No network access (can't run in separate Docker service) |
| Vector Store | Qdrant | Chroma | Qdrant has better async support and FastEmbed integration |
| Vector Store | Qdrant | Pinecone | Not free-tier compatible, cloud-only |
| Embeddings | FastEmbed | OpenAI Embeddings | OpenAI embeddings not free |
| HTTP Client | httpx | aiohttp | httpx supports both sync/async, HTTP/2; aiohttp async-only but faster (use aiohttp if performance bottleneck emerges) |
| Currency API | Frankfurter | exchangerate-api.com | Frankfurter has no rate limits, no API key |
| OCR | VLM (Qwen3 VL, Nemotron Nano) | DeepSeek-OCR, PaddleOCR | VLM approach simpler (end-to-end), but can fallback to dedicated OCR if VLM quality insufficient |

---

## Validation Against Confirmed Stack

| Confirmed Component | Status | Notes |
|---------------------|--------|-------|
| LangGraph | VALIDATED | Latest 2026 version, production-ready for multi-agent orchestration |
| Chainlit | VALIDATED | v2.10.0 (March 5, 2026), maintained by community, async support confirmed |
| OpenRouter API | VALIDATED | 29 free models (March 2026), free VLMs available (Qwen3 VL, NVIDIA Nemotron Nano) |
| PostgreSQL 16 | VALIDATED | v16.13 (Feb 26, 2026), async support via psycopg3 |
| Qdrant | VALIDATED | Python client 1.13.4 (March 13, 2026), Docker-ready |
| MCP servers (4 Docker services) | VALIDATED | FastMCP for RAG/DBHub/Frankfurter, mcp-email-server 0.6.2 for Email |
| Python | VALIDATED | Python 3.10-3.13 compatible across all libraries |
| Docker Compose | VALIDATED | Standard for local multi-service orchestration |
| Frankfurter API | VALIDATED | Free, no rate limits, ECB data, 30+ currencies |

**All confirmed stack components are current best practices as of March 2026.**

---

## Architecture Alignment

This stack supports the confirmed 4-agent architecture:

1. **Intake Agent (ReAct + Evaluator Gate):**
   - VLM receipt extraction: OpenRouter free VLMs (Qwen3 VL, Nemotron Nano)
   - Policy validation via RAG: RAG MCP server (FastMCP + Qdrant + FastEmbed)
   - Currency conversion: Frankfurter MCP server (FastMCP + httpx)

2. **Compliance Agent (Evaluator):**
   - Org-level policy auditing: RAG MCP server

3. **Fraud Agent (Tool Call):**
   - Duplicate/anomaly detection: DBHub MCP server (FastMCP + psycopg3 + PostgreSQL)

4. **Advisor Agent (Reflection + Routing):**
   - Synthesizes findings, routes decisions (auto-approve/return/escalate)
   - Email submission: Email MCP server (mcp-email-server)

**LangGraph** orchestrates the 4-agent pipeline with state management and conditional routing.
**Chainlit** provides the claimant-facing UI for receipt upload and status tracking.
**PostgreSQL** stores claims history, metadata, and audit trail.
**Qdrant** stores policy document embeddings for RAG retrieval.

---

## Risk Assessment

| Component | Risk Level | Mitigation |
|-----------|-----------|------------|
| Chainlit maintainership | LOW-MEDIUM | Original team stepped back May 2025, now community-maintained. Active releases (March 2026). Monitor for stagnation. Have contingency plan (migrate to Streamlit or custom FastAPI+React if abandoned). |
| OpenRouter free tier rate limits | LOW | 20 req/min, 200 req/day sufficient for expense claims use case (not high-volume transactional system). If exceeded, implement request queuing or migrate to self-hosted Ollama. |
| VLM receipt OCR quality | MEDIUM | Free VLMs may have lower accuracy than commercial (GPT-4V, Claude 3.5 Sonnet Vision). Mitigation: Implement fallback to dedicated OCR library (DeepSeek-OCR, PaddleOCR) if VLM extraction fails validation. |
| Frankfurter API availability | LOW | Self-host option available via Docker if public API becomes unreliable. |
| psycopg3 maturity | LOW | psycopg3 stable, actively maintained, but psycopg2 remains fallback option (2.9.11, Oct 2025) if issues emerge. |

---

## Sources

All sources cited inline above. Key references:

- [LangGraph Multi-Agent Orchestration](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025)
- [Chainlit Releases](https://github.com/Chainlit/chainlit/releases)
- [OpenRouter Free Models (March 2026)](https://openrouter.ai/collections/free-models)
- [PostgreSQL 16.13 Documentation](https://www.postgresql.org/docs/current/index.html)
- [Qdrant Python Client PyPI](https://pypi.org/project/qdrant-client/)
- [FastEmbed GitHub](https://github.com/qdrant/fastembed)
- [mcp-email-server PyPI](https://pypi.org/project/mcp-email-server/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/latest/)
- [pytest-asyncio PyPI](https://pypi.org/project/pytest-asyncio/)
- [Docker Compose Best Practices 2026](https://hackmamba.io/engineering/best-practices-when-using-docker-compose/)
- [Frankfurter API](https://frankfurter.dev/)
