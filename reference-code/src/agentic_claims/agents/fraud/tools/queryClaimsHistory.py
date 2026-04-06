"""DB query helpers for fraud detection.

Author: jamesoon

Three targeted read-only queries against the claims + receipts tables:
  1. exactDuplicateCheck  — same employee + merchant + date + amount
  2. recentClaimsByEmployee — all claims from this employee in last 30 days
  3. claimsByMerchantAndEmployee — prior claims at the same merchant

All queries go through the DB MCP server's `executeQuery` tool (SELECT-only),
keeping fraud detection decoupled from the main app's SQLAlchemy models.
"""

import logging

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)


async def exactDuplicateCheck(
    employeeId: str,
    merchant: str,
    receiptDate: str,
    amountSgd: float,
) -> list[dict]:
    """Query for claims that match employee + merchant + date + amount exactly.

    A non-empty result is strong evidence of a duplicate submission.

    Args:
        employeeId: Employee ID from the claim under review
        merchant: Merchant name (case-insensitive match)
        receiptDate: Receipt date string in any format stored in DB
        amountSgd: Total amount in SGD (compared within ±0.01 tolerance)

    Returns:
        List of matching claim rows, or empty list if no duplicates found.
        Returns [{"error": ...}] on DB failure.
    """
    settings = getSettings()

    # Use ILIKE for merchant to handle minor casing/spacing differences
    # Amount tolerance of ±0.01 SGD handles floating point storage differences
    query = f"""
        SELECT
            c.id,
            c.claim_number,
            c.employee_id,
            c.status,
            c.total_amount,
            c.currency,
            c.created_at,
            r.merchant,
            r.date AS receipt_date,
            r.total_amount AS receipt_amount
        FROM claims c
        LEFT JOIN receipts r ON r.claim_id = c.id
        WHERE c.employee_id = '{employeeId}'
          AND r.merchant ILIKE '{merchant}'
          AND r.date::text LIKE '{receiptDate[:10]}%'
          AND ABS(c.total_amount - {amountSgd}) < 0.01
        ORDER BY c.created_at DESC
        LIMIT 10
    """

    logger.info(
        "exactDuplicateCheck query",
        extra={"employeeId": employeeId, "merchant": merchant, "date": receiptDate, "amount": amountSgd},
    )

    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="executeQuery",
        arguments={"query": query},
    )

    if isinstance(result, dict) and "error" in result:
        logger.warning("exactDuplicateCheck DB error", extra={"error": result["error"]})
        return [result]

    return result if isinstance(result, list) else []


async def recentClaimsByEmployee(employeeId: str, days: int = 30) -> list[dict]:
    """Fetch all claims submitted by the employee in the last N days.

    Used to detect frequency anomalies (e.g. many meals claims in one week).

    Args:
        employeeId: Employee ID to filter by
        days: Look-back window in days (default 30)

    Returns:
        List of claim rows with receipt info, newest first.
    """
    settings = getSettings()

    query = f"""
        SELECT
            c.id,
            c.claim_number,
            c.status,
            c.total_amount,
            c.currency,
            c.created_at,
            r.merchant,
            r.date AS receipt_date,
            r.total_amount AS receipt_amount,
            r.currency AS receipt_currency
        FROM claims c
        LEFT JOIN receipts r ON r.claim_id = c.id
        WHERE c.employee_id = '{employeeId}'
          AND c.created_at >= NOW() - INTERVAL '{days} days'
        ORDER BY c.created_at DESC
        LIMIT 50
    """

    logger.info(
        "recentClaimsByEmployee query",
        extra={"employeeId": employeeId, "days": days},
    )

    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="executeQuery",
        arguments={"query": query},
    )

    if isinstance(result, dict) and "error" in result:
        logger.warning("recentClaimsByEmployee DB error", extra={"error": result["error"]})
        return []

    return result if isinstance(result, list) else []


async def claimsByMerchantAndEmployee(employeeId: str, merchant: str) -> list[dict]:
    """Fetch all prior claims from this employee at the same merchant.

    Used to compute average spend and detect amount anomalies.

    Args:
        employeeId: Employee ID
        merchant: Merchant name (ILIKE match)

    Returns:
        List of claim rows ordered by date descending, max 20 rows.
    """
    settings = getSettings()

    query = f"""
        SELECT
            c.id,
            c.claim_number,
            c.status,
            c.total_amount,
            c.currency,
            c.created_at,
            r.merchant,
            r.date AS receipt_date,
            r.total_amount AS receipt_amount
        FROM claims c
        LEFT JOIN receipts r ON r.claim_id = c.id
        WHERE c.employee_id = '{employeeId}'
          AND r.merchant ILIKE '{merchant}'
        ORDER BY c.created_at DESC
        LIMIT 20
    """

    logger.info(
        "claimsByMerchantAndEmployee query",
        extra={"employeeId": employeeId, "merchant": merchant},
    )

    result = await mcpCallTool(
        serverUrl=settings.db_mcp_url,
        toolName="executeQuery",
        arguments={"query": query},
    )

    if isinstance(result, dict) and "error" in result:
        logger.warning("claimsByMerchantAndEmployee DB error", extra={"error": result["error"]})
        return []

    return result if isinstance(result, list) else []
