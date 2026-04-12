"""Currency conversion tool using Currency MCP server.

Structured return contract per:
  - artifacts/research/2026-04-12-multi-turn-react-prompt-technical.md L153 (Gap 3 fix)
  - 13-CONTEXT.md "Currency tool contract" decision
  - 13-RESEARCH.md Section 5 (files-to-modify map)

Every return value carries a `supported` key so downstream code never
pattern-matches on error strings:
  - Success:   {supported: True, originalAmount, convertedAmount, rate, date, ...}
  - Unsupported currency:
               {supported: False, currency, error: "unsupported", provider: "frankfurter"}
"""

import logging
import time
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent

# Markers that identify a legacy unsupported-currency error from the MCP layer
_UNSUPPORTED_MARKERS = ("404", "not found", "unsupported", "frankfurter api error:")


def _isUnsupportedCurrencyResult(result: object) -> bool:
    """Return True if result looks like a Frankfurter unsupported-currency error."""
    if isinstance(result, dict):
        errorVal = result.get("error", "")
        if isinstance(errorVal, str):
            errorLower = errorVal.lower()
            return any(marker in errorLower for marker in _UNSUPPORTED_MARKERS)
    if isinstance(result, str):
        resultLower = result.lower()
        return any(marker in resultLower for marker in _UNSUPPORTED_MARKERS)
    return False


@tool
async def convertCurrency(amount: float, fromCurrency: str, toCurrency: str) -> dict:
    """Convert currency using live exchange rates.

    Args:
        amount: Amount to convert
        fromCurrency: Source currency code (e.g., "USD")
        toCurrency: Target currency code (e.g., "SGD")

    Returns:
        Structured dict with `supported` key on every path:
        - {supported: True, originalAmount, convertedAmount, rate, date, ...} on success
        - {supported: False, currency, error: "unsupported", provider: "frankfurter"} on unsupported currency
    """
    toolStart = time.time()
    logEvent(
        logger,
        "tool.convertCurrency.started",
        logCategory="tool",
        toolName="convertCurrency",
        mcpServer="mcp-currency",
        amount=amount,
        fromCurrency=fromCurrency,
        toCurrency=toCurrency,
    )

    settings = getSettings()

    result = await mcpCallTool(
        serverUrl=settings.currency_mcp_url,
        toolName="convertCurrency",
        arguments={"amount": amount, "fromCurrency": fromCurrency, "toCurrency": toCurrency},
    )

    # --- Defence-in-depth normalisation ---
    # MCP server is the primary source of truth (already returns {supported}),
    # but this layer also handles historical / residual raw-string shapes gracefully.

    if isinstance(result, dict) and "supported" in result:
        # MCP server already returned the structured contract — pass through as-is
        normalised = result

    elif _isUnsupportedCurrencyResult(result):
        # Legacy raw-string or dict-with-error-string: normalise to structured shape
        logEvent(
            logger,
            "tool.convertCurrency.unsupported",
            logCategory="tool",
            toolName="convertCurrency",
            currency=fromCurrency,
            provider="frankfurter",
        )
        normalised = {
            "supported": False,
            "currency": fromCurrency,
            "error": "unsupported",
            "provider": "frankfurter",
        }

    elif isinstance(result, dict):
        # Successful dict without `supported` key (backward compatibility)
        normalised = {"supported": True, **result}

    else:
        # Unexpected shape — surface as generic error without supported key so
        # callers that check `result.get("supported", True)` see the error
        normalised = {"supported": True, "error": str(result)}

    logEvent(
        logger,
        "tool.convertCurrency.completed",
        logCategory="tool",
        toolName="convertCurrency",
        mcpServer="mcp-currency",
        elapsed=f"{time.time() - toolStart:.2f}s",
    )
    return normalised
