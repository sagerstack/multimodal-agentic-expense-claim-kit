"""Intake agent node - wrapper graph + create_react_agent subgraph (Phase 13).

Architecture (Phase 13 hybrid routing):
  Outer StateGraph (this module):
    preIntakeValidator → intakeSubgraph (create_react_agent) → postIntakeRouter
      ├─ humanEscalation (terminal)
      └─ evaluatorGate (main graph's existing routing)

  The create_react_agent subgraph carries:
    - v5 system prompt (routing stripped, descriptive only)
    - preModelHook: ephemeral directive injection via llm_input_messages
    - postModelHook: soft-rewrite validator with 1-retry escalation
    - NO checkpointer (outer graph's AsyncPostgresSaver owns persistence)

Sources:
  - 13-RESEARCH.md §2 (wrapper-graph pattern skeleton)
  - 13-RESEARCH.md §7 (checkpointer ownership — subgraph gets None)
  - 13-CONTEXT.md (hook architecture decisions)
"""

import json
import logging
import time
from typing import Annotated, Optional

import httpx
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_openrouter import ChatOpenRouter
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from typing_extensions import NotRequired, TypedDict

from agentic_claims.agents.intake.auditLogger import bufferStep, flushSteps, logIntakeStep
from agentic_claims.agents.intake.extractionContext import extractedReceiptVar
from agentic_claims.agents.intake.hooks import postModelHook, preModelHook
from agentic_claims.agents.intake.hooks.postToolFlagSetter import postToolFlagSetter
from agentic_claims.agents.intake.hooks.submitClaimGuard import submitClaimGuard
from agentic_claims.agents.intake.prompts.agentSystemPrompt_v6 import INTAKE_AGENT_SYSTEM_PROMPT_V6
from agentic_claims.agents.intake.tools.askHuman import askHuman
from agentic_claims.agents.intake.tools.convertCurrency import convertCurrency
from agentic_claims.agents.intake.tools.extractReceiptFields import extractReceiptFields
from agentic_claims.agents.intake.tools.getClaimSchema import getClaimSchema
from agentic_claims.agents.intake.tools.searchPolicies import searchPolicies
from agentic_claims.agents.intake.tools.submitClaim import submitClaim
from agentic_claims.core.config import getSettings
from agentic_claims.core.logging import logEvent
from agentic_claims.core.state import ClaimState, _unionSet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IntakeSubgraphState — inner schema for create_react_agent subgraph
# ---------------------------------------------------------------------------

