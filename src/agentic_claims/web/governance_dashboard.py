from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from agentic_governance import load_audit_records, load_failure_records, verify_audit_chain
from agentic_claims.infrastructure.database.models import AuditLog, Claim, User
from agentic_claims.web.db import getAsyncSession
from agentic_claims.web.templating import projectRoot


_ACTIONABLE_CONTENT_RESULTS = {
    "Transform",
    "Escalate",
    "Block",
    "transformed",
    "escalated",
    "grounding-failed",
    "concerns-found",
}


@dataclass(frozen=True)
class GovernanceFilters:
    claim: str | None = None
    correlation_id: str | None = None
    db_claim_id: int | None = None


def _candidate_audit_dirs() -> list[Path]:
    return [projectRoot / ".governance-audit", projectRoot / ".agentic_governance"]


def _list_audit_files() -> list[Path]:
    files: list[Path] = []
    for directory in _candidate_audit_dirs():
        if directory.is_dir():
            files.extend(sorted(directory.glob("audit-*.jsonl")))
    return sorted(set(files))


async def buildGovernanceDashboard(filters: GovernanceFilters) -> dict[str, Any]:
    audit_files = _list_audit_files()
    all_records = []
    for path in audit_files:
        all_records.extend(load_audit_records(path))

    claim_context = await _resolve_claim_context(filters, all_records)
    filtered_records = _filter_records(all_records, filters, claim_context)
    filtered_entries = [record.entry for record in filtered_records]

    claim_metadata = await _fetch_claim_metadata(claim_context.get("db_claim_ids", set()))
    claim_governance_rows = await _fetch_claim_governance_rows(claim_context.get("db_claim_ids", set()))
    failure_records = []
    for path in audit_files:
        failure_records.extend(load_failure_records(path))
    filtered_failures = _filter_records(failure_records, filters, claim_context)

    file_summaries = []
    integrity_issue_count = 0
    for path in sorted(audit_files, reverse=True):
        result = verify_audit_chain(path)
        integrity_issue_count += len(result.issues)
        file_summaries.append(
            {
                "name": path.name,
                "eventCount": result.event_count,
                "ok": result.ok,
                "issueCount": len(result.issues),
                "firstEntryHash": result.first_entry_hash,
                "lastEntryHash": result.last_entry_hash,
            }
        )

    failure_entries = [record.entry for record in filtered_failures]
    linkage_warnings = await _build_linkage_warnings(filters, claim_context)

    return {
        "filters": {
            "claim": filters.claim or "",
            "correlationId": filters.correlation_id or "",
            "dbClaimId": "" if filters.db_claim_id is None else str(filters.db_claim_id),
        },
        "scope": _build_scope(filters, claim_context, claim_metadata),
        "overview": _build_overview(filtered_entries, failure_entries, integrity_issue_count),
        "actionAuthorization": _build_action_authorization(filtered_entries),
        "modelContentSafeguards": _build_model_content(filtered_entries, claim_governance_rows),
        "humanOversight": _build_human_oversight(filtered_entries),
        "auditIntegrityMonitoring": _build_audit_integrity(filtered_entries, failure_entries, file_summaries, linkage_warnings),
        "claimLinks": _build_claim_links(filtered_entries, claim_metadata),
        "hasAnyData": bool(filtered_entries or failure_entries),
    }


async def _resolve_claim_context(filters: GovernanceFilters, records: list[Any]) -> dict[str, Any]:
    claim = None
    if filters.db_claim_id is not None:
        async with getAsyncSession() as session:
            claim = await session.get(Claim, filters.db_claim_id)
    elif filters.claim:
        async with getAsyncSession() as session:
            result = await session.execute(select(Claim).where(Claim.claimNumber == filters.claim))
            claim = result.scalar_one_or_none()

    db_claim_ids: set[int] = set()
    claim_numbers: set[str] = set()
    correlation_ids: set[str] = set()
    if claim is not None:
        db_claim_ids.add(claim.id)
        claim_numbers.add(claim.claimNumber)

    for record in records:
        entry = record.entry
        details = entry.get("details") or {}
        contract = details.get("contract") or {}
        if claim is not None:
            if entry.get("dbClaimId") == claim.id:
                if entry.get("correlationId"):
                    correlation_ids.add(entry.get("correlationId"))
                if entry.get("claimId"):
                    correlation_ids.add(entry.get("claimId"))
            if contract.get("claim_number") == claim.claimNumber:
                if entry.get("correlationId"):
                    correlation_ids.add(entry.get("correlationId"))
                if entry.get("claimId"):
                    correlation_ids.add(entry.get("claimId"))

    if filters.correlation_id:
        correlation_ids.add(filters.correlation_id)
    if claim is None and filters.claim:
        claim_numbers.add(filters.claim)

    return {
        "claim": claim,
        "db_claim_ids": db_claim_ids,
        "claim_numbers": claim_numbers,
        "correlation_ids": correlation_ids,
    }


