"""ClaimState definition with Annotated reducers for LangGraph."""

from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from agentic_claims.agents.intake_gpt.state import IntakeGptState


def _unionSet(existing: set | None, update: set | None) -> set:
    """Reducer for Annotated set fields: merges two sets by union.

    Called by LangGraph when a node returns a partial state update that
    includes a field annotated with this reducer. Either arg may be None
    (first write / empty update).

    Pattern reference: docs/deep-research-langgraph-react-node.md
    (state-driven routing with accumulating collections).
    """
    a = existing or set()
    b = update or set()
    return a | b


class ClaimState(TypedDict):
    """State for the expense claim workflow.

    This is the shared state passed between all agent nodes in the LangGraph.
    Phase 1 intentionally keeps it minimal - future phases will expand with
    receipt data, findings, policy results, etc.

    # Phase 13 additions per:
    #   - 13-RESEARCH.md Section 3 "State Shape and Reducers"
    #   - 13-CONTEXT.md "Hook architecture — directive injection" decision
    #
    # Note: ROADMAP Criterion 5 "phase field" is satisfied by the boolean-flag
    # decomposition (clarificationPending + askHumanCount + unsupportedCurrencies)
    # per CONTEXT.md "Hook architecture" decision. A single phase enum was
    # rejected in favour of composable flags.
    """

    claimId: str
    status: str
    messages: Annotated[list[AnyMessage], add_messages]

    # Phase 2.1: Intake Agent conversation fields
    extractedReceipt: Optional[dict]  # VLM extraction output with fields + confidence
    violations: Optional[list[dict]]  # Policy violations with cited clauses
    currencyConversion: Optional[dict]  # Original and converted amounts
    claimSubmitted: Optional[bool]  # Gate flag for routing to compliance/fraud
    claimNumber: Optional[str]  # Claim number returned by submitClaim (e.g. CLAIM-003)

    # Phase 2.2: Agent observations (mismatches, overrides, red flags) for downstream agents and reviewer audit trail
    intakeFindings: Optional[dict]

    # Phase 8: Post-submission agent findings
    complianceFindings: Optional[dict]  # Structured compliance verdict from compliance agent
    fraudFindings: Optional[dict]  # Structured fraud verdict from fraud agent
    advisorDecision: Optional[str]  # One of "auto_approve" | "return_to_claimant" | "escalate_to_reviewer"
    dbClaimId: Optional[int]  # Integer DB primary key from submitClaim, used by post-submission agents
    intakeGpt: Optional[IntakeGptState]  # Nested state for the intake-gpt replacement path

    # Phase 13: routing / loop-bound / validator state (source: 13-RESEARCH.md §3)
    askHumanCount: int  # loop-bound counter; incremented per askHuman interrupt
    unsupportedCurrencies: Annotated[set[str], _unionSet]  # additive across turns
    clarificationPending: bool  # set by post-tool flag setter when user input is required
    validatorRetryCount: int  # soft-rewrite attempts this turn
    validatorEscalate: bool  # postModelHook → outer router signal
    turnIndex: int  # per-turn correlation counter for log events

    # Phase 1 confirmation gate (Issue 2, screenshot #6):
    # Set when extractReceiptFields returns; cleared when the user answers the
    # step-9 confirmation askHuman ("Do the details above look correct?").
    # While True, preModelHook injects a directive forcing the model's next tool
    # call to be askHuman — preventing the jump straight to searchPolicies.
    phase1ConfirmationPending: bool
