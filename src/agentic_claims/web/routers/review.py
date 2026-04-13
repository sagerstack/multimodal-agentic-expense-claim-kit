"""Review router — page handler and API endpoints for the Claim Review page."""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Form
from sqlalchemy import func, select, text, update
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from agentic_claims.infrastructure.database.models import AuditLog, Claim, Receipt, User
from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

_REJECTION_REASONS = {
    "Duplicate submission",
    "Incomplete receipt details",
    "Policy violation",
}


async def _fetchAgentFindingsFromAuditLog(claimId: int) -> dict:
    """Fallback: reconstruct agent findings from audit_log when claims columns are NULL.

    Some claims were processed before the advisor agent began writing compliance_findings
    and fraud_findings directly to the claims table. For those claims, the audit_log
    contains the agent output as JSON in new_value.
    """
    findings: dict = {}
    async with getAsyncSession() as session:
        result = await session.execute(
            select(AuditLog.action, AuditLog.newValue)
            .where(
                AuditLog.claimId == claimId,
                AuditLog.action.in_(["compliance_check", "fraud_check", "advisor_decision"]),
            )
            .order_by(AuditLog.timestamp.asc())
        )
        rows = result.all()

    for action, newValue in rows:
        try:
            data = json.loads(newValue) if newValue else {}
        except Exception:
            data = {}
        if action == "compliance_check" and data:
            findings["compliance_findings"] = data
        elif action == "fraud_check" and data:
            findings["fraud_findings"] = data
        elif action == "advisor_decision" and data:
            findings["advisor_decision"] = data.get("decision")
            findings["advisor_findings"] = data

    return findings


async def _fetchClaimDetail(claimId: int) -> dict | None:
    """Fetch claim with receipt and intake_findings via raw SQL.

    ORM model lacks intake_findings column, so raw SQL is required.
    Falls back to audit_log when compliance_findings / fraud_findings are NULL
    (pre-fix claims processed before the advisor wrote to the claims table).
    """
    async with getAsyncSession() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    c.id, c.claim_number, c.employee_id, c.status,
                    c.total_amount, c.currency, c.created_at, c.category,
                    c.intake_findings, c.compliance_findings, c.fraud_findings,
                    c.advisor_decision, c.advisor_findings, c.approved_by,
                    r.id AS receipt_id, r.receipt_number, r.merchant, r.date, r.total_amount AS receipt_amount,
                    r.currency AS receipt_currency, r.image_path,
                    r.line_items, r.original_currency, r.original_amount, r.converted_amount_sgd,
                    u.display_name
                FROM claims c
                LEFT JOIN receipts r ON r.claim_id = c.id
                LEFT JOIN users u ON u.employee_id = c.employee_id
                WHERE c.id = :claimId
                ORDER BY r.id ASC
                LIMIT 1
                """
            ),
            {"claimId": claimId},
        )
        row = result.mappings().first()

    if row is None:
        return None

    rowDict = dict(row)

    # If the advisor never wrote findings to the claims table, reconstruct from audit_log
    needsFallback = (
        rowDict.get("compliance_findings") is None
        or rowDict.get("fraud_findings") is None
        or rowDict.get("advisor_findings") is None
    )
    if needsFallback:
        fallback = await _fetchAgentFindingsFromAuditLog(claimId)
        if fallback.get("compliance_findings") and rowDict.get("compliance_findings") is None:
            rowDict["compliance_findings"] = fallback["compliance_findings"]
        if fallback.get("fraud_findings") and rowDict.get("fraud_findings") is None:
            rowDict["fraud_findings"] = fallback["fraud_findings"]
        if fallback.get("advisor_decision") and rowDict.get("advisor_decision") is None:
            rowDict["advisor_decision"] = fallback["advisor_decision"]
        if fallback.get("advisor_findings") and rowDict.get("advisor_findings") is None:
            rowDict["advisor_findings"] = fallback["advisor_findings"]

    return rowDict


async def _fetchSubmissionHistory(employeeId: str) -> dict | None:
    """Query employee submission history for the Submission History card."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(
                func.count(Claim.id).label("total"),
                func.count(Claim.id).filter(Claim.status.in_(["ai_approved", "manually_approved"])).label("approved"),
                User.displayName,
            )
            .outerjoin(User, User.employeeId == Claim.employeeId)
            .where(Claim.employeeId == employeeId)
            .group_by(User.displayName)
        )
        row = result.first()

    if row is None or row.total == 0:
        return None

    approvalRate = round((row.approved / row.total) * 100, 1) if row.total > 0 else 0.0
    return {
        "submissionCount": row.total,
        "approvalRate": approvalRate,
        "employeeName": row.displayName or employeeId,
    }


