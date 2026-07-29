"""Governance dashboard router — single-page monitoring console backed by canonical audit data."""

import logging

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import RedirectResponse

from agentic_claims.web.auth import getCurrentUser
from agentic_claims.web.governance_dashboard import GovernanceFilters, buildGovernanceDashboard
from agentic_claims.web.session import getSessionIds
from agentic_claims.web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/governance")
async def governancePage(request: Request):
    currentUser = getCurrentUser(request)
    if currentUser["role"] != "reviewer":
        return RedirectResponse("/", status_code=302)

    claim = request.query_params.get("claim") or None
    correlation_id = request.query_params.get("correlationId") or None
    db_claim_id_raw = request.query_params.get("dbClaimId") or None
    db_claim_id = None
    if db_claim_id_raw:
        try:
            db_claim_id = int(db_claim_id_raw)
        except ValueError:
            db_claim_id = None

    filters = GovernanceFilters(
        claim=claim,
        correlation_id=correlation_id,
        db_claim_id=db_claim_id,
    )

    sessionIds = getSessionIds(request)

    try:
        dashboard = await buildGovernanceDashboard(filters)
    except Exception:
        logger.exception("Governance dashboard query failed — rendering empty dashboard")
        dashboard = {
            "filters": {"claim": claim or "", "correlationId": correlation_id or "", "dbClaimId": db_claim_id_raw or ""},
            "scope": {"isFiltered": bool(claim or correlation_id or db_claim_id_raw), "label": "Governance dashboard unavailable", "claim": None},
            "overview": {"totalEvents": 0, "escalations": 0, "humanReviewRequired": 0, "systemFailures": 0, "integrityStatus": "Unavailable"},
            "actionAuthorization": {"totalEvents": 0, "byDecision": {}, "agentDistributions": [], "blockedProfiles": [], "blockedTotal": 0, "agentsAffected": 0, "topAgent": None, "topBlockedTool": None},
            "modelContentSafeguards": {"totalEvents": 0, "actionableAlerts": 0, "b1": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": []}, "b2": {"evaluations": 0, "passes": 0, "transformed": 0, "entityTypes": []}, "b3": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": []}, "b4": {"evaluations": 0, "passes": 0, "concerns": 0, "flags": []}, "b6": {"materialDecisions": 0, "explanationsPresent": 0, "explanationsMissing": 0}, "recentAlerts": []},
            "humanOversight": {"oversightEvents": 0, "reviewerDecisions": 0, "oversightByDecision": {}, "reviewerByDecision": {}, "contracts": [], "contractStatuses": [], "reviewRequiredCount": 0, "openContracts": 0},
            "auditIntegrityMonitoring": {"fileSummaries": [], "failureEvents": [], "failureComponents": [], "linkageWarnings": [], "warningTypes": [], "reconstructionReadiness": {"claimsObserved": 0, "failureEvents": 0, "filesWithIssues": 0}},
            "claimLinks": [],
            "hasAnyData": False,
        }

    return templates.TemplateResponse(
        request,
        "governance.html",
        context={
            "activePage": "governance",
            "threadId": sessionIds["threadId"],
            "claimId": sessionIds["claimId"],
            "userRole": currentUser["role"],
            "displayName": currentUser["displayName"],
            "employeeId": currentUser["employeeId"],
            "username": currentUser["username"],
            "dashboard": dashboard,
        },
    )
