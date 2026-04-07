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
    "compliance_check": "Compliance Agent",
    "fraud_check": "Fraud Checking Agent",
    "advisor_decision": "Advisory Agent",
    # Start entries — agent has begun processing
    "compliance_check_start": "Compliance Agent",
    "fraud_check_start": "Fraud Checking Agent",
    "advisor_decision_start": "Advisory Agent",
    # Human reviewer actions
    "claim_approved": "Reviewer Decision",
    "claim_rejected": "Reviewer Decision",
}

# Actions that represent an agent starting (not completing)
_START_ACTIONS = {"compliance_check_start", "fraud_check_start", "advisor_decision_start"}

_TIMELINE_ORDER = [
    "Receipt Uploaded",
    "AI Extraction",
    "Policy Check",
    "Claim Submitted",
    "Compliance Agent",
    "Fraud Checking Agent",
    "Advisory Agent",
    "Reviewer Decision",
]

_STEP_ICONS = {
    "Receipt Uploaded": "cloud_upload",
    "AI Extraction": "troubleshoot",
    "Policy Check": "rule",
    "Claim Submitted": "send",
    "Compliance Agent": "policy",
    "Fraud Checking Agent": "shield",
    "Advisory Agent": "gavel",
    "Reviewer Decision": "person_check",
}

# Agent-specific colors per step (Tailwind color name used in template)
_STEP_COLORS = {
    "Receipt Uploaded": "blue",
    "AI Extraction": "blue",
    "Policy Check": "blue",
    "Claim Submitted": "blue",
    "Compliance Agent": "green",  # overridden to red in _buildTimelineSteps when verdict=fail
    "Fraud Checking Agent": "green",  # overridden by verdict in _buildTimelineSteps
    "Advisory Agent": "green",  # overridden to red in _buildTimelineSteps for non-approve
    "Reviewer Decision": "green",  # overridden by action in _buildTimelineSteps
}


def _buildTimelineSteps(auditRows: list) -> list[dict]:
    """Map audit_log rows to 8 ordered timeline steps with agent-specific colors.

    Supports three statuses: completed, processing (start entry only), pending (no entry).
    A completion entry always overrides a start entry for the same step.
    """
    stepMap: dict[str, dict] = {}
    # Track the action for each step (needed for Final Decision outcome label)
    stepAction: dict[str, str] = {}

    for row in auditRows:
        action = row.action
        stepName = _ACTION_TO_STEP.get(action)
        if stepName is None:
            continue

        isStartAction = action in _START_ACTIONS

        # If step already has a completed entry, skip start entries
        if stepName in stepMap and stepMap[stepName]["status"] == "completed":
            continue
        # If step has a start entry and this is also a start entry, skip
        if stepName in stepMap and isStartAction:
            continue

        details = {}
        try:
            details = json.loads(row.newValue) if row.newValue else {}
        except Exception:
            pass

        color = _STEP_COLORS.get(stepName, "blue")
        status = "processing" if isStartAction else "completed"

        stepData: dict = {
            "name": stepName,
            "icon": _STEP_ICONS.get(stepName, "circle"),
            "status": status,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
            "details": details,
            "color": color,
            "parallel": False,
        }

        if stepName == "AI Extraction":
            conf = details.get("confidence") or details.get("vlm_confidence")
            if isinstance(conf, dict):
                conf = conf.get("score") or conf.get("value") or conf.get("confidence")
            try:
                stepData["confidence"] = float(conf) if conf is not None else None
            except (TypeError, ValueError):
                stepData["confidence"] = None
            extracted = details.get("extracted") or {}
            stepData["merchant"] = extracted.get("merchant") or details.get("merchant")
            stepData["amount"] = extracted.get("total_amount") or details.get("total_amount")

        elif stepName == "Policy Check":
            policyRefs = details.get("policyRefs") or []
            stepData["compliant"] = details.get("compliant", True)
            stepData["policyRef"] = policyRefs[0].get("section") if policyRefs else None
            violations = details.get("violations") or []
            stepData["violations"] = violations

        elif stepName == "Reviewer Decision":
            outcome = action.replace("claim_", "").replace("_", " ").title()
            stepData["outcome"] = outcome
            stepData["reviewerAction"] = details.get("action", "")
            stepData["rejectionReason"] = details.get("rejectionReason")
            stepData["reviewerNotes"] = details.get("reviewerNotes")
            # Color: green for approved, red for rejected
            if "approved" in action:
                stepData["color"] = "green"
            elif "rejected" in action:
                stepData["color"] = "red"

        elif stepName == "Compliance Agent":
            verdict = details.get("verdict", "")
            # Override color: red for fail, green for pass
            stepData["color"] = "red" if verdict == "fail" else "green"
            stepData["complianceVerdict"] = verdict
            violations = details.get("violations") or []
            stepData["violationCount"] = len(violations)
            stepData["citedClauses"] = details.get("citedClauses") or []
            stepData["complianceSummary"] = details.get("summary") or ""

        elif stepName == "Fraud Checking Agent":
            verdict = details.get("verdict", "")
            stepData["fraudVerdict"] = verdict
            # Color: red for duplicate/suspicious, green for legit
            if verdict in ("duplicate", "suspicious"):
                stepData["color"] = "red"
            else:
                stepData["color"] = "green"
            flags = details.get("flags") or []
            stepData["flagCount"] = len(flags)
            stepData["duplicateClaims"] = details.get("duplicateClaims") or []
            stepData["fraudSummary"] = details.get("summary") or ""

        elif stepName == "Advisory Agent":
            decision = details.get("decision") or details.get("verdict") or ""
            stepData["advisorDecision"] = decision
            # Color: green for approve, red for reject, pink for escalate
            if decision == "auto_approve":
                stepData["color"] = "green"
            else:
                stepData["color"] = "red"
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
                    "parallel": False,
                }
            )
    return steps


async def _fetchTimeline(claimId: int) -> list[dict]:
    """Fetch audit_log entries and build 8-step timeline."""
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


async def _fetchAllClaims(employeeId: str | None = None) -> list[dict]:
    """Fetch claims for left panel list, DESC order. Optionally filter by employee_id."""
    async with getAsyncSession() as session:
        query = select(
            Claim.id,
            Claim.claimNumber,
            Claim.status,
            Claim.totalAmount,
            Claim.currency,
            Claim.createdAt,
        )
        if employeeId:
            query = query.where(Claim.employeeId == employeeId)
        result = await session.execute(query.order_by(Claim.createdAt.desc()))
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
    """Render the Audit & Transparency Log page. Reviewers see all claims; users see their own."""
    currentUser = getCurrentUser(request)

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

    # Reviewers see all claims; users see only their own
    employeeFilter = None if currentUser["role"] == "reviewer" else currentUser.get("employeeId")
    try:
        allClaims = await _fetchAllClaims(employeeId=employeeFilter)
    except Exception:
        logger.exception("Audit DB query failed fetching claims list")
        allClaims = []

    try:
        if claimIdInt is not None:
            timelineSteps = await _fetchTimeline(claimIdInt)
            insights = await _fetchInsights(claimIdInt)
            claim = await _fetchClaimSummary(claimIdInt)
    except Exception:
        logger.exception("Audit DB query failed for claim %s", claimId)

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
    """Return 8-step timeline HTML partial for a claim's audit_log entries."""
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
