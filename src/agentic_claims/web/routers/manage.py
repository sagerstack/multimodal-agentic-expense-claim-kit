"""Manage Claims router — filterable claims table with bulk approve/reject for reviewers."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form
from sqlalchemy import select, text, update
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from agentic_claims.infrastructure.database.models import AuditLog, Claim, User
from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_STATUSES = {
    "draft",
    "pending",
    "ai_reviewed",
    "ai_approved",
    "ai_rejected",
    "escalated",
    "manually_approved",
    "manually_rejected",
}

_VALID_CATEGORIES = {
    "Meals",
    "Transport",
    "Accommodation",
    "Office Supplies",
    "General",
}


async def _queryClaims(
    statusFilter: str | None = None,
    categoryFilter: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
) -> list[dict]:
    """Query claims with optional filters, joined with users for display name."""
    conditions = ["c.status != 'draft'"]
    params: dict = {}

    if statusFilter and statusFilter in _VALID_STATUSES and statusFilter != "draft":
        conditions.append("c.status = :status")
        params["status"] = statusFilter

    if categoryFilter and categoryFilter in _VALID_CATEGORIES:
        conditions.append("c.category = :category")
        params["category"] = categoryFilter

    if dateFrom:
        conditions.append("c.created_at >= :dateFrom")
        params["dateFrom"] = dateFrom

    if dateTo:
        conditions.append("c.created_at <= :dateTo")
        params["dateTo"] = dateTo + " 23:59:59"

    whereClause = " AND ".join(conditions)

    query = text(
        f"""
        SELECT
            c.id,
            c.claim_number,
            c.employee_id,
            c.status,
            c.total_amount,
            c.currency,
            c.category,
            c.created_at,
            u.display_name
        FROM claims c
        LEFT JOIN users u ON u.employee_id = c.employee_id
        WHERE {whereClause}
        ORDER BY c.created_at DESC
        """
    )

    async with getAsyncSession() as session:
        result = await session.execute(query, params)
        rows = result.mappings().all()

    claims = []
    for row in rows:
        employeeName = row.get("display_name") or row["employee_id"]
        claims.append(
            {
                "id": row["id"],
                "claimNumber": row["claim_number"],
                "employeeId": row["employee_id"],
                "employeeName": employeeName,
                "status": row["status"],
                "totalAmount": float(row["total_amount"]) if row["total_amount"] else 0.0,
                "currency": row["currency"] or "SGD",
                "category": row.get("category") or "General",
                "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
            }
        )

    return claims


@router.get("/manage")
async def managePage(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
):
    """Render the Manage Claims page. Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)

    try:
        claims = await _queryClaims(
            statusFilter=status,
            categoryFilter=category,
            dateFrom=dateFrom,
            dateTo=dateTo,
        )
    except Exception:
        logger.exception("Manage Claims DB query failed — rendering with empty data")
        claims = []

    return templates.TemplateResponse(
        request,
        "manage.html",
        context={
            "activePage": "manage",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            "claims": claims,
            "filterStatus": status or "",
            "filterCategory": category or "",
            "filterDateFrom": dateFrom or "",
            "filterDateTo": dateTo or "",
        },
    )


@router.post("/api/manage/bulk-action")
async def manageBulkAction(
    request: Request,
    action: str = Form(...),
    claimIds: str = Form(...),
):
    """Bulk approve or reject selected claims. Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        response = Response(status_code=403)
        return response

    if action not in {"approve", "reject"}:
        response = Response(status_code=422)
        return response

    try:
        ids = [int(i.strip()) for i in claimIds.split(",") if i.strip()]
    except ValueError:
        response = Response(status_code=422)
        return response

    if not ids:
        response = Response(status_code=204)
        response.headers["HX-Redirect"] = "/manage"
        return response

    newStatus = "manually_approved" if action == "approve" else "manually_rejected"
    auditAction = "claim_approved" if action == "approve" else "claim_rejected"
    actor = currentUser["displayName"] or currentUser["username"]
    reviewerEmployeeId = currentUser["employeeId"]
    nowUtc = datetime.now(timezone.utc)
    newValue = json.dumps({"action": action, "bulk": True})

    async with getAsyncSession() as session:
        updateStmt = (
            update(Claim)
            .where(Claim.id.in_(ids))
            .values(
                status=newStatus,
                approvedBy=reviewerEmployeeId,
                **({"approvalDate": nowUtc} if action == "approve" else {}),
            )
        )
        await session.execute(updateStmt)

        for claimId in ids:
            auditEntry = AuditLog(
                claimId=claimId,
                action=auditAction,
                newValue=newValue,
                actor=actor,
            )
            session.add(auditEntry)

        await session.commit()

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/manage"
    return response
