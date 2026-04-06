"""Audit router — page handler and API endpoints for the Audit & Transparency Log."""

import json
import logging

from fastapi import APIRouter
from sqlalchemy import func, select, text
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from agentic_claims.infrastructure.database.models import AuditLog, Claim, Receipt
from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

# Map DB audit_log action -> timeline step name
_ACTION_TO_STEP = {
    "receipt_uploaded": "Receipt Uploaded",
    "ai_extraction": "AI Extraction",
    "policy_check": "Policy Check",
    "claim_submitted": "Claim Submitted",
    "compliance_check": "Compliance Check",
    "fraud_check": "Fraud Check",
    "advisor_decision": "Advisor Decision",
    # Backwards compat: old claims that have these actions map to Final Decision
    "claim_approved": "Final Decision",
    "claim_rejected": "Final Decision",
    "status_change": "Final Decision",
}

_TIMELINE_ORDER = [
    "Receipt Uploaded",
    "AI Extraction",
    "Policy Check",
    "Claim Submitted",
    "Compliance Check",
    "Fraud Check",
    "Advisor Decision",
]

_STEP_ICONS = {
    "Receipt Uploaded": "cloud_upload",
    "AI Extraction": "troubleshoot",
    "Policy Check": "rule",
    "Claim Submitted": "send",
    "Compliance Check": "policy",
    "Fraud Check": "shield",
    "Advisor Decision": "gavel",
    "Final Decision": "verified",
}

# Agent-specific colors per step (Tailwind color name used in template)
_STEP_COLORS = {
    "Receipt Uploaded": "blue",
    "AI Extraction": "blue",
    "Policy Check": "blue",
    "Claim Submitted": "blue",
    "Compliance Check": "green",  # overridden to red in _buildTimelineSteps when verdict=fail
    "Fraud Check": "orange",
    "Advisor Decision": "purple",
    "Final Decision": "blue",
}

# Steps that run in parallel (same superstep)
_PARALLEL_STEPS = {"Compliance Check", "Fraud Check"}


def _buildTimelineSteps(auditRows: list) -> list[dict]:
    """Map audit_log rows to 7 ordered timeline steps with agent-specific colors."""
    stepMap: dict[str, dict] = {}
    # Track the action for each step (needed for Final Decision outcome label)
    stepAction: dict[str, str] = {}

    for row in auditRows:
        action = row.action
        stepName = _ACTION_TO_STEP.get(action)
        if stepName is None:
            continue
        if stepName in stepMap:
            continue  # keep first occurrence

        details = {}
        try:
            details = json.loads(row.newValue) if row.newValue else {}
        except Exception:
            pass

        color = _STEP_COLORS.get(stepName, "blue")

        stepData: dict = {
            "name": stepName,
            "icon": _STEP_ICONS.get(stepName, "circle"),
            "status": "completed",
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "details": details,
            "color": color,
            "parallel": stepName in _PARALLEL_STEPS,
        }

        if stepName == "AI Extraction":
            conf = details.get("confidence") or details.get("vlm_confidence")
            stepData["confidence"] = float(conf) if conf is not None else None
            extracted = details.get("extracted") or {}
            stepData["merchant"] = extracted.get("merchant") or details.get("merchant")
            stepData["amount"] = extracted.get("total_amount") or details.get("total_amount")

        elif stepName == "Policy Check":
            policyRefs = details.get("policyRefs") or []
            stepData["compliant"] = details.get("compliant", True)
            stepData["policyRef"] = policyRefs[0].get("section") if policyRefs else None
            violations = details.get("violations") or []
            stepData["violations"] = violations

        elif stepName == "Final Decision":
            stepData["outcome"] = action.replace("claim_", "").replace("_", " ").title()
            stepData["rejectionReason"] = details.get("rejectionReason")
            stepData["reviewerNotes"] = details.get("reviewerNotes")

        elif stepName == "Compliance Check":
            verdict = details.get("verdict", "")
            # Override color: red for fail, green for pass
            stepData["color"] = "red" if verdict == "fail" else "green"
            stepData["complianceVerdict"] = verdict
            violations = details.get("violations") or []
            stepData["violationCount"] = len(violations)
            stepData["citedClauses"] = details.get("citedClauses") or []
            stepData["complianceSummary"] = details.get("summary") or ""

        elif stepName == "Fraud Check":
            stepData["fraudVerdict"] = details.get("verdict", "")
            flags = details.get("flags") or []
            stepData["flagCount"] = len(flags)
            stepData["duplicateClaims"] = details.get("duplicateClaims") or []
            stepData["fraudSummary"] = details.get("summary") or ""

        elif stepName == "Advisor Decision":
            stepData["advisorDecision"] = details.get("decision") or details.get("verdict") or ""
            stepData["advisorReasoning"] = details.get("reasoning") or ""
            stepData["complianceSummary"] = details.get("complianceSummary") or ""
            stepData["fraudSummary"] = details.get("fraudSummary") or ""

        stepMap[stepName] = stepData
        stepAction[stepName] = action

    # Build ordered list, filling missing steps as pending
    steps = []
    for name in _TIMELINE_ORDER:
        if name in stepMap:
            steps.append(stepMap[name])
        else:
            steps.append(
                {
                    "name": name,
                    "icon": _STEP_ICONS.get(name, "circle"),
                    "status": "pending",
                    "timestamp": None,
                    "details": {},
                    "color": _STEP_COLORS.get(name, "blue"),
                    "parallel": name in _PARALLEL_STEPS,
                }
            )
    return steps


