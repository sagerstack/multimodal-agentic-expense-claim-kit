"""Analytics router — KPI aggregations and trend data for reviewers."""

import logging

from fastapi import APIRouter
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import RedirectResponse

from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


async def _queryAnalytics() -> dict:
    """Run all KPI and trend aggregations in a single async session."""
    async with getAsyncSession() as session:
        # KPI summary: total claims, total amount, approval rate
        kpiResult = await session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total_claims,
                    COALESCE(SUM(total_amount), 0) AS total_amount,
                    COUNT(*) FILTER (WHERE status NOT IN ('draft')) AS processed_claims,
                    COUNT(*) FILTER (
                        WHERE status IN ('ai_approved', 'manually_approved')
                    ) AS approved_claims,
                    AVG(
                        EXTRACT(EPOCH FROM (updated_at - created_at)) / 3600
                    ) FILTER (WHERE status NOT IN ('draft')) AS avg_processing_hours
                FROM claims
                """
            )
        )
        kpiRow = kpiResult.mappings().first()

        # Claims by status
        statusResult = await session.execute(
            text(
                """
                SELECT status, COUNT(*) AS cnt
                FROM claims
                GROUP BY status
                ORDER BY cnt DESC
                """
            )
        )
        statusRows = statusResult.all()

        # Claims by category
        categoryResult = await session.execute(
            text(
                """
                SELECT COALESCE(category, 'General') AS category, COUNT(*) AS cnt
                FROM claims
                GROUP BY category
                ORDER BY cnt DESC
                """
            )
        )
        categoryRows = categoryResult.all()

        # Top 5 employees by claim count with approval rate
        topEmployeesResult = await session.execute(
            text(
                """
                SELECT
                    c.employee_id,
                    COALESCE(u.display_name, c.employee_id) AS display_name,
                    COUNT(*) AS total_claims,
                    COALESCE(SUM(c.total_amount), 0) AS total_amount,
                    COUNT(*) FILTER (
                        WHERE c.status IN ('ai_approved', 'manually_approved')
                    ) AS approved_claims
                FROM claims c
                LEFT JOIN users u ON u.employee_id = c.employee_id
                GROUP BY c.employee_id, u.display_name
                ORDER BY total_claims DESC
                LIMIT 5
                """
            )
        )
        topEmployeesRows = topEmployeesResult.all()

        # Daily trend: past 5 days, including zero-count days
        dailyResult = await session.execute(
            text(
                """
                SELECT
                    TO_CHAR(day::date, 'Dy DD') AS day_label,
                    day::date AS day_date,
                    COUNT(c.id) AS cnt
                FROM generate_series(
                    CURRENT_DATE - INTERVAL '4 days',
                    CURRENT_DATE,
                    INTERVAL '1 day'
                ) AS day
                LEFT JOIN claims c ON c.created_at::date = day::date
                GROUP BY day::date
                ORDER BY day::date ASC
                """
            )
        )
        dailyRows = dailyResult.all()

    totalClaims = int(kpiRow["total_claims"]) if kpiRow else 0
    totalAmount = float(kpiRow["total_amount"]) if kpiRow else 0.0
    processedClaims = int(kpiRow["processed_claims"]) if kpiRow else 0
    approvedClaims = int(kpiRow["approved_claims"]) if kpiRow else 0
    avgProcessingHours = (
        float(kpiRow["avg_processing_hours"]) if kpiRow and kpiRow["avg_processing_hours"] else 0.0
    )
    approvalRate = (
        round((approvedClaims / processedClaims) * 100, 1) if processedClaims > 0 else 0.0
    )

    # Format avg processing time
    if avgProcessingHours < 1:
        avgProcessingTime = f"{int(avgProcessingHours * 60)}m"
    elif avgProcessingHours < 24:
        avgProcessingTime = f"{avgProcessingHours:.1f}h"
    else:
        avgProcessingTime = f"{avgProcessingHours / 24:.1f}d"

    statusBreakdown = [{"status": row[0], "count": int(row[1])} for row in statusRows]

    categoryBreakdown = [{"category": row[0], "count": int(row[1])} for row in categoryRows]

    topEmployees = []
    for row in topEmployeesRows:
        employeeTotal = int(row[2])
        employeeApproved = int(row[4])
        empApprovalRate = (
            round((employeeApproved / employeeTotal) * 100, 1) if employeeTotal > 0 else 0.0
        )
        topEmployees.append(
            {
                "employeeId": row[0],
                "displayName": row[1],
                "totalClaims": employeeTotal,
                "totalAmount": float(row[3]),
                "approvalRate": empApprovalRate,
            }
        )

    dailyTrend = [{"label": row[0], "count": int(row[2])} for row in dailyRows]
    maxDailyCount = max((d["count"] for d in dailyTrend), default=1)

    return {
        "totalClaims": totalClaims,
        "totalAmount": totalAmount,
        "avgProcessingTime": avgProcessingTime,
        "approvalRate": approvalRate,
        "statusBreakdown": statusBreakdown,
        "categoryBreakdown": categoryBreakdown,
        "topEmployees": topEmployees,
        "dailyTrend": dailyTrend,
        "maxDailyCount": maxDailyCount,
    }


@router.get("/analytics")
async def analyticsPage(request: Request):
    """Render the Analytics page with KPI cards and trend visualizations. Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)

    try:
        analytics = await _queryAnalytics()
    except Exception:
        logger.exception("Analytics DB query failed — rendering with empty data")
        analytics = {
            "totalClaims": 0,
            "totalAmount": 0.0,
            "avgProcessingTime": "—",
            "approvalRate": 0.0,
            "statusBreakdown": [],
            "categoryBreakdown": [],
            "topEmployees": [],
            "dailyTrend": [],
            "maxDailyCount": 1,
        }

    return templates.TemplateResponse(
        request,
        "analytics.html",
        context={
            "activePage": "analytics",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            **analytics,
        },
    )
