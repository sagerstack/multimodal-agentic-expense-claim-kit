"""Database MCP Server for Postgres CRUD operations."""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from fastmcp import FastMCP
from psycopg.types.json import Json

# Environment configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://agentic:password@localhost:5432/agentic_claims"
)

# Initialize FastMCP server
mcp = FastMCP("db-server")

# Global connection (initialized on startup)
dbConnection: psycopg.Connection | None = None


def getConnection() -> psycopg.Connection:
    """Get or create database connection."""
    global dbConnection
    if dbConnection is None or dbConnection.closed:
        dbConnection = psycopg.connect(DATABASE_URL)
    return dbConnection


def serializeRow(row: dict) -> dict:
    """Convert non-JSON-serializable values (datetime, Decimal) to strings."""
    return {
        k: (
            v.isoformat()
            if isinstance(v, (datetime, date))
            else float(v)
            if isinstance(v, Decimal)
            else v
        )
        for k, v in row.items()
    }


@mcp.tool()
def executeQuery(query: str) -> list[dict[str, Any]]:
    """
    Execute read-only SQL query against Postgres.

    Args:
        query: SQL SELECT query

    Returns:
        List of rows as dictionaries
    """
    # Safety check: only allow SELECT queries
    queryStripped = query.strip().upper()
    if not queryStripped.startswith("SELECT"):
        return [{"error": "Only SELECT queries are allowed via executeQuery"}]

    try:
        conn = getConnection()
        with conn.cursor() as cur:
            cur.execute(query)
            columns = [desc[0] for desc in cur.description] if cur.description else []
            rows = cur.fetchall()

            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        return [{"error": f"Query execution failed: {e}"}]


