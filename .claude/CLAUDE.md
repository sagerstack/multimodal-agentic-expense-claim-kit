# Agentic Expense Claims

Multi-agent multimodal system that automates SUTD expense claim processing. Replaces the manual SAP Concur workflow (15-25 min per claim) with an AI-driven pipeline targeting <3 min submission time and >95% field extraction accuracy.

Four LangGraph agents process claims through a pipeline: **Intake** (receipt parsing, policy validation) -> **Compliance** + **Fraud** (parallel post-submission checks) -> **Advisor** (decision routing). Chainlit provides the chat UI, PostgreSQL persists state, Qdrant stores policy embeddings.

## Running the App

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Poetry (package manager)

### Setup

```bash
# Install dependencies
poetry install

# Create .env.local from the template
cp .env.example .env.local
# Edit .env.local with your actual values

# Start all services (app + postgres)
docker compose up -d --build

# Verify both services are healthy
docker compose ps

# Open the UI
open http://localhost:8000
```

### Common Commands

```bash
# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=agentic_claims --cov-report=term-missing

# Lint
poetry run ruff check src/ tests/

# Format
poetry run ruff format src/ tests/

# Stop services
docker compose down

# Stop and remove volumes (full reset)
docker compose down -v
```

## Configuration

All configuration is loaded from environment files via pydantic-settings. No hardcoded values in source code.

| File | Purpose | Git tracked? |
|------|---------|-------------|
| `.env.example` | Template with placeholder values | Yes |
| `.env.local` | Local development values | No (gitignored) |
| `tests/.env.test` | Test configuration values | Yes |

The `Settings` class in `src/agentic_claims/core/config.py` loads from `.env.local` by default. Tests override this with `tests/.env.test` via the `testSettings` fixture in `conftest.py`.

Docker Compose reads `.env.local` via `env_file:` directives for both the app and postgres services.

## Project Structure

```
src/agentic_claims/
├── app.py                          # Chainlit entry point (on_chat_start, on_message, on_chat_end)
├── agents/                         # One package per agent (vertical slice)
│   ├── intake/
│   │   ├── __init__.py
│   │   └── node.py                 # intakeNode() - receipt parsing, validation
│   ├── compliance/
│   │   ├── __init__.py
│   │   └── node.py                 # complianceNode() - policy audit
│   ├── fraud/
│   │   ├── __init__.py
│   │   └── node.py                 # fraudNode() - duplicate detection
│   └── advisor/
│       ├── __init__.py
│       └── node.py                 # advisorNode() - decision routing
└── core/                           # Shared infrastructure
    ├── config.py                   # Settings (pydantic-settings, loads .env.local)
    ├── state.py                    # ClaimState TypedDict (shared across all nodes)
    └── graph.py                    # StateGraph definition, compilation, checkpointer

tests/
├── .env.test                       # Test environment values
├── conftest.py                     # Shared fixtures (testSettings)
└── test_graph.py                   # Graph orchestration tests
```

## Graph Topology

The LangGraph StateGraph defines the claim processing pipeline:

```
START -> intake -> [compliance || fraud] -> advisor -> END
```

- **intake**: First node. Processes the incoming claim.
- **compliance** and **fraud**: Run in parallel (same LangGraph superstep) via fan-out from intake.
- **advisor**: Fan-in node. Waits for both compliance and fraud, then makes the final decision.

The graph is defined in `core/graph.py`. `buildGraph()` returns an uncompiled `StateGraph`. `getCompiledGraph()` compiles it with an `AsyncPostgresSaver` checkpointer for state persistence.

## Writing a New Agent Node

Every agent lives in its own package under `src/agentic_claims/agents/`. Follow this pattern:

### 1. Create the package

```
src/agentic_claims/agents/your_agent/
├── __init__.py
└── node.py
```

### 2. Write the node function

The node function is an `async` function that takes `ClaimState` and returns a `dict` with partial state updates. Only return the keys you want to change.

```python
"""Your agent node - brief description of purpose."""

from langchain_core.messages import AIMessage

from agentic_claims.core.state import ClaimState


async def yourAgentNode(state: ClaimState) -> dict:
    """What this agent does.

    Args:
        state: Current claim state (read claimId, status, messages, etc.)

    Returns:
        Partial state update dict
    """
    # Read from state
    claimId = state["claimId"]
    currentMessages = state["messages"]

    # Do your agent's work here
    result = "Your agent's output"

    # Return partial state update
    # - messages uses an Annotated reducer (add_messages) so new messages
    #   are APPENDED, not replaced
    # - Other keys (status, claimId) are replaced on write
    aiMessage = AIMessage(content=result)
    return {"messages": [aiMessage]}
```