async def _fetchTimeline(claimId: int) -> list[dict]:
    """Fetch audit_log entries and build 7-step timeline."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.claimId == claimId).order_by(AuditLog.timestamp.asc())
        )
        rows = result.scalars().all()
    return _buildTimelineSteps(list(rows))


async def _fetchInsights(claimId: int) -> dict:
    """Fetch anomaly count and cost benchmark for a claim."""
    async with getAsyncSession() as session:
        # Get claim with intake_findings via raw SQL
        claimResult = await session.execute(
            text("SELECT total_amount, currency, intake_findings FROM claims WHERE id = :cid"),
            {"cid": claimId},
        )
        claimRow = claimResult.mappings().first()

    if claimRow is None:
        return {"anomalyCount": 0, "costBenchmark": None}

    # Parse anomaly count from intake_findings
    findings = claimRow.get("intake_findings") or {}
    if isinstance(findings, str):
        try:
            findings = json.loads(findings)
        except Exception:
            findings = {}
    violations = findings.get("violations") or []
    anomalyCount = len(violations)

    # Cost benchmark: average total_amount across all claims
    async with getAsyncSession() as session:
        avgResult = await session.execute(select(func.avg(Claim.totalAmount).label("avg")))
        avgRow = avgResult.first()

    categoryAverage = float(avgRow.avg) if avgRow and avgRow.avg else 0.0
    totalAmountRaw = claimRow.get("total_amount")
    claimAmount = float(totalAmountRaw) if totalAmountRaw else 0.0

    return {
        "anomalyCount": anomalyCount,
        "costBenchmark": {
            "claimAmount": claimAmount,
            "categoryAverage": round(categoryAverage, 2),
            "category": "All",
        },
    }


async def _fetchAllClaims() -> list[dict]:
    """Fetch all claims for left panel list, DESC order."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(
                Claim.id,
                Claim.claimNumber,
                Claim.status,
                Claim.totalAmount,
                Claim.currency,
                Claim.createdAt,
            ).order_by(Claim.createdAt.desc())
        )
        rows = result.all()

    return [
        {
            "id": row.id,
            "claimNumber": row.claimNumber,
            "status": row.status,
            "totalAmount": float(row.totalAmount) if row.totalAmount else 0.0,
            "currency": row.currency or "SGD",
            "createdAt": row.createdAt.isoformat() if row.createdAt else None,
        }
        for row in rows
    ]


async def _fetchClaimSummary(claimId: int) -> dict | None:
    """Fetch a single claim's summary for the right panel header."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(
                Claim.id,
                Claim.claimNumber,
                Claim.status,
                Claim.totalAmount,
                Claim.currency,
                Receipt.merchant,
            )
            .outerjoin(Receipt, Receipt.claimId == Claim.id)
            .where(Claim.id == claimId)
            .limit(1)
        )
        row = result.first()

    if row is None:
        return None
    return {
        "id": row.id,
        "claimNumber": row.claimNumber,
        "status": row.status,
        "totalAmount": float(row.totalAmount) if row.totalAmount else 0.0,
        "currency": row.currency or "SGD",
        "merchant": row.merchant or "Expense Claim",
    }


@router.get("/audit/{claimId}")
async def auditPage(request: Request, claimId: str):
    """Render the Audit & Transparency Log page. Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)

    # Try to resolve claimId to an int for DB queries; fall back gracefully
    claimIdInt: int | None = None
    try:
        claimIdInt = int(claimId)
    except (ValueError, TypeError):
        pass

    timelineSteps: list = []
    insights: dict = {"anomalyCount": 0, "costBenchmark": None}
    claim: dict | None = None

    try:
        allClaims = await _fetchAllClaims()
        if claimIdInt is not None:
            timelineSteps = await _fetchTimeline(claimIdInt)
            insights = await _fetchInsights(claimIdInt)
            claim = await _fetchClaimSummary(claimIdInt)
    except Exception:
        logger.exception("Audit DB query failed — rendering with empty data")
        allClaims = []

    return templates.TemplateResponse(
        request,
        "audit.html",
        context={
            "activePage": "audit",
            "claimId": claimId,
            "threadId": sessionIds["threadId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            "claim": claim,
            "timelineSteps": timelineSteps,
            "insights": insights,
            "allClaims": allClaims,
            "selectedClaimId": claimIdInt,
        },
    )


@router.get("/api/audit/{claimId}/timeline")
async def auditTimelineApi(request: Request, claimId: int):
    """Return 7-step timeline HTML partial for a claim's audit_log entries."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    steps = await _fetchTimeline(claimId)
    claim = await _fetchClaimSummary(claimId)
    insights = await _fetchInsights(claimId)
    return templates.TemplateResponse(
        request,
        "partials/audit_timeline.html",
        context={
            "timelineSteps": steps,
            "claim": claim,
            "insights": insights,
            "claimId": claimId,
        },
    )


@router.get("/api/audit/{claimId}/insights")
async def auditInsightsApi(request: Request, claimId: int):
    """Return anomaly count and cost benchmark JSON for a claim."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    insights = await _fetchInsights(claimId)
    return JSONResponse(insights)


@router.get("/api/audit/claims")
async def auditClaimsApi(request: Request):
    """Return all claims list for the audit left panel."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    claims = await _fetchAllClaims()
    return JSONResponse(claims)


@router.get("/api/audit/{claimId}/receipt")
async def auditReceiptApi(request: Request, claimId: int):
    """Redirect to the receipt image for a claim."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    async with getAsyncSession() as session:
        result = await session.execute(
            select(Receipt.imagePath).where(Receipt.claimId == claimId).limit(1)
        )
        imagePath = result.scalar_one_or_none()

    if not imagePath:
        return JSONResponse({"error": "No receipt image found"}, status_code=404)

    if not imagePath.startswith("/"):
        return RedirectResponse(f"/static/{imagePath}", status_code=302)
    return RedirectResponse(imagePath, status_code=302)