def _filter_records(records: list[Any], filters: GovernanceFilters, claim_context: dict[str, Any]) -> list[Any]:
    if not (filters.claim or filters.correlation_id or filters.db_claim_id is not None):
        return records

    filtered = []
    for record in records:
        entry = record.entry
        details = entry.get("details") or {}
        contract = details.get("contract") or {}
        if filters.db_claim_id is not None and entry.get("dbClaimId") == filters.db_claim_id:
            filtered.append(record)
            continue
        if claim_context["db_claim_ids"] and entry.get("dbClaimId") in claim_context["db_claim_ids"]:
            filtered.append(record)
            continue
        if filters.claim and (
            entry.get("claimId") == filters.claim
            or entry.get("correlationId") == filters.claim
            or contract.get("claim_number") == filters.claim
        ):
            filtered.append(record)
            continue
        if claim_context["claim_numbers"] and contract.get("claim_number") in claim_context["claim_numbers"]:
            filtered.append(record)
            continue
        if filters.correlation_id and (
            entry.get("correlationId") == filters.correlation_id or entry.get("claimId") == filters.correlation_id
        ):
            filtered.append(record)
            continue
        if claim_context["correlation_ids"] and (
            entry.get("correlationId") in claim_context["correlation_ids"]
            or entry.get("claimId") in claim_context["correlation_ids"]
        ):
            filtered.append(record)
            continue
    return filtered


async def _fetch_claim_metadata(db_claim_ids: set[int]) -> dict[int, dict[str, Any]]:
    async with getAsyncSession() as session:
        query = (
            select(
                Claim.id,
                Claim.claimNumber,
                Claim.status,
                Claim.employeeId,
                Claim.totalAmount,
                Claim.currency,
                Claim.advisorDecision,
                User.displayName,
            )
            .outerjoin(User, User.employeeId == Claim.employeeId)
        )
        if db_claim_ids:
            query = query.where(Claim.id.in_(db_claim_ids))
        result = await session.execute(query)
        rows = result.all()
    metadata = {}
    for row in rows:
        metadata[row.id] = {
            "id": row.id,
            "claimNumber": row.claimNumber,
            "status": row.status,
            "employeeId": row.employeeId,
            "displayName": row.displayName,
            "totalAmount": float(row.totalAmount) if row.totalAmount is not None else None,
            "currency": row.currency,
            "advisorDecision": row.advisorDecision,
        }
    return metadata


async def _fetch_claim_governance_rows(db_claim_ids: set[int]) -> list[dict[str, Any]]:
    async with getAsyncSession() as session:
        query = select(
            Claim.id,
            Claim.claimNumber,
            Claim.advisorDecision,
            Claim.advisorFindings,
            Claim.complianceFindings,
            Claim.fraudFindings,
        )
        if db_claim_ids:
            query = query.where(Claim.id.in_(db_claim_ids))
        result = await session.execute(query)
        rows = result.all()
    return [
        {
            "id": row.id,
            "claimNumber": row.claimNumber,
            "advisorDecision": row.advisorDecision,
            "advisorFindings": row.advisorFindings,
            "complianceFindings": row.complianceFindings,
            "fraudFindings": row.fraudFindings,
        }
        for row in rows
    ]


def _build_scope(filters: GovernanceFilters, claim_context: dict[str, Any], claim_metadata: dict[int, dict[str, Any]]) -> dict[str, Any]:
    claim = claim_context.get("claim")
    metadata = claim_metadata.get(claim.id) if claim is not None else None
    label = "All governance events"
    if metadata is not None:
        label = f"{metadata['claimNumber']} · {metadata['status']}"
    elif filters.correlation_id:
        label = f"Correlation {filters.correlation_id}"
    elif filters.claim:
        label = f"Claim {filters.claim}"
    elif filters.db_claim_id is not None:
        label = f"DB Claim {filters.db_claim_id}"
    return {
        "isFiltered": bool(filters.claim or filters.correlation_id or filters.db_claim_id is not None),
        "label": label,
        "claim": metadata,
    }


