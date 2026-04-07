"""Dashboard router — page handler and API endpoints for the Approver Dashboard."""

import logging

from fastapi import APIRouter
from sqlalchemy import func, select, text
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from agentic_claims.infrastructure.database.models import Claim, User
from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

_DRAFT_STATUSES = {"draft"}
_PENDING_STATUSES = {"pending"}
_AI_REVIEWED_STATUSES = {"ai_reviewed"}
_APPROVED_STATUSES = {"ai_approved", "manually_approved"}
_ESCALATED_STATUSES = {"escalated"}
_REJECTED_STATUSES = {"ai_rejected", "manually_rejected"}


async def _queryKpis() -> dict:
    """Query KPI counts from claims table with status breakdown."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(Claim.status, func.count(Claim.id).label("cnt")).group_by(Claim.status)
        )
        rows = result.all()

    draft = 0
    pending = 0
    aiReviewed = 0
    autoApproved = 0
    escalated = 0
    rejected = 0
    for status, cnt in rows:
        if status in _DRAFT_STATUSES:
            draft += cnt
        elif status in _PENDING_STATUSES:
            pending += cnt
        elif status in _AI_REVIEWED_STATUSES:
            aiReviewed += cnt
        elif status in _APPROVED_STATUSES:
            autoApproved += cnt
        elif status in _ESCALATED_STATUSES:
            escalated += cnt
        elif status in _REJECTED_STATUSES:
            rejected += cnt

    return {
        "draft": draft,
        "pending": pending,
        "aiReviewed": aiReviewed,
        "autoApproved": autoApproved,
        "escalated": escalated,
        "rejected": rejected,
    }


async def _queryClaims() -> list[dict]:
    """Query claims list with employee display name."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(
                Claim.id,
                Claim.claimNumber,
                Claim.employeeId,
                Claim.status,
                Claim.totalAmount,
                Claim.currency,
                Claim.createdAt,
                User.displayName,
            )
            .outerjoin(User, User.employeeId == Claim.employeeId)
            .order_by(Claim.createdAt.desc())
        )
        rows = result.all()

    claims = []
    for row in rows:
        (
            claimId,
            claimNumber,
            employeeId,
            status,
            totalAmount,
            currency,
            createdAt,
            displayName,
        ) = row
        employeeName = f"{displayName} ({employeeId})" if displayName else employeeId
        claims.append(
            {
                "id": claimId,
                "claimNumber": claimNumber,
                "employeeId": employeeId,
                "employeeName": employeeName,
                "category": "General",
                "totalAmount": float(totalAmount) if totalAmount else 0.0,
                "currency": currency or "SGD",
                "status": status,
                "createdAt": createdAt.isoformat() if createdAt else None,
            }
        )

    return claims


async def _queryEfficiency() -> dict:
    """Calculate hourly auto-approval rates for the last 24 hours."""
    async with getAsyncSession() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC') AS hour,
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status IN ('ai_approved', 'manually_approved')) AS approved
                FROM claims
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY hour
                ORDER BY hour
                """
            )
        )
        rows = result.all()

    hourlyRates = []
    for row in rows:
        hour, total, approved = int(row[0]), int(row[1]), int(row[2])
        rate = round((approved / total) * 100, 1) if total > 0 else 0.0
        hourlyRates.append({"hour": f"{hour:02d}:00", "rate": rate})

    return {"hourlyRates": hourlyRates}


@router.get("/dashboard")
async def dashboardPage(request: Request):
    """Render the Approver Dashboard page with server-side KPI and claims data."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)

    try:
        kpis = await _queryKpis()
        claims = await _queryClaims()
    except Exception:
        logger.exception("Dashboard DB query failed — rendering with empty data")
        kpis = {"draft": 0, "pending": 0, "aiReviewed": 0, "autoApproved": 0, "escalated": 0, "rejected": 0}
        claims = []

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={
            "activePage": "dashboard",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            "kpis": kpis,
            "claims": claims,
        },
    )


@router.get("/api/dashboard/kpis")
async def dashboardKpisApi(request: Request):
    """Return KPI counts: pending, autoApproved, escalated."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    kpis = await _queryKpis()
    return JSONResponse(kpis)


@router.get("/api/dashboard/claims")
async def dashboardClaimsApi(request: Request):
    """Return claims list for the dashboard table."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    claims = await _queryClaims()
    return JSONResponse(claims)


@router.get("/api/dashboard/efficiency")
async def dashboardEfficiencyApi(request: Request):
    """Return hourly auto-approval rate data for the AI Efficiency chart."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    efficiency = await _queryEfficiency()
    return JSONResponse(efficiency)
