# Architecture Patterns

**Domain:** Multi-Agent LangGraph Systems with MCP Integration
**Researched:** 2026-03-23
**Confidence:** HIGH

## Recommended Architecture

For a 4-agent expense claims pipeline using LangGraph orchestration with MCP tool integration and Chainlit UI, the recommended architecture follows a **Graph-Based Multi-Agent System with Shared State and Message Bus Communication**.

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Chainlit UI Layer (Two Personas: Claimant, Reviewer)          │
│ - Real-time message streaming                                  │
│ - Session management                                           │
│ - Token-by-token display                                       │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ LangGraph Orchestration Layer                                  │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ ClaimState (TypedDict) - Shared Across All Nodes         │  │
│ │ - claim_data, compliance_status, fraud_score, etc.        │  │
│ │ - message_history (reducer: add_messages)                 │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│ ┌─────────┐    ┌──────────────┐    ┌──────────┐    ┌────────┐ │
│ │ Intake  │───▶│ Compliance   │───▶│  Fraud   │───▶│Advisor │ │
│ │ (ReAct) │    │ (Evaluator)  │    │(ToolCall)│    │(Reflect│ │
│ │ Node    │    │ Node         │    │ Node     │    │+ Route)│ │
│ └─────────┘    └──────────────┘    └──────────┘    └────────┘ │
│      │                │                    │              │     │
│      └────────────────┴────────────────────┴──────────────┘     │
│                              │                                  │
│                              ▼                                  │
│                    PostgreSQL Checkpointer                      │
│                    (State Persistence)                          │
└─────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ MCP Layer (4 Docker Services)                                  │
│ ┌────────┐  ┌────────┐  ┌─────────────┐  ┌───────────┐        │
│ │  RAG   │  │ DBHub  │  │ Frankfurter │  │   Email   │        │
│ │(Qdrant)│  │(Postgres│  │  (Currency  │  │   SMTP    │        │
│ │        │  │ Queries)│  │  Exchange)  │  │           │        │
│ └────────┘  └────────┘  └─────────────┘  └───────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With | State Access |
|-----------|----------------|-------------------|--------------|
| **Chainlit UI** | User interaction, message streaming, session management | LangGraph via async streaming | Read-only (displays state) |
| **Intake Agent Node** | Receipt upload, pre-validation, user Q&A (ReAct pattern) | ClaimState (read/write), MCP RAG + DBHub | Full state read/write |
| **Compliance Agent Node** | Policy evaluation, rule checking (Evaluator pattern) | ClaimState (read/write), MCP RAG (policy docs) | Full state read/write |
| **Fraud Agent Node** | Anomaly detection, pattern analysis (Tool Call pattern) | ClaimState (read/write), MCP DBHub (historical data) | Full state read/write |
| **Advisor Agent Node** | Synthesis, routing decisions (Reflection + Routing) | ClaimState (read/write), MCP Email | Full state read/write |
| **PostgreSQL Checkpointer** | State persistence, crash recovery, time-travel debugging | LangGraph StateGraph | Manages checkpoint persistence |
| **MCP Servers** | External tool access (RAG, DB, Currency, Email) | Agent nodes via langchain-mcp-adapters | Stateless tool providers |

### Data Flow

**Execution Flow (Sequential + Conditional + Parallel):**

1. **Pre-Submission Stage (Sequential)**
   - User uploads receipt via Chainlit UI
   - Intake Agent (ReAct) processes upload
     - Tool call: MCP RAG (extract policy requirements)
     - Tool call: MCP DBHub (validate employee, project codes)
     - Updates ClaimState: `claim_data`, `validation_status`
     - Checkpointed to Postgres after node execution
   - Conditional edge: Is claim submission ready?
     - NO → Loop back to Intake for user clarification
     - YES → Proceed to Post-Submission Stage

