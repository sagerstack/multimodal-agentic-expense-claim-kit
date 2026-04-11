"""DB query helpers for fraud detection.

Three targeted read-only queries against the claims + receipts tables:
  1. exactDuplicateCheck  — same employee + merchant + date + amount
  2. recentClaimsByEmployee — all claims from this employee in last N days
  3. claimsByMerchantAndEmployee — prior claims at the same merchant

All queries go through the DB MCP server's `executeQuery` tool (SELECT-only),
keeping fraud detection decoupled from the main app's SQLAlchemy models.

SQL injection prevention: string values are passed through _sanitize() which
escapes single quotes before interpolation. Numeric values are cast to
float/int before interpolation. executeQuery does not support parameterized
queries, so this is the minimal viable defense.
"""

import logging

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool
from agentic_claims.core.config import getSettings

logger = logging.getLogger(__name__)


def _sanitize(value: str) -> str:
    """Escape single quotes in a string value for safe SQL interpolation.

    Replaces each ' with '' (standard SQL escaping). This prevents
    SQL injection when the executeQuery MCP tool does not support
    parameterized queries.

    Args:
        value: Raw string value to sanitize

    Returns:
        String with single quotes doubled
    """
    return str(value).replace("'", "''")


async def exactDuplicateCheck(
    employeeId: str,
    merchant: str,
    receiptDate: str,
    amountSgd: float,
    excludeClaimId: int | None = None,
) -> list[dict]:
    """Query for claims that match employee + merchant + date + amount exactly.

    A non-empty result is strong evidence of a duplicate submission.

    Args:
        employeeId: Employee ID from the claim under review
        merchant: Merchant name (case-insensitive match)
        receiptDate: Receipt date string in any format stored in DB
        amountSgd: Total amount in SGD (compared within 0.01 tolerance)

    Returns:
        List of matching claim rows, or empty list if no duplicates found.
    """
    settings = getSettings()

    safeEmployeeId = _sanitize(employeeId)
    safeMerchant = _sanitize(merchant)
    safeDate = _sanitize(receiptDate[:10] if receiptDate else "")
    safeAmount = float(amountSgd)
    excludeClause = ""
    if excludeClaimId is not None:
        excludeClause = f" AND c.id != {int(excludeClaimId)}"

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
        WHERE c.employee_id = '{safeEmployeeId}'
          AND r.merchant ILIKE '{safeMerchant}'
          AND r.date::text LIKE '{safeDate}%'
          AND ABS(c.total_amount - {safeAmount}) < 0.01
          {excludeClause}
        ORDER BY c.created_at DESC
        LIMIT 10
    """

    logger.info(
        "exactDuplicateCheck query",
        extra={
            "employeeId": employeeId,
            "merchant": merchant,
            "date": receiptDate,
            "amount": amountSgd,
            "excludeClaimId": excludeClaimId,
        },
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

    safeEmployeeId = _sanitize(employeeId)
    safeDays = int(days)

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
        WHERE c.employee_id = '{safeEmployeeId}'
          AND c.created_at >= NOW() - INTERVAL '{safeDays} days'
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

    safeEmployeeId = _sanitize(employeeId)
    safeMerchant = _sanitize(merchant)

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
        WHERE c.employee_id = '{safeEmployeeId}'
          AND r.merchant ILIKE '{safeMerchant}'
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