def _parseFlagReason(intakeFindings: dict | None) -> dict | None:
    """Extract flag reason from intake_findings JSONB."""
    if not intakeFindings:
        return None
    violations = intakeFindings.get("violations") or []
    explanation = intakeFindings.get("explanation") or intakeFindings.get("flagReason")
    confidence = intakeFindings.get("confidence") or intakeFindings.get("policyCheckConfidence")
    if violations:
        explanation = explanation or violations[0].get("description", "Policy violation detected")
        if not confidence:
            confidence = violations[0].get("score")
    if not explanation:
        return None
    return {
        "explanation": str(explanation),
        "confidence": float(confidence) if confidence is not None else 0.5,
    }


_CONFIDENCE_STRING_MAP = {
    "high": 0.95,
    "medium": 0.75,
    "low": 0.50,
    "very high": 0.99,
    "very low": 0.25,
}


def _normalizeConfidenceValue(v) -> float | None:
    """Convert a confidence value to a float. Handles numeric and string labels."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return _CONFIDENCE_STRING_MAP.get(v.strip().lower())
    return None


def _parseIntakeAgentFindings(intakeFindings: dict | None) -> dict | None:
    """Extract confidence scores from intake_findings and compute summary stats."""
    if not intakeFindings:
        return None
    scores = intakeFindings.get("confidenceScores") or intakeFindings.get("confidence") or intakeFindings.get("confidenceFlags") or {}
    if not scores or not isinstance(scores, dict):
        return None
    # Normalize: convert string labels ("High") to numeric (0.95)
    numericScores = {}
    for k, v in scores.items():
        nv = _normalizeConfidenceValue(v)
        if nv is not None:
            numericScores[k] = nv
    if not numericScores:
        return None
    values = list(numericScores.values())
    avgConfidence = sum(values) / len(values)
    lowestField = min(numericScores, key=lambda k: numericScores[k])
    lowestScore = numericScores[lowestField]
    # Get the extracted value for the lowest confidence field
    extractedFields = intakeFindings.get("extractedFields") or {}
    lowestFieldValue = extractedFields.get(lowestField)
    return {
        "avgConfidence": round(avgConfidence, 3),
        "lowestField": lowestField,
        "lowestScore": round(float(lowestScore), 3),
        "lowestFieldValue": str(lowestFieldValue) if lowestFieldValue is not None else None,
        "scores": numericScores,
    }


def _parseConversationalAudit(intakeFindings: dict | None) -> list[dict]:
    """Extract timeline entries from intake_findings for the Conversational Audit card."""
    if not intakeFindings:
        return []
    entries = []

    # Policy violations
    policyViolation = intakeFindings.get("policyViolation")
    if policyViolation:
        violationTexts = [policyViolation] if isinstance(policyViolation, str) else policyViolation
        for vText in violationTexts:
            entry = {"type": "violation", "icon": "warning", "text": str(vText), "children": []}
            # Attach justification as child of the first violation
            justification = intakeFindings.get("justification")
            if justification and not entries:
                entry["children"].append({"type": "justification", "text": str(justification)})
            entries.append(entry)

    # If justification exists but no violations, add it standalone
    if not entries:
        justification = intakeFindings.get("justification")
        if justification:
            entries.append({"type": "justification", "icon": "edit", "text": str(justification), "children": []})

    # Remarks / soft cap breaches (filter out generic placeholder remarks)
    remarks = intakeFindings.get("remarks")
    if remarks:
        remarkTexts = [remarks] if isinstance(remarks, str) else remarks
        for rText in remarkTexts:
            rStr = str(rText).strip().lower()
            if rStr in ("no expense description provided", "no description provided", "n/a", "none"):
                continue
            entries.append({"type": "remark", "icon": "info", "text": str(rText), "children": []})

    # Field corrections
    corrections = intakeFindings.get("corrections")
    if corrections:
        correctionTexts = [corrections] if isinstance(corrections, str) else corrections
        for cText in correctionTexts:
            entries.append({"type": "correction", "icon": "edit", "text": str(cText), "children": []})

    return entries


def _parseJsonField(value) -> dict | None:
    """Parse a JSONB field that may be a dict, JSON string, or None."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None