2. **Post-Submission Stage (Parallel Execution)**
   - Compliance Agent and Fraud Agent execute in parallel (same superstep)
   - **Compliance Agent (Evaluator):**
     - Reads ClaimState: `claim_data`
     - Tool call: MCP RAG (policy document retrieval)
     - Evaluates against compliance rules
     - Writes ClaimState: `compliance_status`, `policy_violations`
     - Checkpointed to Postgres
   - **Fraud Agent (Tool Call):**
     - Reads ClaimState: `claim_data`
     - Tool call: MCP DBHub (query historical claims for patterns)
     - Tool call: MCP Frankfurter (validate currency conversions)
     - Computes fraud risk score
     - Writes ClaimState: `fraud_score`, `anomaly_flags`
     - Checkpointed to Postgres

3. **Synthesis Stage (Sequential)**
   - Advisor Agent waits for both Compliance + Fraud to complete
   - Reads ClaimState: `compliance_status`, `fraud_score`, `claim_data`
   - Reflection pattern: Synthesizes findings, generates recommendation
   - Routing decision:
     - APPROVE → Tool call: MCP Email (notify approver)
     - REJECT → Tool call: MCP Email (notify claimant with reasons)
     - ESCALATE → Tool call: MCP Email (notify reviewer)
   - Writes ClaimState: `final_decision`, `recommendation_text`
   - Checkpointed to Postgres
   - Returns final state to Chainlit for display

**State Updates via Reducers:**

- `message_history: Annotated[list, add_messages]` - All agents append messages without overwriting
- `claim_data: dict` - Overwritten by each agent
- `compliance_status: dict` - Written by Compliance Agent
- `fraud_score: float` - Written by Fraud Agent
- `final_decision: str` - Written by Advisor Agent

**Checkpoint Persistence:**

- After **every node execution**, LangGraph automatically checkpoints state to PostgreSQL
- On crash: Resume from last checkpoint using `thread_id`
- Time-travel debugging: Access any historical checkpoint via `checkpoint_id`

## Patterns to Follow

### Pattern 1: TypedDict Shared State with Reducers
**What:** All agents read/write from a single TypedDict state object with reducer functions for multi-node coordination.

**When:** Multi-agent systems where all agents need visibility into shared context.

**Example:**
```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class ClaimState(TypedDict):
    claim_data: dict
    message_history: Annotated[list, add_messages]  # Reducer
    compliance_status: dict
    fraud_score: float
    final_decision: str

# Each agent node signature
def intakeAgent(state: ClaimState) -> ClaimState:
    # Read state
    existingData = state.get("claim_data", {})

    # Update state
    return {
        "claim_data": updatedData,
        "message_history": [AIMessage(content="Receipt processed")]
    }
```

**Why:** Eliminates message-ordering races, provides stronger consistency than message-passing, centralizes state management.

### Pattern 2: MCP Adapter for Tool Integration
**What:** Use `langchain-mcp-adapters` to convert MCP tools into LangGraph-compatible tools.

**When:** Integrating external services (RAG, databases, APIs) as agent tools.

**Example:**
```python
from langchain_mcp_adapters import MultiServerMCPClient

# Multi-server client configuration
config = {
    "rag": {
        "transport": "stdio",
        "command": "docker",
        "args": ["exec", "-i", "mcp-rag", "python", "/app/server.py"]
    },
    "dbhub": {
        "transport": "http",
        "url": "http://localhost:8001/mcp"
    }
}

client = MultiServerMCPClient(config)
tools = await client.get_tools()  # Returns LangChain-compatible tools

# Pass to agent node
graph.add_node("intake", create_react_agent(model, tools))
```

**Why:** Standardized tool access across distributed services, automatic conversion to LangChain format, multi-server support.

### Pattern 3: Conditional Routing with Parallel Execution
**What:** Use conditional edges for branching logic, automatic parallel execution for independent nodes.

**When:** Compliance and Fraud checks can run concurrently, but Advisor must wait for both.

