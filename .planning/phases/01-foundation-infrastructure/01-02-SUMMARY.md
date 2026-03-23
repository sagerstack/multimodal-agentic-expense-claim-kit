---
phase: 01-foundation-infrastructure
plan: 02
subsystem: orchestration
tags: [langgraph, state-graph, parallel-fan-out, postgres-checkpointer, chainlit]

# Dependency graph
requires:
  - phase: 01-foundation-infrastructure
    plan: 01
    provides: project skeleton, Docker Compose, configuration
provides:
  - ClaimState TypedDict with Annotated reducers
  - LangGraph StateGraph with 4 stub nodes and parallel fan-out
  - AsyncPostgresSaver checkpointer integration
  - Chainlit integration invoking graph on message
  - 3 integration tests proving flow, parallelism, state preservation
affects: [phase-2-intake, phase-3-compliance-fraud, phase-4-advisor]

# Tech tracking
tech-stack:
  added: [langgraph-state-graph, async-postgres-saver, langchain-core-messages]
  patterns: [parallel-fan-out, annotated-reducers, async-checkpointer]

key-files:
  created:
    - src/agentic_claims/core/state.py
    - src/agentic_claims/agents/intake/node.py
    - src/agentic_claims/agents/compliance/node.py
    - src/agentic_claims/agents/fraud/node.py
    - src/agentic_claims/agents/advisor/node.py
    - src/agentic_claims/core/graph.py
    - tests/test_graph.py
  modified:
    - src/agentic_claims/app.py

key-decisions:
  - Used Annotated reducers with add_messages for automatic message list merging
  - Parallel fan-out topology: Intake -> [Compliance || Fraud] -> Advisor
  - Checkpointer lifecycle managed per chat session in Chainlit
  - Integration tests use graph.compile() without checkpointer for faster execution

patterns-established:
  - ClaimState as TypedDict with minimal fields (claimId, status, messages)
  - Each agent node returns partial state dict for reducer merging
  - Graph compilation with AsyncPostgresSaver for state persistence
  - Chainlit handlers manage graph lifecycle and display agent outputs

# Metrics
duration: 5min
completed: 2026-03-23
---

# Phase 1 Plan 2: LangGraph Orchestration Summary

**One-liner**: LangGraph StateGraph with parallel fan-out (Compliance || Fraud), Postgres checkpointer persistence, and Chainlit integration producing 4-agent orchestrated responses.

## What Was Built

### ClaimState Definition (src/agentic_claims/core/state.py)
- TypedDict with 3 fields:
  - `claimId: str` — unique identifier
  - `status: str` — lifecycle tracking (draft, submitted, processing, approved, rejected, returned)
  - `messages: Annotated[list[AnyMessage], add_messages]` — auto-merging message list
- Intentionally minimal for Phase 1 — future phases expand with receipt data, findings, policy results

### Four Stub Agent Nodes
Each agent implemented as async function returning partial state dict:

1. **intakeNode** (src/agentic_claims/agents/intake/node.py)
   - Status transition: draft → submitted
   - Returns AIMessage: "Hello world from Intake Agent"

2. **complianceNode** (src/agentic_claims/agents/compliance/node.py)
   - Parallel validation node (no status change)
   - Returns AIMessage: "Hello world from Compliance Agent"

3. **fraudNode** (src/agentic_claims/agents/fraud/node.py)
   - Parallel detection node (no status change)
   - Returns AIMessage: "Hello world from Fraud Agent"

4. **advisorNode** (src/agentic_claims/agents/advisor/node.py)
   - Final decision node
   - Status transition: submitted → approved
   - Returns AIMessage: "Hello world from Advisor Agent"

### LangGraph StateGraph (src/agentic_claims/core/graph.py)
- **buildGraph()**: Creates uncompiled StateGraph with parallel fan-out topology
  - START → intake → [compliance || fraud] → advisor → END
  - Compliance and Fraud execute in same superstep (parallel)
  - Advisor waits for both (fan-in behavior)
- **getCompiledGraph()**: Compiles with AsyncPostgresSaver checkpointer
  - Creates Postgres connection from settings.postgres_dsn
  - Calls checkpointer.setup() to create persistence tables
  - Returns (compiled_graph, checkpointer) tuple