class IntakeSubgraphState(TypedDict):
    """Inner state schema for the create_react_agent subgraph.

    Shares the Phase 13 flag field NAMES with ClaimState so that the
    subgraph's updates propagate back to outer state via LangGraph
    subgraph state merging (13-RESEARCH.md §2 Risk 1 mitigation).

    Notes:
    - remaining_steps is required by create_react_agent internals (source L539).
    - claimId / threadId / turnIndex are read-only correlation fields; inner
      hooks read them but do not write them back.
    - phase field is intentionally absent: 13-02 chose boolean-flag
      decomposition (clarificationPending + askHumanCount + unsupportedCurrencies)
      over a single phase enum.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: NotRequired[int]
    # Phase 13 flag fields — present in BOTH schemas for subgraph → outer merge
    unsupportedCurrencies: Annotated[set[str], _unionSet]
    clarificationPending: NotRequired[bool]
    validatorRetryCount: NotRequired[int]
    validatorEscalate: NotRequired[bool]
    askHumanCount: NotRequired[int]
    # Phase 1 confirmation gate + submission state. preModelHook reads these
    # to decide whether to inject the "ask for confirmation" directive.
    # Without them on this schema LangGraph filters the keys out of the
    # subgraph state, so the directive never fires across turns.
    # Source: CLAIM-022 regression (Vietnamese receipt) — phase1ConfirmationPending
    # was set in outer state but never reached preModelHook inside the subgraph.
    phase1ConfirmationPending: NotRequired[bool]
    claimSubmitted: NotRequired[bool]
    # Read-only correlation fields (hooks read, outer graph writes)
    claimId: NotRequired[str]
    threadId: NotRequired[str]
    turnIndex: NotRequired[int]


# ---------------------------------------------------------------------------
# buildIntakeSubgraph — inner subgraph factory
# ---------------------------------------------------------------------------

def buildIntakeSubgraph(llm, tools):
    """Build the create_react_agent subgraph with Phase 13 hooks.

    Per 13-RESEARCH.md §7: NO checkpointer on the inner subgraph.
    The outer graph's AsyncPostgresSaver owns all persistence.

    Per 13-RESEARCH.md §2: pre_model_hook uses llm_input_messages
    (ephemeral channel, never writes state.messages); post_model_hook
    uses RemoveMessage soft-rewrite with 1-retry bound.
    """
    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=INTAKE_AGENT_SYSTEM_PROMPT_V6,
        state_schema=IntakeSubgraphState,
        pre_model_hook=preModelHook,
        post_model_hook=postModelHook,
        version="v2",
        name="intakeSubgraph",
        checkpointer=None,  # outer graph owns checkpointer per §7
    )


_intakeSubgraphSingleton = None


def _getIntakeSubgraph(llm, tools):
    """Return a module-level singleton subgraph (built once, reused per process).

    Note: singleton is keyed on module lifetime; if llm/tools change between
    calls (e.g. fallback model switch), the singleton is NOT rebuilt.
    Task 1a registers it; intakeNode wires it in Task 1b.
    """
    global _intakeSubgraphSingleton
    if _intakeSubgraphSingleton is None:
        _intakeSubgraphSingleton = buildIntakeSubgraph(llm, tools)
    return _intakeSubgraphSingleton


# ---------------------------------------------------------------------------
# LLM + tools factory (shared by getIntakeAgent and buildIntakeSubgraph)
# ---------------------------------------------------------------------------

def _buildLlmAndTools(useFallback: bool = False):
    """Construct the ChatOpenRouter LLM and tool list.

    Separated so both getIntakeAgent (legacy/test-facing) and
    _getIntakeSubgraph (Phase 13 production path) share the same
    construction logic.

    Args:
        useFallback: If True, use fallback LLM model instead of primary.

    Returns:
        Tuple of (llm, tools)
    """
    settings = getSettings()
    modelName = settings.openrouter_fallback_model_llm if useFallback else settings.openrouter_model_llm

    llm = ChatOpenRouter(
        model=modelName,
        openrouter_api_key=settings.openrouter_api_key,
        temperature=settings.openrouter_llm_temperature,
        max_retries=settings.openrouter_max_retries,
        max_tokens=settings.openrouter_llm_max_tokens,
    )

    # Bypass SSL verification (Zscaler corporate proxy workaround)
    llm.client.sdk_configuration.client = httpx.Client(verify=False, follow_redirects=True)
    llm.client.sdk_configuration.async_client = httpx.AsyncClient(verify=False, follow_redirects=True)

    tools = [
        getClaimSchema,
        extractReceiptFields,
        searchPolicies,
        convertCurrency,
        submitClaim,
        askHuman,
    ]

    return llm, tools


def getIntakeAgent(useFallback: bool = False):
    """Create and return the compiled ReAct agent for intake processing.

    Phase 13 note: production intake traffic flows through buildIntakeSubgraph
    (Phase 13 hooks wired). This function is retained for:
      - Backward-compatible tests that patch create_react_agent via this path.
      - Legacy callers that may reference getIntakeAgent directly.

    Args:
        useFallback: If True, use fallback LLM model instead of primary

    Returns:
        Compiled ReAct agent graph
    """
    llm, tools = _buildLlmAndTools(useFallback=useFallback)

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=INTAKE_AGENT_SYSTEM_PROMPT_V6,
    )

    return agent


# ---------------------------------------------------------------------------
# _mergeSubgraphResult — authoritative result → outer state translator
# ---------------------------------------------------------------------------

# Whitelist of keys that may flow from subgraph result to outer ClaimState.
# Keys NOT in this set are silently dropped (prevents internal create_react_agent
# bookkeeping — remaining_steps, etc. — from polluting outer state).
_SUBGRAPH_PROPAGATE_KEYS = frozenset({
    # Phase 13 flag fields
    "validatorEscalate",
    "clarificationPending",
    "validatorRetryCount",
    "askHumanCount",
    "unsupportedCurrencies",
    # Existing domain fields populated by the tool-scan logic below
    "claimSubmitted",
    "extractedReceipt",
    "currencyConversion",
    "intakeFindings",
    "status",
    "dbClaimId",
    "claimNumber",
    "violations",
})


def _mergeSubgraphResult(state: dict, result: dict) -> dict:
    """Propagate a whitelisted subset of subgraph result back to outer ClaimState.

    Messages form: delta (slice from prior count onward). Chosen so the
    outer add_messages reducer appends only the NEW messages generated this
    turn. The full list is written from the subgraph result; we take the
    suffix starting at len(state["messages"]) to get only new messages.

    Invariants:
    - Never writes a key not in _SUBGRAPH_PROPAGATE_KEYS.
    - Keys absent from result are omitted entirely (outer state unchanged).
    - Pure function: no I/O, no logEvent calls, no global mutation.
      May be called from unit tests directly.

    See Plan 13-06 Task 1b for authoritative whitelist and semantics.
    """
    merged: dict = {}

    # messages — delta form
    resultMessages = result.get("messages")
    if resultMessages is not None:
        priorCount = len(state.get("messages") or [])
        newMessages = list(resultMessages)[priorCount:]
        if newMessages:
            merged["messages"] = newMessages

    # All other whitelisted keys: copy only if present in result
    for key in _SUBGRAPH_PROPAGATE_KEYS:
        if key in result:
            merged[key] = result[key]

    return merged


# ---------------------------------------------------------------------------
# _scanToolMessages — domain-field extraction from ToolMessages
# ---------------------------------------------------------------------------

async def _scanToolMessages(state: dict, result: dict, merged: dict) -> None:
    """Scan ToolMessages in result and populate domain fields in merged.

    Extracts: claimSubmitted, claimNumber, dbClaimId, extractedReceipt,
    currencyConversion, violations, intakeFindings — exactly preserving
    the logic from the pre-Phase-13 intakeNode tool-scan loop.

    Mutates merged in-place.
    """
    for msg in result.get("messages", []):
        if not (hasattr(msg, "name") and hasattr(msg, "content")):
            continue
        try:
            content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            if not isinstance(content, dict) or "error" in content:
                continue

            if msg.name == "submitClaim":
                merged["claimSubmitted"] = True
                claimRecord = content.get("claim", {})
                claimNumber = claimRecord.get("claim_number")
                if claimNumber:
                    merged["claimNumber"] = claimNumber
                dbClaimId = claimRecord.get("id")
                if dbClaimId is not None:
                    try:
                        parsedDbClaimId = int(dbClaimId)
                        merged["dbClaimId"] = parsedDbClaimId
                        sessionClaimId = state.get("claimId", "")
                        await flushSteps(sessionClaimId=sessionClaimId, dbClaimId=parsedDbClaimId)
                        await logIntakeStep(
                            claimId=parsedDbClaimId,
                            action="claim_submitted",
                            details={"claimNumber": claimNumber, "status": "pending"},
                        )
                        intakeFindingsFromDb = claimRecord.get("intake_findings")
                        if intakeFindingsFromDb and isinstance(intakeFindingsFromDb, dict):
                            merged["intakeFindings"] = intakeFindingsFromDb
                    except (TypeError, ValueError):
                        pass
            elif msg.name == "extractReceiptFields":
                merged["extractedReceipt"] = content
                extractedReceiptVar.set(content)
                sessionClaimId = state.get("claimId", "")
                if sessionClaimId:
                    fields = content.get("fields", {})
                    confidence = content.get("confidence", {})
                    imagePath = content.get("imagePath")
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="receipt_uploaded",
                        details={"imagePath": imagePath},
                    )
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="ai_extraction",
                        details={
                            "confidence": confidence,
                            "merchant": fields.get("merchant"),
                            "amount": fields.get("totalAmount"),
                            "fields": fields,
                        },
                    )
            elif msg.name == "convertCurrency":
                merged["currencyConversion"] = content
            elif msg.name == "searchPolicies":
                results = content.get("results", content.get("policies", []))
                if isinstance(results, list):
                    merged["violations"] = results
                else:
                    merged["violations"] = []
                sessionClaimId = state.get("claimId", "")
                if sessionClaimId:
                    policyRefs = [
                        {"section": r.get("section"), "category": r.get("category"), "score": r.get("score")}
                        for r in (results if isinstance(results, list) else [])
                        if isinstance(r, dict)
                    ]
                    bufferStep(
                        sessionClaimId=sessionClaimId,
                        action="policy_check",
                        details={
                            "violations": [],
                            "policyRefs": policyRefs,
                            "compliant": True,
                            "query": "intake policy check",
                        },
                    )
        except (json.JSONDecodeError, TypeError):
            pass

    if "violations" not in merged:
        merged["violations"] = []


# ---------------------------------------------------------------------------
# preIntakeValidator — outer pre-node (runs BEFORE intake subgraph)
# ---------------------------------------------------------------------------

async def preIntakeValidator(state: ClaimState) -> dict:
    """Outer pre-node. Runs BEFORE entering the intake subgraph.

    Responsibilities:
    - Increments turnIndex for log correlation
    - Resets validatorRetryCount at the start of each turn
    - Runs postToolFlagSetter on current state (catches flags from the
      previous turn's tool results that the outer graph needs)
    - Runs submitClaimGuard on current state
    """
    claimId = state.get("claimId")
    threadId = state.get("threadId")
    turnIndex = int(state.get("turnIndex", 0)) + 1

    logEvent(
        logger,
        "intake.turn.start",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        message="preIntakeValidator: turn start",
    )

    updates: dict = {"turnIndex": turnIndex, "validatorRetryCount": 0}

    flagUpdates = await postToolFlagSetter(state)
    updates.update(flagUpdates)

    guardUpdates = await submitClaimGuard(state)
    updates.update(guardUpdates)

    return updates


# ---------------------------------------------------------------------------
# postIntakeRouter — conditional edge after intake subgraph
# ---------------------------------------------------------------------------

def postIntakeRouter(state: ClaimState) -> str:
    """Conditional edge after the intake subgraph returns.

    Returns one of:
      - "humanEscalation": explicit validator escalate OR loop-bound exceeded
      - "continue": fall-through to evaluatorGate

    Precedence: explicit escalate signal takes priority over loop-bound check.
    Boundary: askHumanCount == 3 is NOT an escalation (strictly > 3).
    """
    claimId = state.get("claimId")
    threadId = state.get("threadId")

    if state.get("validatorEscalate"):
        logEvent(
            logger,
            "intake.router.decision",
            logCategory="routing",
            agent="intake",
            claimId=claimId,
            threadId=threadId,
            branch="humanEscalation",
            reason="validatorEscalate",
            message="postIntakeRouter: routing to humanEscalation (validatorEscalate=True)",
        )
        return "humanEscalation"

    if int(state.get("askHumanCount", 0)) > 3:
        logEvent(
            logger,
            "intake.router.decision",
            logCategory="routing",
            agent="intake",
            claimId=claimId,
            threadId=threadId,
            branch="humanEscalation",
            reason="askHumanCount_exceeded",
            message="postIntakeRouter: routing to humanEscalation (askHumanCount > 3)",
        )
        return "humanEscalation"

    logEvent(
        logger,
        "intake.router.decision",
        logCategory="routing",
        agent="intake",
        claimId=claimId,
        threadId=threadId,
        branch="continue",
        reason="no_escalation",
        message="postIntakeRouter: fall-through to evaluatorGate",
    )
    return "continue"


# ---------------------------------------------------------------------------
# intakeNode — outer wrapper node (Phase 13 production path)
# ---------------------------------------------------------------------------

async def intakeNode(state: ClaimState, config: RunnableConfig) -> dict:
    """Outer intake node: invoke create_react_agent subgraph, merge result.

    Phase 13 wrapper responsibilities (outer graph-owned):
      - Invoke the create_react_agent subgraph with Phase 13 hooks
      - Merge the result back to outer state via _mergeSubgraphResult
      - Scan ToolMessages for domain-field extraction (claimSubmitted, etc.)
      - Run postToolFlagSetter + submitClaimGuard on the merged state
        so the outer postIntakeRouter sees flags set by THIS turn's tools
      - Emit intake.turn.end event

    Fallback: if the primary model returns a 402 error, the subgraph is
    rebuilt with the fallback model (singleton is bypassed for the retry).
    """
    nodeStart = time.time()
    claimId = state.get("claimId")
    threadId = state.get("threadId")
    turnIndex = state.get("turnIndex", 0)

    logEvent(
        logger,
        "intake.started",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        messageCount=len(state.get("messages", [])),
        message="intakeNode started",
    )

    settings = getSettings()

    # Build the primary LLM + tools
    llm, tools = _buildLlmAndTools(useFallback=False)
    subgraph = _getIntakeSubgraph(llm, tools)

    # Build subgraph input: pass Phase 13 flag fields + messages + correlation ids.
    # phase1ConfirmationPending MUST be passed so preModelHook (running inside the
    # subgraph) can inject the confirmation directive on every turn until the
    # user confirms. Source: CLAIM-022 regression — flag was set in outer state
    # but never reached the subgraph, so the directive never fired.
    subgraphInput = {
        "messages": state.get("messages", []),
        "claimId": claimId,
        "threadId": threadId,
        "turnIndex": turnIndex,
        "askHumanCount": state.get("askHumanCount", 0),
        "clarificationPending": state.get("clarificationPending", False),
        "validatorRetryCount": state.get("validatorRetryCount", 0),
        "validatorEscalate": state.get("validatorEscalate", False),
        "unsupportedCurrencies": state.get("unsupportedCurrencies") or set(),
        "phase1ConfirmationPending": state.get("phase1ConfirmationPending", False),
        "claimSubmitted": state.get("claimSubmitted", False),
    }

    logEvent(
        logger,
        "intake.agent_invoked",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        message="intakeNode: invoking subgraph",
    )

    # Invoke subgraph with 402 fallback retry
    try:
        result = await subgraph.ainvoke(subgraphInput, config=config)
    except Exception as e:
        errorStr = str(e)
        if "402" in errorStr or "credits" in errorStr.lower() or "quota" in errorStr.lower():
            logEvent(
                logger,
                "intake.llm_402_fallback",
                level=logging.WARNING,
                logCategory="agent",
                agent="intake",
                claimId=claimId,
                model=settings.openrouter_model_llm,
                fallbackModel=settings.openrouter_fallback_model_llm,
                error=errorStr,
                message="Primary LLM returned 402 — falling back to secondary model",
            )
            fallbackLlm, fallbackTools = _buildLlmAndTools(useFallback=True)
            fallbackSubgraph = buildIntakeSubgraph(fallbackLlm, fallbackTools)
            result = await fallbackSubgraph.ainvoke(subgraphInput, config=config)
        else:
            raise

    # Merge Phase 13 flag fields + messages from subgraph result
    merged = _mergeSubgraphResult(state, result)

    # Scan ToolMessages for domain-field extraction
    await _scanToolMessages(state, result, merged)

    # Run post-subgraph hooks on the virtual "post-turn" state so the outer
    # postIntakeRouter sees flags set by THIS turn's tools.
    # scanMode="full-delta": the merged["messages"] suffix is *this turn's delta*
    # only, so a full scan is turn-scoped. The trailing scan in the default
    # (preIntakeValidator) path misses tools followed by an AIMessage, which
    # qwen3 emits routinely (e.g. JSON content after extractReceiptFields).
    # Source: 13-DEBUG-phase1-skip.md Issue 2 (CLAIM-022 regression).
    postSubgraphState = {**state, **merged}
    flagUpdates = await postToolFlagSetter(postSubgraphState, scanMode="full-delta")
    merged.update(flagUpdates)

    guardUpdates = await submitClaimGuard(postSubgraphState)
    merged.update(guardUpdates)

    logEvent(
        logger,
        "intake.completed",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        elapsed=f"{time.time() - nodeStart:.2f}s",
        stateUpdateKeys=list(merged.keys()),
        message="intakeNode completed",
    )

    logEvent(
        logger,
        "intake.turn.end",
        logCategory="agent",
        agent="intake",
        claimId=claimId,
        threadId=threadId,
        turnIndex=turnIndex,
        message="intakeNode: turn end",
    )

    return merged