**Example:**
```python
from langgraph.graph import StateGraph, END

graph = StateGraph(ClaimState)

# Sequential: Intake
graph.add_node("intake", intakeAgent)

# Parallel: Compliance and Fraud (same superstep)
graph.add_node("compliance", complianceAgent)
graph.add_node("fraud", fraudAgent)

# Sequential: Advisor (next superstep, waits for both)
graph.add_node("advisor", advisorAgent)

# Conditional edge from Intake
def shouldSubmit(state: ClaimState) -> str:
    return "submit" if state["validation_status"] == "ready" else "clarify"

graph.add_conditional_edges(
    "intake",
    shouldSubmit,
    {
        "submit": ["compliance", "fraud"],  # Both executed in parallel
        "clarify": "intake"  # Loop back
    }
)

# Both Compliance and Fraud route to Advisor
graph.add_edge("compliance", "advisor")
graph.add_edge("fraud", "advisor")
graph.add_edge("advisor", END)

graph.set_entry_point("intake")
```

**Why:** Automatic parallelization reduces latency, conditional logic enables loops and branching, explicit supersteps provide deterministic execution order.

### Pattern 4: PostgreSQL Checkpointer for Production
**What:** Use `PostgresSaver` for persistent state across crashes, restarts, and long-running conversations.

**When:** Production deployments requiring resilience, multi-instance scaling, or debugging.

**Example:**
```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost:5432/claims_db"
)

# Setup tables (first run only)
await checkpointer.setup()

# Compile graph with checkpointer
app = graph.compile(checkpointer=checkpointer)

# Invoke with thread_id for persistence
config = {"configurable": {"thread_id": "claim-12345"}}
result = await app.ainvoke(initialState, config)

# Resume after crash
result = await app.ainvoke(None, config)  # Resumes from last checkpoint
```

**Why:** Automatic crash recovery, state survives server restarts, supports time-travel debugging, enables multi-threaded conversations.

### Pattern 5: Chainlit Streaming Integration
**What:** Stream LangGraph outputs to Chainlit UI in real-time with message filtering.

**When:** Building interactive UIs for LangGraph applications.

**Example:**
```python
import chainlit as cl
from langgraph.graph import StateGraph

@cl.on_message
async def onMessage(message: cl.Message):
    thread_id = cl.context.session.id
    config = {"configurable": {"thread_id": thread_id}}

    # Stream graph execution
    msg = cl.Message(content="")
    async for event in app.astream_events(
        {"message_history": [HumanMessage(content=message.content)]},
        config,
        version="v2"
    ):
        # Filter by node metadata
        if event["event"] == "on_chat_model_stream":
            if event["metadata"].get("langgraph_node") == "advisor":
                await msg.stream_token(event["data"]["chunk"].content)

    await msg.send()
```

**Why:** Real-time user feedback, token-by-token streaming, session-based state management, metadata-based filtering.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Direct Agent-to-Agent Communication
**What:** Agents calling each other's functions directly instead of using shared state.

**Why bad:** Creates tight coupling, breaks observability, loses checkpointing benefits, makes debugging impossible.

**Instead:** All communication through ClaimState updates. Agents are pure functions: `(state) -> state`.

### Anti-Pattern 2: Stateful MCP Servers
**What:** MCP servers maintaining session state between tool calls.

**Why bad:** Breaks parallelization, creates race conditions, complicates deployment.

**Instead:** MCP servers should be stateless tools. All state belongs in ClaimState, persisted by LangGraph checkpointer.

### Anti-Pattern 3: Nested Graph State Leakage
**What:** Subgraphs modifying parent graph state directly.

**Why bad:** Violates encapsulation, makes state mutations unpredictable.

**Instead:** Subgraphs have their own state schemas. Parent graph maps subgraph outputs to parent state explicitly.

### Anti-Pattern 4: Ignoring Superstep Execution Model
**What:** Assuming nodes execute in arbitrary order or that parallel nodes can block each other.

**Why bad:** Leads to deadlocks, race conditions, or incorrect assumptions about execution order.

**Instead:** Understand Pregel-inspired supersteps:
- Parallel nodes = same superstep (isolated state copies, deterministic merge)
- Sequential nodes = separate supersteps (ordered execution)

### Anti-Pattern 5: In-Memory Checkpointer in Production
**What:** Using `MemorySaver` or `SqliteSaver` for production deployments.

**Why bad:** State lost on server restart, doesn't scale across multiple instances, no crash recovery.

