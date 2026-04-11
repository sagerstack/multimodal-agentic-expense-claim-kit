"""Currency conversion tool using Currency MCP server."""

import logging
import time
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent


@tool
async def convertCurrency(amount: float, fromCurrency: str, toCurrency: str) -> dict:
    """Convert currency using live exchange rates.

    Args:
        amount: Amount to convert
        fromCurrency: Source currency code (e.g., "USD")
        toCurrency: Target currency code (e.g., "SGD")

    Returns:
        Conversion result with originalAmount, convertedAmount, rate, and date,
        or error dict if conversion fails
    """
    toolStart = time.time()
    logEvent(logger, "tool.convertCurrency.started", logCategory="tool", toolName="convertCurrency", mcpServer="mcp-currency", amount=amount, fromCurrency=fromCurrency, toCurrency=toCurrency)

    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.currency_mcp_url,
        toolName="convertCurrency",
        arguments={"amount": amount, "fromCurrency": fromCurrency, "toCurrency": toCurrency},
    )

    logEvent(logger, "tool.convertCurrency.completed", logCategory="tool", toolName="convertCurrency", mcpServer="mcp-currency", elapsed=f"{time.time() - toolStart:.2f}s")
    return result