def _build_overview(entries: list[dict[str, Any]], failures: list[dict[str, Any]], integrity_issue_count: int) -> dict[str, Any]:
    human_review_claims = {
        (entry.get("dbClaimId") or entry.get("claimId"))
        for entry in entries
        if entry.get("eventType") == "oversight_governance" and entry.get("decision") == "require_human_review"
    }
    escalations = sum(
        1
        for entry in entries
        if str(entry.get("decision", "")).lower() in {"escalate", "require_human_review"}
        or str(entry.get("result", "")).lower() in {"escalate", "escalated"}
    )
    return {
        "totalEvents": len(entries),
        "escalations": escalations,
        "humanReviewRequired": len({c for c in human_review_claims if c is not None}),
        "systemFailures": len(failures),
        "integrityStatus": "Healthy" if integrity_issue_count == 0 else "Issues detected",
    }


def _build_action_authorization(entries: list[dict[str, Any]]) -> dict[str, Any]:
    action_entries = [entry for entry in entries if entry.get("eventType") == "action_governance"]
    by_decision = Counter(entry.get("decision") or "Unknown" for entry in action_entries)
    agent_tool_counts: dict[str, Counter] = defaultdict(Counter)
    blocked_by_agent = Counter()
    blocked_by_tool_by_agent: dict[str, Counter] = defaultdict(Counter)

    for entry in action_entries:
        agent = entry.get("agentIdentity") or {}
        agent_id = agent.get("id") if isinstance(agent, dict) else agent
        agent_id = agent_id or "unknown"
        envelope = entry.get("envelope") or {}
        tool = envelope.get("toolName") or "unknown"
        decision = entry.get("decision") or "Unknown"
        result = entry.get("result") or "Unknown"

        agent_tool_counts[agent_id][tool] += 1
        if str(decision).lower() in {"deny", "escalate"} or str(result).lower() in {"deny", "denied", "escalate", "escalated"}:
            blocked_by_agent[agent_id] += 1
            blocked_by_tool_by_agent[agent_id][tool] += 1

    agent_distributions = []
    for agent_id, tool_counts in sorted(agent_tool_counts.items()):
        total = sum(tool_counts.values())
        distribution = []
        for tool, count in tool_counts.most_common():
            pct = round((count / total) * 100, 1) if total else 0.0
            distribution.append({"tool": tool, "count": count, "pct": pct})
        agent_distributions.append(
            {
                "agent": agent_id,
                "totalActions": total,
                "distribution": distribution,
            }
        )

    blocked_profiles = []
    for agent_id in sorted(set(agent_tool_counts.keys()) | set(blocked_by_agent.keys())):
        blocked_total = blocked_by_agent.get(agent_id, 0)
        blocked_tools = [
            {"tool": tool, "count": count}
            for tool, count in blocked_by_tool_by_agent.get(agent_id, Counter()).most_common()
        ]
        blocked_profiles.append(
            {
                "agent": agent_id,
                "blockedCalls": blocked_total,
                "blockedTools": blocked_tools,
            }
        )

    top_agent = max(agent_distributions, key=lambda row: row["totalActions"], default=None)
    top_blocked_tool = None
    blocked_tool_counter = Counter()
    for row in blocked_profiles:
        for item in row["blockedTools"]:
            blocked_tool_counter[item["tool"]] += item["count"]
    if blocked_tool_counter:
        label, count = blocked_tool_counter.most_common(1)[0]
        top_blocked_tool = {"label": label, "count": count}

    return {
        "totalEvents": len(action_entries),
        "byDecision": dict(by_decision),
        "agentDistributions": agent_distributions,
        "blockedProfiles": blocked_profiles,
        "blockedTotal": sum(blocked_by_agent.values()),
        "agentsAffected": sum(1 for row in blocked_profiles if row["blockedCalls"] > 0),
        "topAgent": top_agent,
        "topBlockedTool": top_blocked_tool,
    }


