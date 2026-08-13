"""Build a System A capture JSON from a live claim + scraped transcript.

Manual Playwright-MCP driving produces two artifacts per benchmark: the
#chatHistory innerText and the claim number. Everything else in the capture
schema is already persisted by the app, so this script reads it from Postgres
rather than re-deriving it from agent prose.

Field sourcing matches what the System B captures contain:
  extractedFields   <- claims.intake_findings.extractedFields + .conversion
  confidence        <- mean of intake_findings.confidenceScores, bucketed
  category          <- claims.category
  agentDecision     <- claims.advisor_decision
  compliance/fraud  <- claims.compliance_findings / .fraud_findings
  advisorReasoning  <- claims.advisor_findings.reasoning

Usage:
  python buildCapture.py ER-005 CLAIM-281 transcript.txt [--note "..."]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path("/Users/sagarpratapsingh/dev/sagerstack/agentic-expense-claims")
sys.path.insert(0, str(REPO))

from eval.src.capture.playwrightCapture import parseTranscript  # noqa: E402
from eval.src.dataset import BENCHMARKS  # noqa: E402

RESULTS_DIR = REPO / "eval" / "results" / "systemA"


def queryClaim(claimNumber: str) -> dict:
    """Return the claim row as a dict via psql JSON output."""
    sql = (
        "SELECT row_to_json(t) FROM (SELECT claim_number, status, category, "
        "advisor_decision, intake_findings, compliance_findings, fraud_findings, "
        "advisor_findings FROM claims WHERE claim_number = '%s') t;" % claimNumber
    )
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres",
         "psql", "-U", "agentic", "-d", "agentic_claims", "-t", "-A", "-c", sql],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out:
        raise SystemExit(f"Claim {claimNumber} not found in DB")
    return json.loads(out)


def bucketConfidence(scores: dict) -> str:
    """Bucket the per-field confidence scores into the categorical label the
    transcript shows. Mean-based: a single Low field (commonly paymentMethod)
    must not drag an otherwise-High extraction down, which matches how the
    System B captures recorded 'High' alongside a Low paymentMethod."""
    if not scores:
        return None
    mean = sum(scores.values()) / len(scores)
    return "High" if mean >= 0.9 else ("Medium" if mean >= 0.7 else "Low")


def buildExtractedFields(claim: dict) -> dict:
    intake = claim.get("intake_findings") or {}
    ef = intake.get("extractedFields") or {}
    conv = intake.get("conversion") or {}
    lineItems = ef.get("lineItems")

    fields = {
        "merchant": ef.get("merchant"),
        "date": ef.get("date"),
        "total": ef.get("totalAmount"),
        "currency": ef.get("currency"),
        "tax": ef.get("tax"),
        "paymentMethod": ef.get("paymentMethod"),
        "lineItems": len(lineItems) if isinstance(lineItems, list) else None,
        "category": claim.get("category"),
    }
    if conv.get("convertedAmount") is not None:
        fields["convertedAmount"] = conv["convertedAmount"]
        fields["convertedCurrency"] = "SGD"
        fields["exchangeRate"] = conv.get("rate")
    confidence = bucketConfidence(intake.get("confidenceScores") or {})
    if confidence:
        fields["confidence"] = confidence
    return fields


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmarkId")
    parser.add_argument("claimNumber")
    parser.add_argument("transcriptFile")
    parser.add_argument("--note", default=None)
    args = parser.parse_args()

    benchmark = next(
        (b for b in BENCHMARKS if b["benchmarkId"] == args.benchmarkId), None
    )
    if benchmark is None:
        raise SystemExit(f"Unknown benchmark {args.benchmarkId}")

    transcriptText = Path(args.transcriptFile).read_text()
    turns = parseTranscript(transcriptText)
    claim = queryClaim(args.claimNumber)

    advisorFindings = claim.get("advisor_findings") or {}
    result = {
        "benchmarkId": benchmark["benchmarkId"],
        "benchmark": benchmark["benchmark"],
        "category": benchmark["category"],
        "file": benchmark["file"],
        "scoringType": benchmark["scoringType"],
        "capture": {
            "claimId": claim["claim_number"],
            "conversationTranscript": turns,
            "extractedFields": buildExtractedFields(claim),
            "agentDecision": claim.get("advisor_decision") or "submitted",
            "complianceFindings": claim.get("compliance_findings"),
            "fraudFindings": claim.get("fraud_findings"),
            "advisorReasoning": advisorFindings.get("reasoning"),
            "retrievedPolicyChunks": [],
        },
        "expected": {
            "expectedDecision": benchmark["expectedDecision"],
            "passCriteria": benchmark["passCriteria"],
            "companionMetadata": benchmark.get("companionMetadata"),
        },
    }
    if args.note:
        result["captureNote"] = args.note

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    outPath = RESULTS_DIR / f"{args.benchmarkId}.json"
    outPath.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {outPath}")
    print(f"  claim={claim['claim_number']} decision={result['capture']['agentDecision']} "
          f"turns={len(turns)} status={claim['status']}")
    print(f"  fields={json.dumps(result['capture']['extractedFields'])}")


if __name__ == "__main__":
    main()
