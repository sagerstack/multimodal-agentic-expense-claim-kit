"""LangGraph StateGraph definition with parallel fan-out and Postgres checkpointer."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from agentic_claims.agents.advisor.node import advisorNode
from agentic_claims.agents.compliance.node import complianceNode
from agentic_claims.agents.fraud.node import fraudNode
from agentic_claims.agents.intake.node import intakeNode
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState


def evaluatorGate(state: ClaimState) -> str:
    """Route based on whether claim has been submitted.

    Args:
        state: Current claim state

    Returns:
        "submitted" if claim was submitted (route to compliance+fraud),
        "pending" if still in intake conversation (route to END)
    """
    if state.get("claimSubmitted", False):
        return "submitted"
    return "pending"


def buildGraph() -> StateGraph:
    """Build the StateGraph with 4 nodes and parallel fan-out topology.

    Graph topology:
        START -> intake -> [compliance || fraud] -> advisor -> END

    The parallel fan-out means compliance and fraud run in the same superstep
    after intake. Advisor waits for both to complete (fan-in).

    Returns:
        Uncompiled StateGraph builder
    """
    builder = StateGraph(ClaimState)

    # Add 4 agent nodes
    builder.add_node("intake", intakeNode)
    builder.add_node("compliance", complianceNode)
    builder.add_node("fraud", fraudNode)
    builder.add_node("advisor", advisorNode)

    # Wire the graph with Evaluator Gate
    # START -> intake
    builder.add_edge(START, "intake")

    # Evaluator Gate: intake -> (submitted) -> postSubmission OR (pending) -> END
    # Use intermediate postSubmission node for fan-out to compliance and fraud
    builder.add_node("postSubmission", lambda state: state)  # Pass-through node
    builder.add_conditional_edges(
        "intake", evaluatorGate, {"submitted": "postSubmission", "pending": END}
    )

    # Fan-out from postSubmission to compliance and fraud (parallel)
    builder.add_edge("postSubmission", "compliance")
    builder.add_edge("postSubmission", "fraud")

    # Fan-in to advisor
    builder.add_edge("compliance", "advisor")
    builder.add_edge("fraud", "advisor")
    builder.add_edge("advisor", END)

    return builder


async def getCompiledGraph():
    """Create compiled graph with Postgres checkpointer.

    The checkpointer persists state after each node execution,
    enabling resumption and debugging.

    AsyncPostgresSaver.from_conn_string() returns an async context manager.
    We enter it manually here — caller must store the context and call
    __aexit__ on cleanup (see app.py onChatEnd).

    Returns:
        Tuple of (compiled graph, checkpointer context manager)
    """
    settings = getSettings()

    # from_conn_string returns an async context manager — enter it manually
    # so the connection pool stays alive for the session lifetime
    checkpointerCtx = AsyncPostgresSaver.from_conn_string(settings.postgres_dsn)
    checkpointer = await checkpointerCtx.__aenter__()

    # Setup checkpointer tables in Postgres
    await checkpointer.setup()

    # Build and compile graph with checkpointer
    builder = buildGraph()
    graph = builder.compile(checkpointer=checkpointer)

    return graph, checkpointerCtx