def _buildClaimContext(row: dict) -> tuple[dict, dict | None]:
    """Build claim and receipt context dicts from a DB row."""
    claim = {
        "id": row["id"],
        "claimNumber": row["claim_number"],
        "employeeId": row["employee_id"],
        "status": row["status"],
        "totalAmount": float(row["total_amount"]) if row["total_amount"] else 0.0,
        "currency": row["currency"] or "SGD",
        "createdAt": row["created_at"].isoformat() if row["created_at"] else None,
        "employeeName": row.get("display_name") or row["employee_id"],
        "complianceFindings": _parseJsonField(row.get("compliance_findings")),
        "fraudFindings": _parseJsonField(row.get("fraud_findings")),
        "advisorDecision": row.get("advisor_decision"),
        "advisorFindings": _parseJsonField(row.get("advisor_findings")),
        "approvedBy": row.get("approved_by"),
    }
    receipt = None
    if row.get("receipt_id"):
        lineItems = row.get("line_items") or {}
        receipt = {
            "merchant": row.get("merchant") or "Unknown",
            "date": str(row.get("date", "")) if row.get("date") else None,
            "totalAmount": float(row["receipt_amount"]) if row.get("receipt_amount") else 0.0,
            "currency": row.get("receipt_currency") or "SGD",
            "imagePath": row.get("image_path"),
            "lineItems": lineItems,
            "category": row.get("category") or "General",
            "receiptNumber": row.get("receipt_number"),
            "originalCurrency": row.get("original_currency"),
            "originalAmount": (
                float(row["original_amount"]) if row.get("original_amount") else None
            ),
            "convertedAmountSgd": (
                float(row["converted_amount_sgd"]) if row.get("converted_amount_sgd") else None
            ),
        }
    return claim, receipt


