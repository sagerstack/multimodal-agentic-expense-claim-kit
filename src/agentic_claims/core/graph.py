"""LangGraph StateGraph definition with parallel fan-out and Postgres checkpointer."""

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg_pool import AsyncConnectionPool

from agentic_claims.agents.advisor.node import advisorNode
from agentic_claims.agents.compliance.node import complianceNode
from agentic_claims.agents.debug_llm_node import debugLlmNode
from agentic_claims.agents.fraud.node import fraudNode
from agentic_claims.agents.intake.node import intakeNode
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.state import ClaimState

logger = logging.getLogger(__name__)


def evaluatorGate(state: ClaimState) -> str:
    """Route based on whether claim has been submitted.

    Args:
        state: Current claim state

    Returns:
        "submitted" if claim was submitted (route to compliance+fraud),
        "pending" if still in intake conversation (route to END)
    """
    result = "submitted" if state.get("claimSubmitted", False) else "pending"
    logger.info("evaluatorGate decision", extra={"decision": result, "claimId": state.get("claimId")})
    return result


async def markAiReviewedNode(state: ClaimState) -> dict:
    """Write ai_reviewed status to DB after compliance+fraud complete, before advisor.

    Non-fatal: if the DB call fails, the advisor will still run and set the
    final status. This intermediate status provides audit trail visibility.
    """
    dbClaimId = state.get("dbClaimId")
    claimId = state.get("claimId", "unknown")

    if dbClaimId is not None:
        try:
            settings = getSettings()
            await mcpCallTool(
                serverUrl=settings.db_mcp_url,
                toolName="updateClaimStatus",
                arguments={
                    "claimId": dbClaimId,
                    "newStatus": "ai_reviewed",
                    "actor": "system",
                },
            )
            logger.info("markAiReviewedNode: status set to ai_reviewed", extra={"claimId": claimId, "dbClaimId": dbClaimId})
        except Exception as e:
            logger.warning(
                "markAiReviewedNode: failed to update status — continuing to advisor",
                extra={"claimId": claimId, "error": str(e)},
            )

    return {"status": "ai_reviewed"}


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

    # Add agent nodes
    builder.add_node("intake", intakeNode)
    builder.add_node("compliance", complianceNode)
    builder.add_node("fraud", fraudNode)
    builder.add_node("debugLlm", debugLlmNode)
    builder.add_node("markAiReviewed", markAiReviewedNode)
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

    # Fan-out from postSubmission to compliance, fraud, and debug (parallel)
    builder.add_edge("postSubmission", "compliance")
    builder.add_edge("postSubmission", "fraud")
    builder.add_edge("postSubmission", "debugLlm")

    # Fan-in to markAiReviewed, then advisor
    builder.add_edge("compliance", "markAiReviewed")
    builder.add_edge("fraud", "markAiReviewed")
    builder.add_edge("debugLlm", "markAiReviewed")
    builder.add_edge("markAiReviewed", "advisor")
    builder.add_edge("advisor", END)

    return builder


async def getCompiledGraph():
    """Create compiled graph with Postgres checkpointer using a connection pool.

    Uses AsyncConnectionPool instead of a single connection so that
    astream_events can issue concurrent checkpoint reads/writes without
    hitting psycopg's one-command-at-a-time limitation.

    Returns:
        Tuple of (compiled graph, connection pool)
    """
    settings = getSettings()

    pool = AsyncConnectionPool(
        conninfo=settings.postgres_dsn,
        max_size=20,
        open=False,
    )
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    builder = buildGraph()
    graph = builder.compile(checkpointer=checkpointer)

    return graph, pool