@mcp.tool()
def insertClaim(
    employeeId: str,
    status: str,
    totalAmount: float,
    currency: str = "SGD",
    category: str | None = None,
    intakeFindings: dict | None = None,
    claimNumber: str | None = None,
    idempotencyKey: str | None = None,
    receiptNumber: str | None = None,
    merchant: str | None = None,
    receiptDate: str | None = None,
    receiptTotalAmount: float | None = None,
    receiptCurrency: str | None = None,
    lineItems: list | None = None,
    imagePath: str | None = None,
    paymentMethod: str | None = None,
    taxAmount: float | None = None,
    originalAmount: float | None = None,
    originalCurrency: str | None = None,
    convertedAmount: float | None = None,
    convertedCurrency: str | None = None,
    exchangeRate: float | None = None,
    conversionDate: str | None = None,
) -> dict[str, Any]:
    """
    Insert a new claim and optionally its receipt atomically.

    Args:
        employeeId: Employee ID who created the claim
        status: Claim status (draft, pending, approved, rejected, paid)
        totalAmount: Total claim amount
        currency: Currency code (default SGD)
        category: Expense category (meals, transport, accommodation, office_supplies, general)
        intakeFindings: Agent observations (mismatches, overrides, red flags)
        claimNumber: Unique claim identifier (optional, DB generates via sequence if omitted)
        idempotencyKey: Natural key for deduplication (optional, enables ON CONFLICT)
        receiptNumber: Unique receipt identifier (optional)
        merchant: Merchant name (optional)
        receiptDate: Receipt date (optional)
        receiptTotalAmount: Receipt total amount (optional)
        receiptCurrency: Receipt currency (optional)
        lineItems: Line items as list of dicts (optional)
        imagePath: Path to receipt image (optional)
        paymentMethod: Payment method (optional)
        taxAmount: Tax amount (optional)
        originalAmount: Original amount before conversion (optional)
        originalCurrency: Original currency code (optional)
        convertedAmount: Converted amount in SGD (optional)
        convertedCurrency: Converted currency code (optional)
        exchangeRate: Exchange rate used (optional)
        conversionDate: Date of conversion (optional)

    Returns:
        Dict with "claim" and "receipt" keys containing the inserted records,
        or note key if duplicate detected
    """
    conn = getConnection()
    try:
        with conn.cursor() as cur:
            # Build claim INSERT with idempotent pattern
            if idempotencyKey:
                # Idempotent insert: ON CONFLICT DO NOTHING, then fetch existing if duplicate
                if claimNumber:
                    # Legacy path: claimNumber provided (backwards compatibility)
                    claimSql = """
                        INSERT INTO claims (
                            claim_number, employee_id, status,
                            total_amount, currency, category, intake_findings,
                            original_amount, original_currency,
                            converted_amount_sgd, idempotency_key
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING id, claim_number, employee_id, status,
                                  total_amount, currency, category, intake_findings,
                                  original_amount, original_currency,
                                  converted_amount_sgd, created_at, updated_at
                    """
                    claimParams = (
                        claimNumber,
                        employeeId,
                        status,
                        totalAmount,
                        currency,
                        category,
                        Json(intakeFindings or {}),
                        originalAmount,
                        originalCurrency,
                        convertedAmount,
                        idempotencyKey,
                    )
                else:
                    # Standard path: DB generates claim_number via DEFAULT (sequence)
                    claimSql = """
                        INSERT INTO claims (
                            employee_id, status, total_amount, currency,
                            category, intake_findings, original_amount, original_currency,
                            converted_amount_sgd, idempotency_key
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        RETURNING id, claim_number, employee_id, status,
                                  total_amount, currency, category, intake_findings,
                                  original_amount, original_currency,
                                  converted_amount_sgd, created_at, updated_at
                    """
                    claimParams = (
                        employeeId,
                        status,
                        totalAmount,
                        currency,
                        category,
                        Json(intakeFindings or {}),
                        originalAmount,
                        originalCurrency,
                        convertedAmount,
                        idempotencyKey,
                    )

                cur.execute(claimSql, claimParams)
                claimColumns = [desc[0] for desc in cur.description]
                claimRow = cur.fetchone()

                # If no row returned, duplicate detected — fetch existing
                if not claimRow:
                    cur.execute(
                        """
                        SELECT id, claim_number, employee_id, status,
                               total_amount, currency, intake_findings,
                               original_amount, original_currency,
                               converted_amount_sgd, created_at, updated_at
                        FROM claims WHERE idempotency_key = %s
                        """,
                        (idempotencyKey,),
                    )
                    claimColumns = [desc[0] for desc in cur.description]
                    claimRow = cur.fetchone()
                    if not claimRow:
                        conn.rollback()
                        return {"error": "Claim insert failed and existing claim not found"}

                    claimRecord = serializeRow(dict(zip(claimColumns, claimRow)))
                    conn.rollback()  # No changes to commit
                    claimNum = claimRecord.get("claim_number", "unknown")
                    claimDate = claimRecord.get("created_at", "unknown date")
                    return {
                        "error": (
                            f"Duplicate receipt detected. This receipt was already "
                            f"submitted as {claimNum} on {claimDate}. "
                            f"Each receipt can only be submitted once."
                        ),
                        "existingClaimNumber": claimRecord.get("claim_number"),
                    }

                claimRecord = serializeRow(dict(zip(claimColumns, claimRow)))
            else:
                # Non-idempotent path (backwards compatibility or testing)
                # Generate a fallback idempotency_key to satisfy NOT NULL constraint
                import uuid as _uuid
                fallbackKey = f"auto_{_uuid.uuid4().hex[:16]}"

                if claimNumber:
                    claimSql = """
                        INSERT INTO claims (
                            claim_number, employee_id, status,
                            total_amount, currency, category, intake_findings,
                            original_amount, original_currency, converted_amount_sgd,
                            idempotency_key
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, claim_number, employee_id, status,
                                  total_amount, currency, category, intake_findings,
                                  original_amount, original_currency,
                                  converted_amount_sgd, created_at, updated_at
                    """
                    claimParams = (
                        claimNumber,
                        employeeId,
                        status,
                        totalAmount,
                        currency,
                        category,
                        Json(intakeFindings or {}),
                        originalAmount,
                        originalCurrency,
                        convertedAmount,
                        fallbackKey,
                    )
                else:
                    # DB generates claim_number via DEFAULT
                    claimSql = """
                        INSERT INTO claims (
                            employee_id, status, total_amount, currency,
                            category, intake_findings, original_amount,
                            original_currency, converted_amount_sgd,
                            idempotency_key
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id, claim_number, employee_id, status,
                                  total_amount, currency, category, intake_findings,
                                  original_amount, original_currency,
                                  converted_amount_sgd, created_at, updated_at
                    """
                    claimParams = (
                        employeeId,
                        status,
                        totalAmount,
                        currency,
                        category,
                        Json(intakeFindings or {}),
                        originalAmount,
                        originalCurrency,
                        convertedAmount,
                        fallbackKey,
                    )

                cur.execute(claimSql, claimParams)
                claimColumns = [desc[0] for desc in cur.description]
                claimRow = cur.fetchone()
                if not claimRow:
                    conn.rollback()
                    return {"error": "Claim insert failed"}

                claimRecord = serializeRow(dict(zip(claimColumns, claimRow)))
            claimId = claimRecord["id"]

            # Insert receipt if receipt data provided
            receiptRecord = None
            if receiptNumber and merchant and receiptDate:
                cur.execute(
                    """
                    INSERT INTO receipts (
                        claim_id, receipt_number, merchant, date,
                        total_amount, currency, line_items, image_path,
                        original_amount, original_currency, converted_amount_sgd
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, claim_id, receipt_number, merchant, date,
                              total_amount, currency, line_items, image_path,
                              original_amount, original_currency,
                              converted_amount_sgd, created_at, updated_at
                    """,
                    (
                        claimId,
                        receiptNumber,
                        merchant,
                        receiptDate,
                        receiptTotalAmount or 0.0,
                        receiptCurrency or currency,
                        Json(lineItems or []),
                        imagePath,
                        originalAmount,
                        originalCurrency,
                        convertedAmount,
                    ),
                )
                receiptColumns = [desc[0] for desc in cur.description]
                receiptRow = cur.fetchone()
                if receiptRow:
                    receiptRecord = serializeRow(dict(zip(receiptColumns, receiptRow)))

            conn.commit()

            return {
                "claim": claimRecord,
                "receipt": receiptRecord if receiptRecord else None,
            }

    except Exception as e:
        conn.rollback()
        return {"error": f"Insert claim failed: {e}"}