### Chainlit Integration (src/agentic_claims/app.py)
- **onChatStart()**: Initialize graph and checkpointer per session
  - Stores graph, checkpointer, thread_id in user_session
  - Thread ID enables conversation-level state persistence
- **onMessage()**: Invoke graph with user input
  - Creates ClaimState with HumanMessage
  - Invokes graph with checkpointer config
  - Sends all agent AIMessages back to user
- **onChatEnd()**: Clean up checkpointer connection

### Integration Tests (tests/test_graph.py)
Three pytest-asyncio tests proving core behaviors:

1. **test_graphFlowsThrough4Nodes**
   - Verifies all 4 agents execute
   - Checks final status = "approved"
   - Validates message count and agent names present

2. **test_complianceAndFraudRunInParallel**
   - Uses astream(stream_mode="updates") to capture execution order
   - Proves compliance and fraud execute in same superstep
   - Verifies both run before advisor (fan-in)

3. **test_claimStatePassedBetweenNodes**
   - Confirms claimId preservation across nodes
   - Validates status transitions (draft → approved)
   - Proves state reducer merging works

## Verification Results

### Unit Tests
```
tests/test_graph.py::test_graphFlowsThrough4Nodes PASSED                 [ 33%]
tests/test_graph.py::test_complianceAndFraudRunInParallel PASSED         [ 66%]
tests/test_graph.py::test_claimStatePassedBetweenNodes PASSED            [100%]

3 passed, 1 warning in 3.45s
```

### Docker Compose Integration
- Both services (app, postgres) reached healthy status
- Chainlit UI accessible at http://localhost:8000 (HTTP 200)
- App logs confirm: "Your app is available at http://0.0.0.0:8000"
- Checkpointer tables created on first chat session (lazy initialization)

## Deviations from Plan

None - plan executed exactly as written.

## Technical Insights

### Parallel Fan-Out Mechanics
LangGraph automatically executes nodes with no dependencies in the same superstep. By adding edges from intake to both compliance and fraud, then from both to advisor, the graph naturally parallelizes the two validation steps. The test using `stream_mode="updates"` confirms this behavior.

### Annotated Reducers Pattern
Using `Annotated[list[AnyMessage], add_messages]` enables automatic message list merging. Each node returns `{"messages": [new_message]}` and LangGraph appends to the existing list. This eliminates boilerplate message handling in every node.

### Checkpointer Lifecycle Management
AsyncPostgresSaver requires proper async context management. We initialize once per chat session in `onChatStart()` and store in `cl.user_session`. The checkpointer creates tables lazily on first `setup()` call. For unit tests, we compile without checkpointer for faster execution.

### Status Transition Flow
The plan correctly identified status transitions:
- User creates claim → status = "draft"
- Intake processes → status = "submitted"
- Compliance + Fraud run (no status change - parallel nodes)
- Advisor decides → status = "approved"

This establishes the pattern for future phases where advisor will make approval/rejection decisions based on compliance and fraud findings.

## Next Phase Readiness

### Blockers
None.

### Concerns
- **Python 3.14 Compatibility**: langchain-core emits warning about Pydantic V1 incompatibility with Python 3.14. Tests pass despite warning. Monitor for potential issues in future langchain updates.
- **Checkpointer Table Schema**: Haven't inspected the actual Postgres schema created by AsyncPostgresSaver.setup(). Should verify in Phase 2 when we need to query checkpoint data.

### Prerequisites for Phase 2
Phase 2 (Intake) will expand ClaimState with:
- Receipt data fields (vendor, amount, date, category, etc.)
- Image storage references (base64 or S3 URLs)
- Validation results from intake processing

The intakeNode stub should be replaced with:
- Multimodal receipt parsing (GPT-4o vision)
- Data extraction into structured format
- Initial validation (required fields, data quality)

Current orchestration foundation is ready - no changes needed to graph topology or checkpointer for Phase 2 work.

## Commits

- bd35227: feat(01-02): add ClaimState and 4 stub agent nodes
- 5c16338: feat(01-02): integrate LangGraph with parallel fan-out and Postgres checkpointer

## Duration

5 minutes (298 seconds)

## Status

✅ Complete - Phase 1 foundation infrastructure ready for Phase 2 intake development