### 3. Wire the node into the graph

In `src/agentic_claims/core/graph.py`, add the node and its edges:

```python
from agentic_claims.agents.your_agent.node import yourAgentNode

# Inside buildGraph():
builder.add_node("your_agent", yourAgentNode)
builder.add_edge("some_previous_node", "your_agent")
builder.add_edge("your_agent", "some_next_node")
```

### 4. Update ClaimState if needed

If your agent needs new state fields, add them to `ClaimState` in `src/agentic_claims/core/state.py`:

```python
class ClaimState(TypedDict):
    claimId: str
    status: str
    messages: Annotated[list[AnyMessage], add_messages]
    # Add your fields here
    yourField: str  # Simple replacement on write
    yourList: Annotated[list[str], operator.add]  # Append reducer
```

Use `Annotated` with a reducer function when you want values to accumulate across nodes (like `messages`). Use plain types when you want the last writer to win.

### Key patterns

- **CamelCase naming** for all functions, variables, classes, and tests
- **Async nodes** — all node functions must be `async def`
- **Partial state updates** — only return the keys you want to change
- **Messages accumulate** — the `add_messages` reducer appends new messages to the list
- **Status transitions** — only set `status` if your node changes the claim lifecycle stage
- **No infrastructure imports in agent nodes** — agents should not import config, database, or infrastructure directly. Use tools/MCP or pass data through state.

## ClaimState

The shared state passed between all nodes is defined in `src/agentic_claims/core/state.py`:

```python
class ClaimState(TypedDict):
    claimId: str                                        # Unique claim identifier
    status: str                                         # Lifecycle: draft -> submitted -> approved/returned/escalated
    messages: Annotated[list[AnyMessage], add_messages]  # Conversation history (append-only)
```

This is intentionally minimal in Phase 1. Future phases will expand it with receipt data, compliance findings, fraud flags, etc.

## AsyncPostgresSaver (Checkpointer)

The checkpointer persists graph state to PostgreSQL after each node execution. Important implementation detail:

`AsyncPostgresSaver.from_conn_string()` returns an **async context manager**, not the saver directly. The app enters it manually in `getCompiledGraph()` and stores the context for cleanup in `onChatEnd()`. See `core/graph.py:62-63` and `app.py:64-66`.

## Infrastructure (Docker Compose)

Current services (Phase 1):

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `app` | Built from Dockerfile | 8000 | Chainlit + LangGraph app |
| `postgres` | postgres:16-alpine | 5432 | State persistence, checkpointer |

Future phases will add: Qdrant (vector store), RAG MCP server, DBHub MCP server, Frankfurter MCP server, Email MCP server.

The Dockerfile uses a two-step poetry install for layer caching: `poetry install --no-root` (deps only), then copy source, then `poetry install` (root project).

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
| 2. Intake Agent + Receipt Processing | Not started |
| 3. Compliance + Fraud Agents | Not started |
| 4. Advisor Agent + Reviewer Flow | Not started |
| 5. Evaluation + Demo | Not started |

## Code Standards

- **Package manager**: Poetry. All commands via `poetry run`. Never use pip, hatchling, or setuptools.
- **Architecture**: Vertical slice + DDD. Each agent is its own package.
- **Naming**: CamelCase everywhere (functions, variables, classes, tests).
- **Testing**: TDD (red-green-refactor). Coverage >= 90%. Tests in `tests/` with `pytest-asyncio`.
- **Configuration**: No hardcoded values. All config from `.env.local` via pydantic-settings.
- **Domain purity**: Agent nodes must not import infrastructure (config, database) directly.
- **Git**: Feature branches per story, merge latest main before push.

---

## Project Memory

Agents read and write cross-session knowledge to `docs/project_notes/`:

| File | Read By | Written By |
|------|---------|-----------|
| `bugs.md` | Critical Analyst, Developer, QA | Developer, QA |
| `decisions.md` | BA, Architect, Critical Analyst, Developer | Architect |
| `key_facts.md` | Architect, Developer | Architect, Developer |
| `issues.md` | BA | QA |