@router.get("/review/{claimId}")
async def reviewPage(request: Request, claimId: int):
    """Render the Claim Review page (v2 layout). Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)
    row = await _fetchClaimDetail(claimId)

    if row is None:
        return templates.TemplateResponse(
            request,
            "review_v2.html",
            context={
                "activePage": "review",
                "claimId": claimId,
                "threadId": sessionIds["threadId"],
                "userRole": currentUser["role"],
                "displayName": currentUser["displayName"],
                "employeeId": currentUser["employeeId"],
                "username": currentUser["username"],
                "claim": None,
                "receipt": None,
                "flagReason": None,
                "intakeAgentFindings": None,
                "conversationalAudit": [],
                "submissionHistory": None,
                "showActions": False,
                "complianceFindings": None,
                "fraudFindings": None,
                "advisorDecision": None,
            },
            status_code=404,
        )

    claim, receipt = _buildClaimContext(row)
    intakeFindings = _parseJsonField(row.get("intake_findings")) or {}
    flagReason = _parseFlagReason(intakeFindings)
    intakeAgentFindings = _parseIntakeAgentFindings(intakeFindings)
    conversationalAudit = _parseConversationalAudit(intakeFindings)
    submissionHistory = await _fetchSubmissionHistory(row["employee_id"])
    showActions = claim["status"] == "escalated"

    return templates.TemplateResponse(
        request,
        "review_v2.html",
        context={
            "activePage": "review",
            "claimId": claimId,
            "threadId": sessionIds["threadId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            "claim": claim,
            "receipt": receipt,
            "flagReason": flagReason,
            "intakeAgentFindings": intakeAgentFindings,
            "conversationalAudit": conversationalAudit,
            "submissionHistory": submissionHistory,
            "showActions": showActions,
            "complianceFindings": claim["complianceFindings"],
            "fraudFindings": claim["fraudFindings"],
            "advisorDecision": claim["advisorDecision"],
            "advisorFindings": claim["advisorFindings"],
        },
    )


@router.get("/api/review/{claimId}")
async def reviewDetailApi(request: Request, claimId: int):
    """Return full claim detail JSON for the review page."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    row = await _fetchClaimDetail(claimId)
    if row is None:
        return JSONResponse({"error": "Claim not found"}, status_code=404)

    claim, receipt = _buildClaimContext(row)
    intakeFindings = _parseJsonField(row.get("intake_findings")) or {}
    flagReason = _parseFlagReason(intakeFindings)
    intakeAgentFindings = _parseIntakeAgentFindings(intakeFindings)
    conversationalAudit = _parseConversationalAudit(intakeFindings)
    submissionHistory = await _fetchSubmissionHistory(row["employee_id"])
    showActions = claim["status"] == "escalated"

    return JSONResponse(
        {
            "claim": claim,
            "receipt": receipt,
            "flagReason": flagReason,
            "intakeAgentFindings": intakeAgentFindings,
            "conversationalAudit": conversationalAudit,
            "submissionHistory": submissionHistory,
            "showActions": showActions,
            "complianceFindings": claim["complianceFindings"],
            "fraudFindings": claim["fraudFindings"],
            "advisorDecision": claim["advisorDecision"],
            "advisorFindings": claim["advisorFindings"],
        }
    )


@router.post("/api/review/{claimId}/decision")
async def reviewDecisionApi(
    request: Request,
    claimId: int,
    action: str = Form(...),
    rejectionReason: str = Form(default=""),
    reviewerNotes: str = Form(default=""),
):
    """Process approve or reject decision for a claim."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    if action not in {"approve", "reject"}:
        return JSONResponse({"error": "Invalid action"}, status_code=422)

    if action == "reject" and rejectionReason not in _REJECTION_REASONS:
        return JSONResponse(
            {
                "error": (
                    "rejectionReason required for reject action. "
                    f"Must be one of: {', '.join(_REJECTION_REASONS)}"
                )
            },
            status_code=422,
        )

    newStatus = "manually_approved" if action == "approve" else "manually_rejected"
    auditAction = "claim_approved" if action == "approve" else "claim_rejected"
    newValue = json.dumps(
        {
            "action": action,
            **({"rejectionReason": rejectionReason} if action == "reject" else {}),
            **({"reviewerNotes": reviewerNotes} if reviewerNotes else {}),
        }
    )
    actor = currentUser["displayName"] or currentUser["username"]
    nowUtc = datetime.now(timezone.utc)

    reviewerEmployeeId = currentUser["employeeId"]

    async with getAsyncSession() as session:
        # Update claim status and set approved_by to reviewer's employee ID
        updateStmt = (
            update(Claim)
            .where(Claim.id == claimId)
            .values(
                status=newStatus,
                approvedBy=reviewerEmployeeId,
                **({"approvalDate": nowUtc} if action == "approve" else {}),
            )
        )
        await session.execute(updateStmt)

        # Create audit log entry
        auditEntry = AuditLog(
            claimId=claimId,
            action=auditAction,
            newValue=newValue,
            actor=actor,
        )
        session.add(auditEntry)
        await session.commit()

    # HTMX redirect response
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/manage"
    return response


@router.get("/api/review/{claimId}/receipt-image")
async def receiptImageApi(request: Request, claimId: int):
    """Serve or redirect to the receipt image for a claim."""
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

    # Redirect to static URL if path is relative
    if not imagePath.startswith("/"):
        return RedirectResponse(f"/static/{imagePath}", status_code=302)
    return RedirectResponse(imagePath, status_code=302)
