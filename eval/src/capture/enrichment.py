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
                        intake_findings,
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
                intakeFindings, complianceFindings, fraudFindings, advisorDecision, advisorFindings = row
                return {
                    "intakeFindings": intakeFindings,
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


async def _fetchReceiptFields(
    claimNumber: str, dbUrl: str
) -> Optional[dict[str, Any]]:
    """Query the receipts table for structured extracted fields by claim_number.

    Returns a normalized dict suitable for FieldExtractionMetric / AmountReconciliationMetric,
    or None if the claim has no linked receipt.
    """
    try:
        async with await psycopg.AsyncConnection.connect(dbUrl) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        r.merchant,
                        r.date,
                        r.total_amount,
                        r.currency,
                        r.line_items,
                        r.original_amount,
                        r.original_currency,
                        r.converted_amount_sgd
                    FROM receipts r
                    JOIN claims c ON r.claim_id = c.id
                    WHERE c.claim_number = %s
                    ORDER BY r.id DESC
                    LIMIT 1
                    """,
                    (claimNumber,),
                )
                row = await cur.fetchone()
                if row is None:
                    return None
                (
                    merchant, date, totalAmount, currency, lineItems,
                    originalAmount, originalCurrency, convertedAmountSgd,
                ) = row
                fields: dict[str, Any] = {}
                if merchant is not None:
                    fields["merchant"] = merchant
                if date is not None:
                    fields["date"] = str(date)
                if totalAmount is not None:
                    fields["total"] = float(totalAmount)
                if currency is not None:
                    fields["currency"] = currency
                if lineItems is not None:
                    fields["lineItems"] = lineItems
                if originalAmount is not None:
                    fields["originalAmount"] = float(originalAmount)
                if originalCurrency is not None:
                    fields["originalCurrency"] = originalCurrency
                if convertedAmountSgd is not None:
                    fields["convertedAmountSgd"] = float(convertedAmountSgd)
                return fields if fields else None
    except Exception as exc:
        logger.warning(
            "enrichment: receipts query failed for claim %s: %s",
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
# DB reset
# ---------------------------------------------------------------------------


async def resetEvalDatabase(dbUrl: str) -> None:
    """Truncate all claim data before a full eval run to prevent cross-run contamination.

    The fraud agent detects duplicates by querying claims history. Without a reset,
    repeated eval runs accumulate identical receipts and the fraud agent flags every
    re-submitted benchmark as a duplicate, poisoning advisor decisions.

    Truncates: audit_log, receipts, claims (cascade order respects FK constraints).
    Leaves intact: alembic_version, users, LangGraph checkpoint tables.
    """
    try:
        async with await psycopg.AsyncConnection.connect(dbUrl) as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE audit_log, receipts, claims RESTART IDENTITY CASCADE")
            await conn.commit()
        logger.info("resetEvalDatabase: claims/receipts/audit_log truncated")
    except Exception as exc:
        raise RuntimeError(f"resetEvalDatabase: failed to truncate eval tables: {exc}") from exc


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

    # --- 1. Query claims table, polling until advisor_decision is populated ---
    # The post-submission pipeline (compliance → fraud → advisor) runs asynchronously
    # after intake. Poll every 30s for up to 3 minutes so we capture the full verdict.
    POLL_INTERVAL_S = 30
    POLL_MAX_ATTEMPTS = 6  # 6 × 30s = 3 minutes
    claimRow = None
    for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
        claimRow = await _fetchClaimRow(claimId, dbUrl)
        if claimRow is not None and claimRow.get("advisorDecision"):
            logger.info(
                "enrichment: advisor_decision ready for %s after %d poll(s)",
                benchmarkId,
                attempt,
            )
            break
        if attempt < POLL_MAX_ATTEMPTS:
            logger.info(
                "enrichment: advisor_decision not yet set for %s (attempt %d/%d) — waiting %ds",
                benchmarkId,
                attempt,
                POLL_MAX_ATTEMPTS,
                POLL_INTERVAL_S,
            )
            import asyncio as _asyncio
            await _asyncio.sleep(POLL_INTERVAL_S)
        else:
            logger.warning(
                "enrichment: advisor_decision still null for %s after %d attempts — proceeding with partial data",
                benchmarkId,
                POLL_MAX_ATTEMPTS,
            )

    if claimRow is None:
        logger.warning(
            "enrichment: claim '%s' not found in DB for benchmark %s",
            claimId,
            benchmarkId,
        )
    else:
        capture["intakeFindings"] = claimRow["intakeFindings"]
        capture["complianceFindings"] = claimRow["complianceFindings"]
        capture["fraudFindings"] = claimRow["fraudFindings"]
        # Store advisor decision in a separate field — do NOT override agentDecision.
        # agentDecision is the intake-stage browser capture; keeping them separate
        # allows routing actual_output correctly per benchmark stage.
        capture["advisorDecision"] = claimRow["advisorDecision"]
        capture["advisorReasoning"] = _parseAdvisorReasoning(
            claimRow["advisorFindings"]
        )

    # --- 1b. Query receipts table for structured extracted fields ---
    receiptFields = await _fetchReceiptFields(claimId, dbUrl)
    if receiptFields:
        # Start with receipts table fields (merchant, date, total, currency, lineItems)
        mergedFields: dict = dict(receiptFields)

        # Merge richer fields from intakeFindings.extractedFields (VLM raw output).
        # intakeFindings may include subtotal, serviceCharge, gst, paymentMethod,
        # passenger, etc. that the receipts table schema does not store.
        intakeFindings = capture.get("intakeFindings")
        if isinstance(intakeFindings, dict):
            vlmFields = intakeFindings.get("extractedFields", {})
            if isinstance(vlmFields, dict):
                for k, v in vlmFields.items():
                    if k not in mergedFields and v is not None:
                        mergedFields[k] = v

        capture["extractedFields"] = mergedFields

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
