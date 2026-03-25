"""Database MCP Server for Postgres CRUD operations."""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from fastmcp import FastMCP

# Environment configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://agentic:password@localhost:5432/agentic_claims")

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
        k: (v.isoformat() if isinstance(v, (datetime, date))
             else float(v) if isinstance(v, Decimal)
             else v)
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
    claimNumber: str,
    employeeId: str,
    status: str,
    totalAmount: float,
    currency: str = "SGD",
) -> dict[str, Any]:
    """
    Insert a new claim into the database.

    Args:
        claimNumber: Unique claim identifier
        employeeId: Employee ID who created the claim
        status: Claim status (draft, pending, approved, rejected, paid)
        totalAmount: Total claim amount
        currency: Currency code (default SGD)

    Returns:
        Newly created claim record
    """
    try:
        conn = getConnection()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO claims (claim_number, employee_id, status, total_amount, currency)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, claim_number, employee_id, status, total_amount, currency, created_at, updated_at
                """,
                (claimNumber, employeeId, status, totalAmount, currency),
            )
            conn.commit()

            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            return serializeRow(dict(zip(columns, row))) if row else {"error": "Insert failed"}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": f"Insert claim failed: {e}"}


@mcp.tool()
def updateClaimStatus(claimId: int, newStatus: str, actor: str) -> dict[str, Any]:
    """
    Update claim status and insert audit log entry.

    Args:
        claimId: Claim ID to update
        newStatus: New status value
        actor: User/system performing the update

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

            # Update claim status
            cur.execute(
                """
                UPDATE claims
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, claim_number, employee_id, status, total_amount, currency, created_at, updated_at
                """,
                (newStatus, claimId),
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
                SELECT id, claim_number, employee_id, status, total_amount, currency, created_at, updated_at
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
                SELECT id, claim_id, receipt_number, merchant, date, total_amount, currency, image_path, line_items, created_at, updated_at
                FROM receipts
                WHERE claim_id = %s
                ORDER BY date
                """,
                (claimId,),
            )
            receiptColumns = [desc[0] for desc in cur.description]
            receiptRows = cur.fetchall()

            claim["receipts"] = [serializeRow(dict(zip(receiptColumns, row))) for row in receiptRows]

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
