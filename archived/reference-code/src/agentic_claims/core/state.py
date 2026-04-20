"""ClaimState definition with Annotated reducers for LangGraph."""

from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ClaimState(TypedDict):
    """State for the expense claim workflow.

    This is the shared state passed between all agent nodes in the LangGraph.
    Phase 1 intentionally keeps it minimal - future phases will expand with
    receipt data, findings, policy results, etc.
    """

    claimId: str
    status: str
    messages: Annotated[list[AnyMessage], add_messages]

    # Phase 2.1: Intake Agent conversation fields
    extractedReceipt: Optional[dict]  # VLM extraction output with fields + confidence
    violations: Optional[list[dict]]  # Policy violations with cited clauses
    currencyConversion: Optional[dict]  # Original and converted amounts
    claimSubmitted: Optional[bool]  # Gate flag for routing to compliance/fraud

    # Phase 2.2: Agent observations (mismatches, overrides, red flags) for downstream agents and reviewer audit trail
    intakeFindings: Optional[dict]

    # Phase 3: Post-submission agent findings — jamesoon
    # complianceFindings: structured verdict from Compliance Agent (Evaluator pattern)
    #   Shape: {verdict, violations, citedClauses, requiresManagerApproval,
    #           requiresDirectorApproval, summary, requiresReview}
    complianceFindings: Optional[dict]

    # fraudFindings: structured verdict from Fraud Agent (Duplicate Check pattern)
    #   Shape: {verdict, flags, duplicateClaims, summary}
    fraudFindings: Optional[dict]

    # advisorDecision: final routing choice from Advisor Agent (Reflection + Routing)
    #   Values: "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
    advisorDecision: Optional[str]
