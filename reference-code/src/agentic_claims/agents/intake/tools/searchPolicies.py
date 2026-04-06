"""Policy search tool using RAG MCP server."""

from langchain_core.tools import tool

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
    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.rag_mcp_url,
        toolName="searchPolicies",
        arguments={"query": query, "limit": limit},
    )

    return result
