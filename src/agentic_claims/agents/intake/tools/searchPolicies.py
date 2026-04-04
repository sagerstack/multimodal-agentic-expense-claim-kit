"""Policy search tool using RAG MCP server."""

import logging
import time
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings


@tool
async def searchPolicies(query: str, limit: int = 5) -> list | dict:
    """Search company policy documents using RAG.

    Args:
        query: Search query describing the policy question
        limit: Maximum number of policy chunks to return (default: 5)

    Returns:
        List of policy chunks with text, file, category, section, and relevance score,
        or error dict if search fails
    """
    toolStart = time.time()
    logger.info("searchPolicies started", extra={"query": query, "limit": limit})

    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": query, "limit": limit},
    )

    logger.info("searchPolicies completed", extra={"elapsed": f"{time.time() - toolStart:.2f}s", "resultCount": len(result) if isinstance(result, list) else 0})
    return result
