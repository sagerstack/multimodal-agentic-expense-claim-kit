"""Post-capture DB enrichment for benchmark results.

After the Playwright subagent captures a result from the browser, this module
queries the PostgreSQL database and Qdrant to attach:
  - compliance_findings   (from claims table, JSONB)
  - fraud_findings        (from claims table, JSONB)
  - advisor_decision      (from claims table, string)
  - advisor_findings      (from claims table, JSONB)
  - retrieved policy chunks (from Qdrant, via section references in audit_log)

All operations are async. All edge cases (missing claimId, DB unreachable,
Qdrant unreachable) are handled gracefully with warnings.

This module is fully decoupled from the app -- no imports from agentic_claims.
"""

import json
import logging
from typing import Any, Optional

import httpx
import psycopg

logger = logging.getLogger(__name__)

_QDRANT_COLLECTION = "expense_policies"


async def _fetchClaimRow(
    claimNumber: str, dbUrl: str
) -> Optional[dict[str, Any]]:
    """Query the claims table for agent output columns by claim_number.

    Args:
        claimNumber: The claim number string (e.g. "CLAIM-abc12345").
        dbUrl: PostgreSQL connection URL (psycopg format).

    Returns:
        Dict with compliance_findings, fraud_findings, advisor_decision,
        advisor_findings keys, or None if not found.
    """
    # psycopg accepts postgresql:// or postgres:// DSN
    connStr = dbUrl
    try:
        async with await psycopg.AsyncConnection.connect(connStr) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        compliance_findings,
                        fraud_findings,
                        advisor_decision,
                        advisor_findings
                    FROM claims
                    WHERE claim_number = %s
                    LIMIT 1
                    """,
                    (claimNumber,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                complianceFindings, fraudFindings, advisorDecision, advisorFindings = row
                return {
                    "complianceFindings": complianceFindings,
                    "fraudFindings": fraudFindings,
                    "advisorDecision": advisorDecision,
                    "advisorFindings": advisorFindings,
                }
    except Exception as exc:
        logger.warning(
            "enrichment: DB query failed for claim %s: %s",
            claimNumber,
            exc,
        )
        return None


async def _fetchPolicyCheckRefs(
    claimNumber: str, dbUrl: str
) -> list[str]:
    """Query audit_log for policy_check entries and extract section references.

    Looks for rows where action = 'policy_check'. The new_value column is
    expected to be a JSON string with a 'policyRefs' key (list of section names).

    Args:
        claimNumber: The claim number used to look up the claim id.
        dbUrl: PostgreSQL connection URL.

    Returns:
        List of section/category strings to query from Qdrant.
    """
    refs: list[str] = []
    try:
        async with await psycopg.AsyncConnection.connect(dbUrl) as conn:
            async with conn.cursor() as cur:
                # First resolve claim_number → id
                await cur.execute(
                    "SELECT id FROM claims WHERE claim_number = %s LIMIT 1",
                    (claimNumber,),
                )
                claimRow = await cur.fetchone()
                if claimRow is None:
                    return refs
                claimId = claimRow[0]

                await cur.execute(
                    """
                    SELECT new_value
                    FROM audit_log
                    WHERE claim_id = %s AND action = 'policy_check'
                    ORDER BY timestamp
                    """,
                    (claimId,),
                )
                rows = await cur.fetchall()
                for (newValue,) in rows:
                    if not newValue:
                        continue
                    try:
                        data = json.loads(newValue) if isinstance(newValue, str) else newValue
                        policyRefs = data.get("policyRefs", [])
                        if isinstance(policyRefs, list):
                            refs.extend(str(r) for r in policyRefs)
                    except (json.JSONDecodeError, AttributeError):
                        pass
    except Exception as exc:
        logger.warning(
            "enrichment: audit_log query failed for claim %s: %s",
            claimNumber,
            exc,
        )
    return refs


async def _fetchPolicyChunksFromQdrant(
    sectionRefs: list[str], qdrantUrl: str
) -> list[str]:
    """Query Qdrant for policy chunks matching the given section references.

    Uses the scroll API with a filter on the `section` metadata field.

    Args:
        sectionRefs: List of section name strings from audit_log.
        qdrantUrl: Base URL for Qdrant (e.g. "http://localhost:6333").

    Returns:
        List of policy text strings. Empty list if unreachable or no refs.
    """
    if not sectionRefs:
        return []

    chunks: list[str] = []
    seenTexts: set[str] = set()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for sectionName in set(sectionRefs):  # deduplicate refs
                try:
                    response = await client.post(
                        f"{qdrantUrl}/collections/{_QDRANT_COLLECTION}/points/scroll",
                        json={
                            "filter": {
                                "must": [
                                    {
                                        "key": "section",
                                        "match": {"value": sectionName},
                                    }
                                ]
                            },
                            "with_payload": True,
                            "limit": 10,
                        },
                    )
                    response.raise_for_status()
                    points = response.json().get("result", {}).get("points", [])
                    for point in points:
                        text = point.get("payload", {}).get("text", "")
                        if text and text not in seenTexts:
                            chunks.append(text)
                            seenTexts.add(text)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "enrichment: Qdrant query failed for section '%s': %s",
                        sectionName,
                        exc,
                    )
    except Exception as exc:
        logger.warning("enrichment: Qdrant client error: %s", exc)

    return chunks


def _parseAdvisorReasoning(advisorFindings: Any) -> Optional[str]:
    """Extract a human-readable reasoning string from advisor_findings JSONB.

    The advisor agent stores its findings as a JSONB dict. This helper tries
    common key patterns to extract the reasoning text.

    Args:
        advisorFindings: The JSONB value from the claims.advisor_findings column.

    Returns:
        A string with the reasoning, or None if unavailable.
    """
    if advisorFindings is None:
        return None
    if isinstance(advisorFindings, str):
        return advisorFindings
    if isinstance(advisorFindings, dict):
        # Try common keys in order of preference
        for key in ("reasoning", "rationale", "explanation", "summary", "message"):
            if key in advisorFindings:
                return str(advisorFindings[key])
        # Fall back to serialising the whole dict
        return json.dumps(advisorFindings)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def enrichCapturedResult(
    capturedResult: dict,
    dbUrl: str,
    qdrantUrl: str = "http://localhost:6333",
) -> dict:
    """Enrich a captured benchmark result with DB and Qdrant data.

    Fills in fields that the browser capture step cannot observe:
      - complianceFindings (from claims.compliance_findings)
      - fraudFindings      (from claims.fraud_findings)
      - agentDecision      (from claims.advisor_decision, overrides browser value)
      - advisorReasoning   (parsed from claims.advisor_findings)
      - retrievedPolicyChunks (from Qdrant via audit_log policy_check entries)

    The input dict is modified in-place AND returned.

    Edge cases:
      - claimId is None/empty: skip enrichment, log warning, return unchanged
      - Claim not found in DB: set all findings to None, log warning
      - DB unreachable: log warning, return partial result
      - Qdrant unreachable: set retrievedPolicyChunks to [], log warning

    Args:
        capturedResult: The result dict produced by the subagent (or loaded
            from disk). Must have a "capture" key.
        dbUrl: PostgreSQL connection URL.
        qdrantUrl: Qdrant base URL. Defaults to http://localhost:6333.

    Returns:
        The enriched (mutated) result dict.
    """
    benchmarkId = capturedResult.get("benchmarkId", "UNKNOWN")
    capture = capturedResult.get("capture")

    if capture is None:
        logger.warning(
            "enrichment: no 'capture' key in result for %s — skipping",
            benchmarkId,
        )
        return capturedResult

    claimId: Optional[str] = capture.get("claimId")
    if not claimId:
        logger.warning(
            "enrichment: claimId is empty for %s — skipping DB enrichment",
            benchmarkId,
        )
        return capturedResult

    # --- 1. Query claims table ---
    claimRow = await _fetchClaimRow(claimId, dbUrl)
    if claimRow is None:
        logger.warning(
            "enrichment: claim '%s' not found in DB for benchmark %s",
            claimId,
            benchmarkId,
        )
        # Leave findings as None (already the default from subagent)
    else:
        capture["complianceFindings"] = claimRow["complianceFindings"]
        capture["fraudFindings"] = claimRow["fraudFindings"]
        # Override agentDecision with authoritative DB value if present
        if claimRow["advisorDecision"]:
            capture["agentDecision"] = claimRow["advisorDecision"]
        capture["advisorReasoning"] = _parseAdvisorReasoning(
            claimRow["advisorFindings"]
        )

    # --- 2. Query audit_log for policy section references ---
    sectionRefs = await _fetchPolicyCheckRefs(claimId, dbUrl)

    # --- 3. Fetch matching policy chunks from Qdrant ---
    policyChunks = await _fetchPolicyChunksFromQdrant(sectionRefs, qdrantUrl)
    capture["retrievedPolicyChunks"] = policyChunks

    return capturedResult


async def enrichAllResults(
    results: list[dict],
    dbUrl: str,
    qdrantUrl: str = "http://localhost:6333",
) -> list[dict]:
    """Enrich all captured results sequentially.

    Runs enrichCapturedResult for each result in order. Errors for individual
    benchmarks are logged and do not abort the batch.

    Args:
        results: List of captured result dicts.
        dbUrl: PostgreSQL connection URL.
        qdrantUrl: Qdrant base URL.

    Returns:
        The same list with each result mutated in-place.
    """
    for result in results:
        benchmarkId = result.get("benchmarkId", "UNKNOWN")
        try:
            await enrichCapturedResult(result, dbUrl, qdrantUrl)
        except Exception as exc:
            logger.error(
                "enrichment: unexpected error for %s: %s",
                benchmarkId,
                exc,
            )
    return results
