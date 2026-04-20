"""Currency conversion tool using Currency MCP server."""

from langchain_core.tools import tool

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings


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
    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.currency_mcp_url,
        toolName="convertCurrency",
        arguments={"amount": amount, "fromCurrency": fromCurrency, "toCurrency": toCurrency},
    )

    return result
