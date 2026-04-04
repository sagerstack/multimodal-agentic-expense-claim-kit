"""Claim schema discovery tool using DB MCP server."""

import logging
import time
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings


@tool
async def getClaimSchema() -> dict:
    """Get the database schema for claims and receipts tables.

    Returns column names, types, and nullable status so the agent
    can discover required and optional fields dynamically.

    Returns:
        Dict with 'claims' and 'receipts' keys containing column metadata,
        or error dict if schema lookup fails
    """
    toolStart = time.time()
    logger.info("getClaimSchema started")

    settings = getSettings()
    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="getClaimSchema",
        arguments={},
    )

    logger.info("getClaimSchema completed", extra={"elapsed": f"{time.time() - toolStart:.2f}s"})
    return result
