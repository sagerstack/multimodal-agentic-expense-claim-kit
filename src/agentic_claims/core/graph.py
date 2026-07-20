"""LangGraph StateGraph definition with parallel fan-out and Postgres checkpointer."""

import inspect
import logging
from contextvars import ContextVar
from functools import wraps
from importlib import import_module
from typing import Any, Callable

from agentic_governance.integrations.langgraph_mcp import install
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from agentic_claims.agents.advisor.node import advisorNode
from agentic_claims.agents.compliance.node import complianceNode
from agentic_claims.agents.fraud.node import fraudNode
from agentic_claims.agents.intake.extractionContext import (
    extractedReceiptVar,
    sessionClaimIdVar,
)
from agentic_claims.agents.intake.node import intakeNode, postIntakeRouter, preIntakeValidator
from agentic_claims.agents.intake.nodes.humanEscalation import humanEscalationNode
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool as _realMcpCallTool
from agentic_claims.agents.intake_gpt.node import intakeGptNode
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.core.state import ClaimState
from agentic_claims.web.employeeIdContext import employeeIdVar

logger = logging.getLogger(__name__)

# Rebound to the governed callable when buildGraph installs the composition root.
mcpCallTool = _realMcpCallTool
nodeIdentityVar: ContextVar[str | None] = ContextVar("nodeIdentityVar", default=None)

_MCP_CALL_TOOL_IMPORTERS = (
    "agentic_claims.agents.advisor.node",
    "agentic_claims.agents.advisor.tools.searchPolicies",
    "agentic_claims.agents.advisor.tools.sendNotification",
    "agentic_claims.agents.advisor.tools.updateClaimStatus",
    "agentic_claims.agents.compliance.node",
    "agentic_claims.agents.fraud.node",
    "agentic_claims.agents.fraud.tools.queryClaimsHistory",
    "agentic_claims.agents.intake.auditLogger",
    "agentic_claims.agents.intake.nodes.humanEscalation",
    "agentic_claims.agents.intake.tools.convertCurrency",
    "agentic_claims.agents.intake.tools.getClaimSchema",
    "agentic_claims.agents.intake.tools.searchPolicies",
    "agentic_claims.agents.intake.tools.submitClaim",
    "agentic_claims.core.graph",
    "agentic_claims.web.routers.chat",
)


def _installGovernedMcpBoundary() -> None:
    """Install governance and replace every bound import of the real MCP boundary."""
    governedMcpCallTool = install(
        real_mcp_call_tool=_realMcpCallTool,
        employee_id_provider=lambda: employeeIdVar.get(None),
        extracted_receipt_provider=lambda: extractedReceiptVar.get(None),
        session_claim_id_provider=lambda: sessionClaimIdVar.get(None),
        node_identity_provider=lambda: nodeIdentityVar.get(None),
    )
    for moduleName in _MCP_CALL_TOOL_IMPORTERS:
        setattr(import_module(moduleName), "mcpCallTool", governedMcpCallTool)


