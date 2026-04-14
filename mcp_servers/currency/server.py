"""Currency MCP Server for currency conversion via Frankfurter API."""

import logging
from datetime import datetime
from typing import Any

import httpx
from fastmcp import FastMCP

# Frankfurter API base URL (free, no API key required)
FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"

# Initialize FastMCP server
mcp = FastMCP("currency-server")

logger = logging.getLogger(__name__)


@mcp.tool()
def convertCurrency(
    amount: float, fromCurrency: str, toCurrency: str = "SGD"
) -> dict[str, Any]:
    """
    Convert currency using Frankfurter API (European Central Bank rates).

    Returns a structured dict with a `supported` key on every path:
      - Success:  {supported: True, originalAmount, originalCurrency,
                   convertedAmount, convertedCurrency, rate, date}
      - Unsupported currency (Frankfurter 404):
                  {supported: False, currency, error: "unsupported", provider: "frankfurter"}

    No secondary provider and no caching (locked decisions per 13-CONTEXT.md).

    Args:
        amount: Amount to convert
        fromCurrency: Source currency code (e.g., USD, EUR, GBP)
        toCurrency: Target currency code (default SGD)

    Returns:
        Structured conversion result with explicit `supported` key
    """
    try:
        # Call Frankfurter API
        response = httpx.get(
            f"{FRANKFURTER_BASE_URL}/latest",
            params={"from": fromCurrency.upper(), "to": toCurrency.upper()},
            timeout=10.0,
            verify=False,
        )
        response.raise_for_status()

        data = response.json()

        # Extract rate and calculate converted amount
        rate = data["rates"].get(toCurrency.upper())
        if rate is None:
            return {"supported": False, "currency": fromCurrency.upper(), "error": "unsupported", "provider": "frankfurter"}

        convertedAmount = round(amount * rate, 2)

        return {
            "supported": True,
            "originalAmount": amount,
            "originalCurrency": fromCurrency.upper(),
            "convertedAmount": convertedAmount,
            "convertedCurrency": toCurrency.upper(),
            "rate": rate,
            "date": data.get("date", datetime.now().strftime("%Y-%m-%d")),
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.info(
                "mcp.currency.unsupported",
                extra={"currency": fromCurrency, "provider": "frankfurter", "statusCode": 404},
            )
            return {
                "supported": False,
                "currency": fromCurrency.upper(),
                "error": "unsupported",
                "provider": "frankfurter",
            }
        raise  # Let non-404 HTTP errors surface through existing error path
    except httpx.RequestError as e:
        return {"error": f"Network error: {e}"}
    except Exception as e:
        return {"error": f"Currency conversion failed: {e}"}


@mcp.tool()
def getSupportedCurrencies() -> list[str]:
    """
    Get list of supported currencies from Frankfurter API.

    Returns:
        List of currency codes
    """
    try:
        response = httpx.get(f"{FRANKFURTER_BASE_URL}/currencies", timeout=10.0, verify=False)
        response.raise_for_status()

        currencies = response.json()
        return sorted(currencies.keys())
    except Exception as e:
        return [f"Error: {e}"]


@mcp.resource("frankfurter://health")
def getFrankfurterHealth() -> str:
    """Check Frankfurter API health."""
    try:
        response = httpx.get(f"{FRANKFURTER_BASE_URL}/latest", timeout=5.0, verify=False)
        response.raise_for_status()
        return "Connected to Frankfurter API"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    # Start FastMCP server with Streamable HTTP transport
    mcp.run(transport="streamable-http")
