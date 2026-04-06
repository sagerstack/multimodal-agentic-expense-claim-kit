"""Advisor tool: policy search via RAG MCP.

Separate tool registration for the Advisor Agent so it has its own
@tool-decorated callable. Used optionally to cite policy clauses in the
advisor's decision reasoning.
"""

import logging

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)


@tool
async def searchPolicies(query: str, limit: int = 5) -> list | dict:
    """Search SUTD expense policy documents using semantic search.

    Use this to find specific policy clauses that justify or qualify
    the advisor routing decision — e.g. to confirm approval thresholds,
    cite grounds for escalation, or provide policy references in notifications.

    Args:
        query: Natural language question or keyword describing the policy area.
               Example: "meal expense approval threshold SGD 500"
        limit: Maximum number of policy chunks to return (default: 5).

    Returns:
        List of policy chunks: [{text, file, category, section, score}],
        or error dict if the RAG MCP server is unreachable.
    """
    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": query, "limit": limit},
    )

    return result