def _withNodeIdentity(nodeName: str, nodeCallable: Callable[..., Any]) -> Callable[..., Any]:
    """Set trusted node identity for the duration of one graph-node call."""

    @wraps(nodeCallable)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        token = nodeIdentityVar.set(nodeName)
        try:
            result = nodeCallable(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result
        finally:
            nodeIdentityVar.reset(token)

    return _wrapped


def evaluatorGate(state: ClaimState) -> str:
    """Route based on whether claim has been submitted.

    Args:
        state: Current claim state

    Returns:
        "submitted" if claim was submitted (route to compliance+fraud),
        "pending" if still in intake conversation (route to END)
    """
    result = "submitted" if state.get("claimSubmitted", False) else "pending"
    logEvent(
        logger,
        "graph.evaluator_gate",
        logCategory="graph",
        claimId=state.get("claimId"),
        decision=result,
        message="evaluatorGate decision",
    )
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
            logEvent(
                logger,
                "graph.mark_ai_reviewed",
                logCategory="graph",
                claimId=claimId,
                dbClaimId=dbClaimId,
                message="markAiReviewedNode: status set to ai_reviewed",
            )
        except Exception as e:
            logEvent(
                logger,
                "graph.mark_ai_reviewed_error",
                level=logging.WARNING,
                logCategory="graph",
                claimId=claimId,
                error=str(e),
                message="markAiReviewedNode: failed to update status — continuing to advisor",
            )

    return {"status": "ai_reviewed"}


def buildGraph() -> StateGraph:
    """Build the StateGraph with Phase 13 wrapper-graph topology.

    Graph topology (Phase 13):
        START -> preIntakeValidator -> intake -> postIntakeRouter
          ├─ humanEscalation -> END   (escalation: validatorEscalate OR askHumanCount > 3)
          └─ evaluatorGate
               ├─ submitted -> postSubmission -> [compliance || fraud || debugLlm]
               │                              -> markAiReviewed -> advisor -> END
               └─ pending -> END

    Phase 13 notes:
    - preIntakeValidator increments turnIndex, runs postToolFlagSetter + submitClaimGuard
    - postIntakeRouter is the conditional edge after intake (replaces the old direct
      conditional edge from intake to evaluatorGate)
    - evaluatorGate is unchanged — it remains the submitted/pending router
    - humanEscalation is terminal: its edge goes directly to END
    - AsyncPostgresSaver is the sole checkpointer on the outer compile (no secondary)

    Returns:
        Uncompiled StateGraph builder
    """
    _installGovernedMcpBoundary()
    builder = StateGraph(ClaimState)
    settings = getSettings()
    intakeNodeImpl = intakeGptNode if settings.intake_agent_mode.lower() == "gpt" else intakeNode

    # Add agent nodes with request-local identity available to governance providers.
    builder.add_node(
        "preIntakeValidator", _withNodeIdentity("preIntakeValidator", preIntakeValidator)
    )
    builder.add_node("intake", _withNodeIdentity("intake", intakeNodeImpl))
    builder.add_node("humanEscalation", _withNodeIdentity("humanEscalation", humanEscalationNode))
    builder.add_node("compliance", _withNodeIdentity("compliance", complianceNode))
    builder.add_node("fraud", _withNodeIdentity("fraud", fraudNode))
    builder.add_node("markAiReviewed", _withNodeIdentity("markAiReviewed", markAiReviewedNode))
    builder.add_node("advisor", _withNodeIdentity("advisor", advisorNode))

    # START -> preIntakeValidator -> intake
    builder.add_edge(START, "preIntakeValidator")
    builder.add_edge("preIntakeValidator", "intake")

    # Phase 13 conditional edge from intake:
    #   postIntakeRouter decides humanEscalation vs. evaluatorGate path
    # evaluatorGate is still a conditional function — "continue" resolves
    # to evaluatorGate as a *node-level routing call* by using a lambda
    # that runs evaluatorGate and maps its result to postSubmission/END.
    #
    # Implementation: use a combined conditional that:
    #   1. Checks postIntakeRouter first (escalation takes precedence)
    #   2. Falls through to evaluatorGate for the non-escalation branch
    #   The "continue" branch from postIntakeRouter invokes evaluatorGate
    #   inline so we keep a single add_conditional_edges call.
    builder.add_node(
        "postSubmission",
        _withNodeIdentity("postSubmission", lambda state: state),
    )  # Pass-through node

    def _intakeConditionalRouter(state: ClaimState) -> str:
        """Combined router: escalation check → evaluator gate.

        Escalation takes precedence over submitted/pending routing.
        postIntakeRouter returns 'humanEscalation' or 'continue'.
        When 'continue', evaluatorGate decides submitted/pending.
        """
        branch = postIntakeRouter(state)
        if branch == "humanEscalation":
            return "humanEscalation"
        # continue path: delegate to evaluatorGate
        return evaluatorGate(state)  # returns "submitted" or "pending"

    builder.add_conditional_edges(
        "intake",
        _intakeConditionalRouter,
        {
            "humanEscalation": "humanEscalation",
            "submitted": "postSubmission",
            "pending": END,
        },
    )

    # humanEscalation is terminal
    builder.add_edge("humanEscalation", END)

    # Fan-out from postSubmission to compliance and fraud (parallel)
    builder.add_edge("postSubmission", "compliance")
    builder.add_edge("postSubmission", "fraud")

    # Fan-in to markAiReviewed, then advisor
    builder.add_edge("compliance", "markAiReviewed")
    builder.add_edge("fraud", "markAiReviewed")
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

    # Setup checkpointer tables with autocommit so CREATE INDEX CONCURRENTLY
    # (used by langgraph-checkpoint-postgres >=3.0.5) can run outside a transaction.
    async with await AsyncConnection.connect(settings.postgres_dsn, autocommit=True) as setupConn:
        setupSaver = AsyncPostgresSaver(setupConn)
        await setupSaver.setup()

    checkpointer = AsyncPostgresSaver(pool)

    builder = buildGraph()
    graph = builder.compile(checkpointer=checkpointer)

    return graph, pool