**Instead:** Always use `PostgresSaver` in production for persistence, crash recovery, and multi-instance support.

## Scalability Considerations

| Concern | At 100 users | At 10K users | At 1M users |
|---------|--------------|--------------|-------------|
| **State Persistence** | PostgreSQL single instance | PostgreSQL with connection pooling | PostgreSQL with read replicas, write leader |
| **MCP Servers** | Single Docker container per service | Horizontal scaling with load balancer | Kubernetes with auto-scaling, service mesh |
| **Checkpointing** | Checkpoint after every node | Selective checkpointing (critical nodes only) | Async checkpointing, batch writes |
| **Graph Execution** | Single process | Multi-process with thread-based routing | Distributed execution with LangGraph Cloud |
| **Message History** | Store all messages in state | Prune old messages (keep last N) | External message store, reference in state |

## Build Order Recommendations

Based on dependency analysis, the recommended build order is:

### Phase 1: Foundation (No Dependencies)
1. **Define ClaimState TypedDict** - Central contract for all agents
2. **Setup PostgreSQL Checkpointer** - State persistence infrastructure
3. **Configure MCP Server Stubs** - Placeholder implementations for development

**Rationale:** Shared state schema is the foundational contract. All agents depend on it. Checkpointer enables testing with state persistence from day one.

### Phase 2: MCP Integration (Depends on Phase 1)
4. **Implement MCP Servers** - RAG, DBHub, Frankfurter, Email as Docker services
5. **Test MCP Adapters** - Verify `langchain-mcp-adapters` tool conversion
6. **Create Tool Registry** - Centralized tool management

**Rationale:** Tools must exist before agents can use them. Testing MCP integration in isolation prevents compounding errors.

### Phase 3: Agent Nodes (Depends on Phase 1, 2)
7. **Intake Agent (ReAct)** - First node, simplest pattern, validates state flow
8. **Compliance Agent (Evaluator)** - Parallel execution candidate
9. **Fraud Agent (Tool Call)** - Parallel execution candidate
10. **Advisor Agent (Reflection + Routing)** - Terminal node, depends on all previous

**Rationale:** Build intake first to validate end-to-end flow. Then build parallel agents (Compliance, Fraud) to test superstep execution. Build Advisor last as it synthesizes outputs from all other agents.

### Phase 4: Graph Orchestration (Depends on Phase 3)
11. **Construct StateGraph** - Wire nodes with conditional edges
12. **Implement Conditional Routing** - Intake loop, Advisor routing logic
13. **Test Parallel Execution** - Verify Compliance || Fraud superstep

**Rationale:** Graph construction requires all nodes to exist. Conditional logic is the most complex part, test iteratively.

### Phase 5: UI Integration (Depends on Phase 4)
14. **Chainlit Streaming** - Real-time message display
15. **Session Management** - Thread-based state persistence
16. **Persona Switching** - Claimant vs. Reviewer views

**Rationale:** UI is the final layer. Requires fully functional graph to test streaming and session management.

### Phase 6: Production Hardening (Depends on All)
17. **Error Handling** - Node-level, graph-level, app-level
18. **Observability** - Tracing, logging, metrics
19. **Cost Monitoring** - Token usage, MCP call tracking
20. **Docker Compose Orchestration** - Local development parity with production

**Rationale:** Production concerns span all layers. Address after core functionality is validated.

## Project Structure Conventions

**Standard LangGraph Project Layout (2026):**