def _build_model_content(entries: list[dict[str, Any]], claim_governance_rows: list[dict[str, Any]]) -> dict[str, Any]:
    content_entries = [entry for entry in entries if entry.get("eventType") == "content_governance"]
    actionable = [entry for entry in content_entries if entry.get("result") in _ACTIONABLE_CONTENT_RESULTS]
    controls: dict[str, dict[str, Any]] = {
        "B1": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": Counter()},
        "B2": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": Counter(), "entityTypes": Counter()},
        "B3": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": Counter()},
        "B4": {"evaluations": 0, "passes": 0, "interventions": 0, "outcomes": Counter(), "flags": Counter()},
        "B6": {"materialDecisions": 0, "explanationsPresent": 0, "explanationsMissing": 0},
    }
    alerts = []
    for entry in content_entries:
        fired_controls = ((entry.get("disposition") or {}).get("firedControls") or [])
        for control in fired_controls:
            control_id = control.get("controlId")
            if control_id not in controls or control_id == "B6":
                continue
            result = str(control.get("result") or "unknown")
            controls[control_id]["evaluations"] += 1
            controls[control_id]["outcomes"][result] += 1
            if result in {"allowed", "grounded", "no-concerns"}:
                controls[control_id]["passes"] += 1
            else:
                controls[control_id]["interventions"] += 1
            if control_id == "B2":
                for entity_type in control.get("entityTypes") or []:
                    controls[control_id]["entityTypes"][entity_type] += 1
        if entry in actionable:
            alerts.append(
                {
                    "timestamp": entry.get("timestamp"),
                    "agent": entry.get("agentIdentity") or "unknown",
                    "contentType": entry.get("contentType") or "unknown",
                    "result": entry.get("result"),
                    "claimId": entry.get("dbClaimId") or entry.get("claimId"),
                }
            )

    for row in claim_governance_rows:
        for findings_key in ("complianceFindings", "advisorFindings", "fraudFindings"):
            findings = row.get(findings_key) or {}
            for governance_item in findings.get("governance") or []:
                if governance_item.get("control") == "B4":
                    for flag in (governance_item.get("details") or {}).get("flags") or []:
                        controls["B4"]["flags"][flag] += 1
        if row.get("advisorDecision"):
            controls["B6"]["materialDecisions"] += 1
            if (row.get("advisorFindings") or {}).get("reviewerExplanation"):
                controls["B6"]["explanationsPresent"] += 1
            else:
                controls["B6"]["explanationsMissing"] += 1

    return {
        "totalEvents": len(content_entries),
        "actionableAlerts": len(actionable),
        "b1": {
            "evaluations": controls["B1"]["evaluations"],
            "passes": controls["B1"]["passes"],
            "interventions": controls["B1"]["interventions"],
            "outcomes": _counter_rows(controls["B1"]["outcomes"]),
        },
        "b2": {
            "evaluations": controls["B2"]["evaluations"],
            "passes": controls["B2"]["passes"],
            "transformed": controls["B2"]["outcomes"].get("transformed", 0),
            "entityTypes": _counter_rows(controls["B2"]["entityTypes"]),
        },
        "b3": {
            "evaluations": controls["B3"]["evaluations"],
            "passes": controls["B3"]["passes"],
            "interventions": controls["B3"]["interventions"],
            "outcomes": _counter_rows(controls["B3"]["outcomes"]),
        },
        "b4": {
            "evaluations": controls["B4"]["evaluations"],
            "passes": controls["B4"]["passes"],
            "concerns": controls["B4"]["outcomes"].get("concerns-found", 0),
            "flags": _counter_rows(controls["B4"]["flags"]),
        },
        "b6": {
            "materialDecisions": controls["B6"]["materialDecisions"],
            "explanationsPresent": controls["B6"]["explanationsPresent"],
            "explanationsMissing": controls["B6"]["explanationsMissing"],
        },
        "recentAlerts": alerts[-8:][::-1],
    }


def _build_human_oversight(entries: list[dict[str, Any]]) -> dict[str, Any]:
    oversight_entries = [entry for entry in entries if entry.get("eventType") == "oversight_governance"]
    reviewer_entries = [entry for entry in entries if entry.get("eventType") == "reviewer_decision"]
    by_decision = Counter(entry.get("decision") or "Unknown" for entry in oversight_entries)
    reviewer_by_decision = Counter(entry.get("decision") or "Unknown" for entry in reviewer_entries)
    contracts = []
    contract_statuses = Counter()
    for entry in oversight_entries[-12:][::-1]:
        details = entry.get("details") or {}
        contract = details.get("contract") or {}
        status = contract.get("status") or "unknown"
        contract_statuses[status] += 1
        contracts.append(
            {
                "claimNumber": contract.get("claim_number") or entry.get("claimId"),
                "decision": entry.get("decision"),
                "contractId": contract.get("contract_id"),
                "status": status,
                "reasons": ", ".join(details.get("reasons") or []),
            }
        )
    return {
        "oversightEvents": len(oversight_entries),
        "reviewerDecisions": len(reviewer_entries),
        "oversightByDecision": dict(by_decision),
        "reviewerByDecision": dict(reviewer_by_decision),
        "contracts": contracts,
        "contractStatuses": _counter_rows(contract_statuses),
        "reviewRequiredCount": by_decision.get("require_human_review", 0),
        "openContracts": contract_statuses.get("pending_review", 0),
    }


