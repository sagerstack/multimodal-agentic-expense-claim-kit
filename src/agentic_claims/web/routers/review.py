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


async def _fetchClaimDetail(claimId: int) -> dict | None:
    """Fetch claim with receipt and intake_findings via raw SQL.

    ORM model lacks intake_findings column, so raw SQL is required.
    """
    async with getAsyncSession() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    c.id, c.claim_number, c.employee_id, c.status,
                    c.total_amount, c.currency, c.created_at,
                    c.intake_findings,
                    r.id AS receipt_id, r.merchant, r.date, r.total_amount AS receipt_amount,
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

    return dict(row)


async def _fetchAiInsight(employeeId: str) -> dict | None:
    """Query employee submission history for the AI Insight card."""
    async with getAsyncSession() as session:
        result = await session.execute(
            select(
                func.count(Claim.id).label("total"),
                func.count(Claim.id).filter(Claim.status == "approved").label("approved"),
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
    }
    receipt = None
    if row.get("receipt_id"):
        lineItems = row.get("line_items") or {}
        category = "General"
        if isinstance(lineItems, dict):
            category = lineItems.get("category") or "General"
        elif isinstance(lineItems, list) and lineItems:
            category = lineItems[0].get("category") or "General"
        receipt = {
            "merchant": row.get("merchant") or "Unknown",
            "date": str(row.get("date", "")) if row.get("date") else None,
            "totalAmount": float(row["receipt_amount"]) if row.get("receipt_amount") else 0.0,
            "currency": row.get("receipt_currency") or "SGD",
            "imagePath": row.get("image_path"),
            "lineItems": lineItems,
            "category": category,
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
    """Render the Claim Review page with server-side claim data. Reviewer-only."""
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    sessionIds = getSessionIds(request)
    row = await _fetchClaimDetail(claimId)

    if row is None:
        return templates.TemplateResponse(
            request,
            "review.html",
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
                "aiInsight": None,
            },
            status_code=404,
        )

    claim, receipt = _buildClaimContext(row)
    intakeFindings = row.get("intake_findings")
    if isinstance(intakeFindings, str):
        try:
            intakeFindings = json.loads(intakeFindings)
        except Exception:
            intakeFindings = {}
    flagReason = _parseFlagReason(intakeFindings)
    aiInsight = await _fetchAiInsight(row["employee_id"])

    return templates.TemplateResponse(
        request,
        "review.html",
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
            "aiInsight": aiInsight,
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
    intakeFindings = row.get("intake_findings") or {}
    if isinstance(intakeFindings, str):
        try:
            intakeFindings = json.loads(intakeFindings)
        except Exception:
            intakeFindings = {}
    flagReason = _parseFlagReason(intakeFindings)
    aiInsight = await _fetchAiInsight(row["employee_id"])

    return JSONResponse(
        {
            "claim": claim,
            "receipt": receipt,
            "flagReason": flagReason,
            "aiInsight": aiInsight,
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

    newStatus = "approved" if action == "approve" else "rejected"
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

    async with getAsyncSession() as session:
        # Update claim status
        updateStmt = (
            update(Claim)
            .where(Claim.id == claimId)
            .values(
                status=newStatus,
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
    response.headers["HX-Redirect"] = "/dashboard"
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