```
expense-claims/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── intake.py           # Intake agent node
│   │   ├── compliance.py       # Compliance agent node
│   │   ├── fraud.py            # Fraud agent node
│   │   └── advisor.py          # Advisor agent node
│   ├── state/
│   │   ├── __init__.py
│   │   └── claim_state.py      # ClaimState TypedDict definition
│   ├── tools/
│   │   ├── __init__.py
│   │   └── mcp_registry.py     # MCP tool registration
│   ├── graph/
│   │   ├── __init__.py
│   │   └── claim_graph.py      # StateGraph construction
│   └── app.py                  # Chainlit application entry
├── mcp_servers/
│   ├── rag/
│   │   ├── Dockerfile
│   │   └── server.py
│   ├── dbhub/
│   │   ├── Dockerfile
│   │   └── server.py
│   ├── frankfurter/
│   │   ├── Dockerfile
│   │   └── server.py
│   └── email/
│       ├── Dockerfile
│       └── server.py
├── tests/
│   ├── unit/
│   │   ├── test_agents.py
│   │   ├── test_tools.py
│   │   └── test_state.py
│   ├── integration/
│   │   ├── test_graph.py
│   │   └── test_mcp.py
│   └── e2e/
│       └── test_claim_flow.py
├── .env                        # Environment variables
├── docker-compose.yml          # MCP servers orchestration
├── langgraph.json             # LangGraph deployment config
├── pyproject.toml             # Python dependencies
└── README.md
```

## Sources

**Official Documentation (HIGH Confidence):**
- [LangGraph Application Structure - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/application-structure)
- [Model Context Protocol (MCP) - LangChain Docs](https://docs.langchain.com/oss/python/langchain/mcp)
- [LangChain/LangGraph - Chainlit Integration](https://docs.chainlit.io/integrations/langchain)
- [LangGraph Multi-Agent Workflows - LangChain Blog](https://blog.langchain.com/langgraph-multi-agent-workflows/)
- [Choosing the Right Multi-Agent Architecture - LangChain Blog](https://blog.langchain.com/choosing-the-right-multi-agent-architecture/)
- [LangGraph Graph API Overview - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [Memory - LangChain Docs](https://docs.langchain.com/oss/python/langgraph/add-memory)

**Community Resources (MEDIUM Confidence):**
- [How to Design Production-Grade Multi-Agent Communication System - MarkTechPost (2026)](https://www.marktechpost.com/2026/03/01/how-to-design-a-production-grade-multi-agent-communication-system-using-langgraph-structured-message-bus-acp-logging-and-persistent-shared-state-architecture/)
- [LangGraph Multi-Agent Systems Tutorial 2026 - LangChain Tutorials](https://langchain-tutorials.github.io/langgraph-multi-agent-systems-2026/)
- [LangGraph: Build Stateful Multi-Agent Systems That Don't Crash - Mager.co (2026-03-12)](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive/)
- [LangGraph Explained (2026 Edition) - Medium](https://medium.com/@dewasheesh.rana/langgraph-explained-2026-edition-ea8f725abff3)
- [LangGraph Best Practices - Swarnendu De](https://www.swarnendu.de/blog/langgraph-best-practices/)
- [LangGraph MCP Client Setup Made Easy [2026 Guide] - Generect](https://generect.com/blog/langgraph-mcp/)
- [Quickly Build a ReAct Agent With LangGraph and MCP - Neo4j](https://neo4j.com/blog/developer/react-agent-langgraph-mcp/)
- [Building Parallel Workflows with LangGraph - GoPenAI](https://blog.gopenai.com/building-parallel-workflows-with-langgraph-a-practical-guide-3fe38add9c60)
- [Unlocking AI Resilience: State Persistence with LangGraph and PostgreSQL - DEV](https://dev.to/programmingcentral/unlocking-ai-resilience-mastering-state-persistence-with-langgraph-and-postgresql-50h0)
- [Persistence in LangGraph — Deep, Practical Guide - Towards AI (2026)](https://pub.towardsai.net/persistence-in-langgraph-deep-practical-guide-36dc4c452c3b)
- [Docker Compose - MCP Server with LangGraph](https://mcp-server-langgraph.mintlify.app/deployment/docker)
- [Build AI Agents with Docker Compose - Docker Blog](https://www.docker.com/blog/build-ai-agents-with-docker-compose/)

**GitHub Projects (MEDIUM Confidence):**
- [langchain-ai/langchain-mcp-adapters - GitHub](https://github.com/langchain-ai/langchain-mcp-adapters)
- [teddynote-lab/langgraph-mcp-agents - GitHub](https://github.com/teddynote-lab/langgraph-mcp-agents)
- [brucechou1983/chainlit_langgraph - GitHub](https://github.com/brucechou1983/chainlit_langgraph)