def _build_audit_integrity(
    entries: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    file_summaries: list[dict[str, Any]],
    linkage_warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    claims_seen = {
        entry.get("dbClaimId") or entry.get("claimId")
        for entry in entries
        if entry.get("dbClaimId") is not None or entry.get("claimId") not in (None, "unknown")
    }
    failure_events = [
        {
            "timestamp": entry.get("timestamp"),
            "component": (entry.get("details") or {}).get("component"),
            "error": (entry.get("details") or {}).get("error"),
            "claimId": entry.get("dbClaimId") or entry.get("claimId"),
        }
        for entry in failures[-12:][::-1]
    ]
    failure_component_counts = Counter(event.get("component") or "unknown" for event in failure_events)
    warning_counts = Counter(row.get("message") or "warning" for row in linkage_warnings)
    return {
        "fileSummaries": file_summaries[:8],
        "failureEvents": failure_events,
        "failureComponents": _counter_rows(failure_component_counts),
        "linkageWarnings": linkage_warnings,
        "warningTypes": _counter_rows(warning_counts),
        "reconstructionReadiness": {
            "claimsObserved": len({c for c in claims_seen if c is not None}),
            "failureEvents": len(failures),
            "filesWithIssues": sum(1 for summary in file_summaries if not summary["ok"]),
        },
    }


def _build_claim_links(entries: list[dict[str, Any]], claim_metadata: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_claim = {}
    for entry in entries:
        db_claim_id = entry.get("dbClaimId")
        if db_claim_id is None or db_claim_id not in claim_metadata:
            continue
        latest_by_claim[db_claim_id] = entry
    links = []
    for claim_id, entry in list(latest_by_claim.items())[-12:][::-1]:
        metadata = claim_metadata[claim_id]
        links.append(
            {
                "id": claim_id,
                "claimNumber": metadata["claimNumber"],
                "status": metadata["status"],
                "amount": metadata["totalAmount"],
                "currency": metadata["currency"],
                "displayName": metadata["displayName"],
                "lastEventType": entry.get("eventType"),
            }
        )
    return links


async def _build_linkage_warnings(filters: GovernanceFilters, claim_context: dict[str, Any]) -> list[dict[str, Any]]:
    async with getAsyncSession() as session:
        claim_query = select(Claim.id, Claim.claimNumber, Claim.advisorFindings, Claim.status)
        if claim_context.get("db_claim_ids"):
            claim_query = claim_query.where(Claim.id.in_(claim_context["db_claim_ids"]))
        result = await session.execute(claim_query)
        claims = result.all()

        audit_query = select(AuditLog.claimId, AuditLog.action, AuditLog.newValue).where(
            AuditLog.action.in_(["claim_approved", "claim_rejected"])
        )
        if claim_context.get("db_claim_ids"):
            audit_query = audit_query.where(AuditLog.claimId.in_(claim_context["db_claim_ids"]))
        audit_rows = (await session.execute(audit_query)).all()

    warnings = []
    for claim_id, claim_number, advisor_findings, status in claims:
        oversight = (advisor_findings or {}).get("governanceOversight") if advisor_findings else None
        if oversight and not oversight.get("eventRef"):
            warnings.append(
                {
                    "claimNumber": claim_number,
                    "message": "Governance oversight projection is missing canonical eventRef.",
                    "severity": "warning",
                }
            )
    for claim_id, action, new_value in audit_rows:
        payload = {}
        try:
            payload = json.loads(new_value) if new_value else {}
        except Exception:
            payload = {}
        if not payload.get("governanceEventRef"):
            warnings.append(
                {
                    "claimNumber": str(claim_id),
                    "message": f"Reviewer audit projection for {action} is missing governanceEventRef.",
                    "severity": "warning",
                }
            )
    return warnings[:12]


def _counter_rows(counter: Counter) -> list[dict[str, Any]]:
    return [{"label": label, "count": count} for label, count in counter.most_common(6)]
