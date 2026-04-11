"""Policy search tool using RAG MCP server."""

import logging
import time

from langchain_core.tools import tool

from agentic_claims.agents.intake.auditLogger import bufferStep
from agentic_claims.agents.intake.extractionContext import sessionClaimIdVar
from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


@tool
async def searchPolicies(query: str, limit: int = 5, claimId: str | None = None) -> list | dict:
    """Search company policy documents using RAG.

    Args:
        query: Search query describing the policy question
        limit: Maximum number of policy chunks to return (default: 5)
        claimId: Session claim ID for audit buffering (optional)

    Returns:
        List of policy chunks with text, file, category, section, and relevance score,
        or error dict if search fails
    """
    toolStart = time.time()
    logEvent(logger, "tool.searchPolicies.started", logCategory="tool", toolName="searchPolicies", mcpServer="mcp-rag", query=query, limit=limit)

    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": query, "limit": limit},
    )

    logEvent(
        logger,
        "tool.searchPolicies.completed",
        logCategory="tool",
        toolName="searchPolicies",
        mcpServer="mcp-rag",
        elapsed=f"{time.time() - toolStart:.2f}s",
        resultCount=len(result) if isinstance(result, list) else 0,
    )

    # Buffer policy check audit step using session claimId from ContextVar fallback
    effectiveClaimId = claimId or sessionClaimIdVar.get(None)
    if effectiveClaimId and isinstance(result, list):
        policyRefs = [
            {"section": r.get("section"), "category": r.get("category"), "score": r.get("score")}
            for r in result
            if isinstance(r, dict)
        ]
        bufferStep(
            sessionClaimId=effectiveClaimId,
            action="policy_check",
            details={
                "violations": [],
                "policyRefs": policyRefs,
                "compliant": True,
                "query": query,
            },
        )

    return result