@mcp.tool()
def insertAuditLog(
    claimId: int, action: str, newValue: str, actor: str, oldValue: str = ""
) -> dict[str, Any]:
    """
    Insert an audit log entry for a claim.

    Args:
        claimId: Claim ID to log against
        action: Audit action label (e.g., 'receipt_uploaded', 'ai_extraction', 'policy_check')
        newValue: JSON-encoded details for this audit step
        actor: System/user that performed the action
        oldValue: Optional previous value (default empty)

    Returns:
        Dict with id and timestamp of the inserted row
    """
    try:
        conn = getConnection()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_log "
                "(claim_id, action, old_value, new_value, actor) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id, timestamp",
                (claimId, action, oldValue, newValue, actor),
            )
            conn.commit()
            row = cur.fetchone()
            return {"id": row[0], "timestamp": row[1].isoformat()}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": f"insertAuditLog failed: {e}"}


@mcp.tool()
def updateClaimStatus(
    claimId: int,
    newStatus: str,
    actor: str,
    complianceFindings: dict | None = None,
    fraudFindings: dict | None = None,
    advisorDecision: str | None = None,
    advisorFindings: dict | None = None,
    approvedBy: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """
    Update claim status and insert audit log entry.

    Optionally persists agent output columns (compliance_findings,
    fraud_findings, advisor_decision, advisor_findings, approved_by) when provided.

    Args:
        claimId: Claim ID to update
        newStatus: New status value
        actor: User/system performing the update
        complianceFindings: Structured compliance verdict dict (optional)
        fraudFindings: Structured fraud verdict dict (optional)
        advisorDecision: Advisor routing decision string (optional)
        advisorFindings: Structured advisor reasoning dict (optional)
        approvedBy: Actor who approved (e.g. "agent" for auto-approve) (optional)
        category: Expense category to update (optional)

    Returns:
        Updated claim record
    """
    try:
        conn = getConnection()
        with conn.cursor() as cur:
            # Get old status for audit log
            cur.execute("SELECT status FROM claims WHERE id = %s", (claimId,))
            result = cur.fetchone()
            if not result:
                return {"error": f"Claim {claimId} not found"}

            oldStatus = result[0]

            # Build dynamic SET clause based on optional agent findings
            setClauses = ["status = %s", "updated_at = NOW()"]
            params: list = [newStatus]

            if complianceFindings is not None:
                setClauses.append("compliance_findings = %s")
                params.append(Json(complianceFindings))
            if fraudFindings is not None:
                setClauses.append("fraud_findings = %s")
                params.append(Json(fraudFindings))
            if advisorDecision is not None:
                setClauses.append("advisor_decision = %s")
                params.append(advisorDecision)
            if advisorFindings is not None:
                setClauses.append("advisor_findings = %s")
                params.append(Json(advisorFindings))
            if approvedBy is not None:
                setClauses.append("approved_by = %s")
                params.append(approvedBy)
            if category is not None:
                setClauses.append("category = %s")
                params.append(category)

            params.append(claimId)

            cur.execute(
                f"""
                UPDATE claims
                SET {', '.join(setClauses)}
                WHERE id = %s
                RETURNING id, claim_number, employee_id, status,
                          total_amount, currency, created_at, updated_at
                """,
                params,
            )

            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            updatedClaim = serializeRow(dict(zip(columns, row))) if row else {}

            # Insert audit log
            cur.execute(
                """
                INSERT INTO audit_log (claim_id, action, actor, old_value, new_value)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (claimId, "status_change", actor, oldStatus, newStatus),
            )

            conn.commit()
            return updatedClaim
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": f"Update claim status failed: {e}"}


@mcp.tool()
def getClaimSchema() -> dict[str, Any]:
    """Get the database schema for claims and receipts tables.

    Returns column names, types, and nullable status for both tables.
    Agents use this to discover required/optional fields dynamically.

    Returns:
        Dict with 'claims' and 'receipts' keys, each containing a list of
        column descriptors {name, type, nullable, has_default}
    """
    conn = getConnection()
    try:
        with conn.cursor() as cur:
            schema = {}
            for tableName in ("claims", "receipts"):
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = 'public'
                    ORDER BY ordinal_position
                    """,
                    (tableName,),
                )
                columns = []
                for row in cur.fetchall():
                    columns.append(
                        {
                            "name": row[0],
                            "type": row[1],
                            "nullable": row[2] == "YES",
                            "hasDefault": row[3] is not None,
                        }
                    )
                schema[tableName] = columns
            return schema
    except Exception as e:
        return {"error": f"Failed to get schema: {e}"}


@mcp.tool()
def getClaimWithReceipts(claimId: int) -> dict[str, Any]:
    """
    Get claim with all linked receipts.

    Args:
        claimId: Claim ID

    Returns:
        Claim record with nested receipts list
    """
    try:
        conn = getConnection()
        with conn.cursor() as cur:
            # Get claim
            cur.execute(
                """
                SELECT id, claim_number, employee_id, status,
                       total_amount, currency, created_at, updated_at
                FROM claims
                WHERE id = %s
                """,
                (claimId,),
            )
            claimColumns = [desc[0] for desc in cur.description]
            claimRow = cur.fetchone()

            if not claimRow:
                return {"error": f"Claim {claimId} not found"}

            claim = serializeRow(dict(zip(claimColumns, claimRow)))

            # Get receipts
            cur.execute(
                """
                SELECT id, claim_id, receipt_number, merchant, date,
                       total_amount, currency, image_path, line_items,
                       created_at, updated_at
                FROM receipts
                WHERE claim_id = %s
                ORDER BY date
                """,
                (claimId,),
            )
            receiptColumns = [desc[0] for desc in cur.description]
            receiptRows = cur.fetchall()

            claim["receipts"] = [
                serializeRow(dict(zip(receiptColumns, row))) for row in receiptRows
            ]

            return claim
    except Exception as e:
        return {"error": f"Get claim with receipts failed: {e}"}


@mcp.resource("postgres://health")
def getDatabaseHealth() -> str:
    """Check database connection health."""
    try:
        conn = getConnection()
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()
            return f"Connected. PostgreSQL {version[0] if version else 'unknown'}"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    # Start FastMCP server with Streamable HTTP transport
    mcp.run(transport="streamable-http")
