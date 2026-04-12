"""Tests for Intake Agent ReAct loop.

Phase 13 update (Plan 13-06): intakeNode now invokes the create_react_agent
subgraph via _getIntakeSubgraph rather than calling getIntakeAgent directly.
Tests that exercise intakeNode patch _getIntakeSubgraph to return a mock
subgraph whose ainvoke returns controlled test data.

Tests that verify getIntakeAgent itself (LLM construction, tool count, model
config) are unchanged — getIntakeAgent remains a public factory.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_claims.agents.intake.node import getIntakeAgent, intakeNode
from agentic_claims.core.state import ClaimState


# ---------------------------------------------------------------------------
# Helper: build a mock subgraph that returns a given ainvoke payload.
# Patches both _getIntakeSubgraph and _buildLlmAndTools so no real
# settings / HTTP clients are constructed during intakeNode execution.
# ---------------------------------------------------------------------------

def _mockSubgraph(ainvokeResult: dict) -> AsyncMock:
    """Return an AsyncMock whose ainvoke returns ainvokeResult."""
    mockSub = AsyncMock()
    mockSub.ainvoke = AsyncMock(return_value=ainvokeResult)
    return mockSub


def _patchIntakeNode(ainvokeResult: dict):
    """Context manager pair for patching intakeNode's subgraph path.

    Returns a context manager that patches:
      - _buildLlmAndTools → (MagicMock(), [])   (avoids real LLM construction)
      - _getIntakeSubgraph → mock subgraph        (returns ainvokeResult)
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        mockLlm = MagicMock()
        mockSubgraph = _mockSubgraph(ainvokeResult)
        with patch("agentic_claims.agents.intake.node._buildLlmAndTools", return_value=(mockLlm, [])):
            with patch("agentic_claims.agents.intake.node._getIntakeSubgraph", return_value=mockSubgraph):
                yield mockSubgraph

    return _ctx()


# ---------------------------------------------------------------------------
# getIntakeAgent — factory-level tests (unchanged from pre-Phase-13)
# ---------------------------------------------------------------------------

def test_getIntakeAgentReturnsCompiledGraph():
    """Verify getIntakeAgent returns a compiled graph with ainvoke method."""
    agent = getIntakeAgent()

    assert hasattr(agent, "ainvoke"), "Agent should have ainvoke method"
    assert callable(agent.ainvoke), "ainvoke should be callable"


def test_intakeAgentHasSixTools():
    """Verify the ReAct agent has all 6 domain tools registered."""
    with patch("agentic_claims.agents.intake.node.create_react_agent") as mockCreateAgent:
        mockAgent = MagicMock()
        mockCreateAgent.return_value = mockAgent

        getIntakeAgent()

        assert mockCreateAgent.called, "create_react_agent should be called"

        callArgs = mockCreateAgent.call_args
        tools = callArgs.kwargs.get("tools", [])

        assert len(tools) == 6, f"Expected 6 tools, got {len(tools)}"

        toolNames = [tool.name for tool in tools]
        expectedTools = [
            "getClaimSchema",
            "extractReceiptFields",
            "searchPolicies",
            "convertCurrency",
            "submitClaim",
            "askHuman",
        ]
        for expectedTool in expectedTools:
            assert expectedTool in toolNames, f"Tool {expectedTool} missing from agent"


def test_intakeAgentUsesOpenRouterModel():
    """Verify ChatOpenRouter is configured with OpenRouter API key."""
    with patch("agentic_claims.agents.intake.node.ChatOpenRouter") as mockChatOpenRouter:
        mockLlm = MagicMock()
        mockChatOpenRouter.return_value = mockLlm

        with patch("agentic_claims.agents.intake.node.create_react_agent") as mockCreateAgent:
            mockAgent = MagicMock()
            mockCreateAgent.return_value = mockAgent

            getIntakeAgent()

            assert mockChatOpenRouter.called, "ChatOpenRouter should be instantiated"
            callArgs = mockChatOpenRouter.call_args

            assert "openrouter_api_key" in callArgs.kwargs, "openrouter_api_key should be set"
            assert "base_url" not in callArgs.kwargs, "base_url should not be passed to ChatOpenRouter"


# ---------------------------------------------------------------------------
# intakeNode — subgraph-path tests (Phase 13 update: patch _getIntakeSubgraph)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_intakeNodeReturnsMessagesUpdate():
    """Verify intakeNode returns state dict with messages."""
    agentMessages = [
        HumanMessage(content="User message"),
        AIMessage(content="Agent response"),
    ]
    ainvokeResult = {"messages": agentMessages}

    with _patchIntakeNode(ainvokeResult) as mockSubgraph:
        state: ClaimState = {
            "claimId": "test-001",
            "status": "draft",
            "messages": [HumanMessage(content="User message")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert isinstance(result, dict), "Result should be a dict"
        assert "messages" in result, "Result should contain messages"
        assert isinstance(result["messages"], list), "Messages should be a list"

        mockSubgraph.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_intakeNodeSetsClaimSubmittedOnSuccessfulSubmitClaim():
    """Verify intakeNode sets claimSubmitted=True when submitClaim tool succeeds."""
    submitResult = json.dumps({"claim": {"id": 1}, "receipt": {"id": 2}})
    agentMessages = [
        HumanMessage(content="Submit my claim"),
        AIMessage(content="Submitting..."),
        ToolMessage(
            content=submitResult,
            name="submitClaim",
            tool_call_id="call_123",
        ),
        AIMessage(content="Your claim has been submitted."),
    ]
    ainvokeResult = {"messages": agentMessages}

    with _patchIntakeNode(ainvokeResult):
        state: ClaimState = {
            "claimId": "test-002",
            "status": "draft",
            "messages": [HumanMessage(content="Submit my claim")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert result.get("claimSubmitted") is True, "claimSubmitted should be True after successful submitClaim"


@pytest.mark.asyncio
async def test_intakeNodeDoesNotSetClaimSubmittedOnError():
    """Verify intakeNode does NOT set claimSubmitted when submitClaim returns error."""
    errorResult = json.dumps({"error": "Connection failed"})
    agentMessages = [
        HumanMessage(content="Submit my claim"),
        ToolMessage(
            content=errorResult,
            name="submitClaim",
            tool_call_id="call_456",
        ),
        AIMessage(content="Submission failed."),
    ]
    ainvokeResult = {"messages": agentMessages}

    with _patchIntakeNode(ainvokeResult):
        state: ClaimState = {
            "claimId": "test-003",
            "status": "draft",
            "messages": [HumanMessage(content="Submit my claim")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert "claimSubmitted" not in result, "claimSubmitted should NOT be set when submitClaim returns error"


@pytest.mark.asyncio
async def test_intakeNodeClaimSubmittedNotSetWithoutSubmitClaim():
    """Verify claimSubmitted is not set when no submitClaim tool call in messages."""
    agentMessages = [
        HumanMessage(content="What is the meal limit?"),
        AIMessage(content="The meal limit is $50 per day."),
    ]
    ainvokeResult = {"messages": agentMessages}

    with _patchIntakeNode(ainvokeResult):
        state: ClaimState = {
            "claimId": "test-004",
            "status": "draft",
            "messages": [HumanMessage(content="What is the meal limit?")],
        }

        result = await intakeNode(state, RunnableConfig())

        assert "claimSubmitted" not in result, "claimSubmitted should NOT be set without submitClaim call"


@pytest.mark.asyncio
async def test_intakeNodeFlushesAuditBufferAfterSubmission():
    """intakeNode calls flushSteps after submitClaim succeeds so intake audit steps are persisted."""
    submitResult = json.dumps({
        "claim": {"id": 7, "claim_number": "CLAIM-007"},
        "receipt": {"id": 3},
    })
    agentMessages = [
        ToolMessage(
            content=submitResult,
            name="submitClaim",
            tool_call_id="call_flush_test",
        ),
        AIMessage(content="Claim submitted."),
    ]
    ainvokeResult = {"messages": agentMessages}

    mockFlushSteps = AsyncMock()

    with _patchIntakeNode(ainvokeResult):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            state: ClaimState = {
                "claimId": "session-uuid-001",
                "status": "draft",
                "messages": [HumanMessage(content="Submit")],
            }
            result = await intakeNode(state, RunnableConfig())

    mockFlushSteps.assert_called_once_with(
        sessionClaimId="session-uuid-001",
        dbClaimId=7,
    )
    assert result.get("claimSubmitted") is True


@pytest.mark.asyncio
async def test_intakeNodeWritesClaimSubmittedAuditEntry():
    """intakeNode writes a claim_submitted audit log entry after successful submission."""
    submitResult = json.dumps({
        "claim": {"id": 9, "claim_number": "CLAIM-009"},
        "receipt": {"id": 5},
    })
    agentMessages = [
        ToolMessage(
            content=submitResult,
            name="submitClaim",
            tool_call_id="call_audit_test",
        ),
        AIMessage(content="Claim submitted."),
    ]
    ainvokeResult = {"messages": agentMessages}

    mockFlushSteps = AsyncMock()
    mockLogIntakeStep = AsyncMock()

    with _patchIntakeNode(ainvokeResult):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            with patch("agentic_claims.agents.intake.node.logIntakeStep", mockLogIntakeStep):
                state: ClaimState = {
                    "claimId": "session-uuid-002",
                    "status": "draft",
                    "messages": [HumanMessage(content="Submit")],
                }
                result = await intakeNode(state, RunnableConfig())

    mockLogIntakeStep.assert_called_once()
    callKwargs = mockLogIntakeStep.call_args.kwargs
    assert callKwargs["claimId"] == 9
    assert callKwargs["action"] == "claim_submitted"


@pytest.mark.asyncio
async def test_intakeNodeWritesIntakeFindingsToState():
    """intakeNode writes intakeFindings to state from submitClaim result."""
    submitResult = json.dumps({
        "claim": {
            "id": 11,
            "claim_number": "CLAIM-011",
            "intake_findings": {"employeeId": "EMP-123", "violations": []},
        },
        "receipt": {"id": 6},
    })
    agentMessages = [
        ToolMessage(
            content=submitResult,
            name="submitClaim",
            tool_call_id="call_findings_test",
        ),
        AIMessage(content="Claim submitted."),
    ]
    ainvokeResult = {"messages": agentMessages}

    mockFlushSteps = AsyncMock()

    with _patchIntakeNode(ainvokeResult):
        with patch("agentic_claims.agents.intake.node.flushSteps", mockFlushSteps):
            state: ClaimState = {
                "claimId": "session-uuid-003",
                "status": "draft",
                "messages": [HumanMessage(content="Submit")],
            }
            result = await intakeNode(state, RunnableConfig())

    assert "intakeFindings" in result
    assert result["intakeFindings"].get("employeeId") == "EMP-123"


@pytest.mark.asyncio
async def test_intakeNodeBuffersPolicyCheckFromSearchPoliciesResult():
    """intakeNode buffers a policy_check audit step when searchPolicies ToolMessage is present."""
    policyResult = json.dumps({
        "results": [
            {"section": "Meals", "category": "meals", "score": 0.9}
        ]
    })
    agentMessages = [
        ToolMessage(
            content=policyResult,
            name="searchPolicies",
            tool_call_id="call_policy_test",
        ),
        AIMessage(content="Policy checked."),
    ]
    ainvokeResult = {"messages": agentMessages}

    mockBufferStep = MagicMock()

    with _patchIntakeNode(ainvokeResult):
        with patch("agentic_claims.agents.intake.node.bufferStep", mockBufferStep):
            state: ClaimState = {
                "claimId": "session-uuid-policy",
                "status": "draft",
                "messages": [HumanMessage(content="Check policy")],
            }
            await intakeNode(state, RunnableConfig())

    mockBufferStep.assert_called_once_with(
        sessionClaimId="session-uuid-policy",
        action="policy_check",
        details={
            "violations": [],
            "policyRefs": [{"section": "Meals", "category": "meals", "score": 0.9}],
            "compliant": True,
            "query": "intake policy check",
        },
    )


@pytest.mark.asyncio
async def test_intakeNodeBuffersReceiptUploadedAndAiExtractionFromExtractReceiptFields():
    """intakeNode buffers receipt_uploaded and ai_extraction when extractReceiptFields ToolMessage is present."""
    extractResult = json.dumps({
        "fields": {"merchant": "TestMart", "totalAmount": 50.0},
        "confidence": {"merchant": 0.95},
        "imagePath": "uploads/test-session.jpg",
    })
    agentMessages = [
        ToolMessage(
            content=extractResult,
            name="extractReceiptFields",
            tool_call_id="call_extract_test",
        ),
        AIMessage(content="Extracted receipt."),
    ]
    ainvokeResult = {"messages": agentMessages}

    bufferedCalls = []
    mockBufferStep = MagicMock(side_effect=lambda **kwargs: bufferedCalls.append(kwargs))

    with _patchIntakeNode(ainvokeResult):
        with patch("agentic_claims.agents.intake.node.bufferStep", mockBufferStep):
            state: ClaimState = {
                "claimId": "session-uuid-extract",
                "status": "draft",
                "messages": [HumanMessage(content="Process receipt")],
            }
            result = await intakeNode(state, RunnableConfig())

    actions = [c["action"] for c in bufferedCalls]
    assert "receipt_uploaded" in actions
    assert "ai_extraction" in actions

    receiptStep = next(c for c in bufferedCalls if c["action"] == "receipt_uploaded")
    assert receiptStep["sessionClaimId"] == "session-uuid-extract"
    assert receiptStep["details"]["imagePath"] == "uploads/test-session.jpg"

    aiStep = next(c for c in bufferedCalls if c["action"] == "ai_extraction")
    assert aiStep["details"]["merchant"] == "TestMart"


# ---------------------------------------------------------------------------
# Phase 13: preIntakeValidator — outer pre-node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preIntakeValidatorIncrementsTurnIndex():
    """preIntakeValidator increments turnIndex by 1 and resets validatorRetryCount to 0."""
    from agentic_claims.agents.intake.node import preIntakeValidator

    state = {"claimId": "c1", "threadId": "t1", "turnIndex": 2, "messages": []}
    result = await preIntakeValidator(state)

    assert result.get("turnIndex") == 3
    # Reset validatorRetryCount at each turn start
    assert result.get("validatorRetryCount") == 0


@pytest.mark.asyncio
async def test_preIntakeValidatorStartsAtOneWhenTurnIndexAbsent():
    """preIntakeValidator initialises turnIndex to 1 when not present in state."""
    from agentic_claims.agents.intake.node import preIntakeValidator

    state = {"claimId": "c2", "threadId": "t2", "messages": []}
    result = await preIntakeValidator(state)

    assert result.get("turnIndex") == 1


# ---------------------------------------------------------------------------
# Phase 13: postIntakeRouter — conditional edge tests
# ---------------------------------------------------------------------------


def test_postIntakeRouterEscalatesOnValidatorEscalate():
    """validatorEscalate=True → postIntakeRouter returns 'humanEscalation'."""
    from agentic_claims.agents.intake.node import postIntakeRouter

    state = {"validatorEscalate": True, "askHumanCount": 0}
    assert postIntakeRouter(state) == "humanEscalation"


def test_postIntakeRouterEscalatesOnAskHumanCountExceeded():
    """askHumanCount > 3 (e.g. 4) → postIntakeRouter returns 'humanEscalation'."""
    from agentic_claims.agents.intake.node import postIntakeRouter

    state = {"validatorEscalate": False, "askHumanCount": 4}
    assert postIntakeRouter(state) == "humanEscalation"


def test_postIntakeRouterDoesNotEscalateAtExactlyThreeAskHuman():
    """Boundary: askHumanCount == 3 is strictly NOT an escalation (> 3 only)."""
    from agentic_claims.agents.intake.node import postIntakeRouter

    state = {"validatorEscalate": False, "askHumanCount": 3}
    assert postIntakeRouter(state) == "continue"


def test_postIntakeRouterContinuesOnNormalState():
    """No escalation signals → postIntakeRouter returns 'continue'."""
    from agentic_claims.agents.intake.node import postIntakeRouter

    state = {"validatorEscalate": False, "askHumanCount": 1}
    assert postIntakeRouter(state) == "continue"


def test_postIntakeRouterValidatorEscalateTakesPrecedence():
    """validatorEscalate=True takes precedence over low askHumanCount."""
    from agentic_claims.agents.intake.node import postIntakeRouter

    state = {"validatorEscalate": True, "askHumanCount": 0}
    assert postIntakeRouter(state) == "humanEscalation"


# ---------------------------------------------------------------------------
# Phase 13: buildIntakeSubgraph — wiring smoke test
# ---------------------------------------------------------------------------


def test_buildIntakeSubgraphUsesV5PromptAndNoCheckpointer():
    """buildIntakeSubgraph wires v5 prompt, checkpointer=None, version='v2', and both hooks."""
    from unittest.mock import MagicMock, patch

    from agentic_claims.agents.intake.node import buildIntakeSubgraph

    mockLlm = MagicMock()
    mockTools = []
    with patch("agentic_claims.agents.intake.node.create_react_agent") as mockFactory:
        mockFactory.return_value = MagicMock()
        buildIntakeSubgraph(mockLlm, mockTools)

        assert mockFactory.called
        kwargs = mockFactory.call_args.kwargs
        # Outer graph owns checkpointer — inner subgraph must have None
        assert kwargs.get("checkpointer") is None
        # v2 required for post_model_hook support
        assert kwargs.get("version") == "v2"
        # v5 prompt (routing stripped)
        from agentic_claims.agents.intake.prompts.agentSystemPrompt_v5 import (
            INTAKE_AGENT_SYSTEM_PROMPT_V5,
        )
        assert kwargs.get("prompt") is INTAKE_AGENT_SYSTEM_PROMPT_V5
        # Hooks wired
        assert kwargs.get("pre_model_hook") is not None
        assert kwargs.get("post_model_hook") is not None


# ---------------------------------------------------------------------------
# Phase 13: _mergeSubgraphResult — pure function tests
# ---------------------------------------------------------------------------


def test_mergeSubgraphResultPropagatesAllPhase13Flags():
    """All five Phase 13 flag fields are copied from subgraph result to merged output."""
    from agentic_claims.agents.intake.node import _mergeSubgraphResult

    state = {"messages": [], "askHumanCount": 0}
    result = {
        "messages": [],
        "validatorEscalate": True,
        "clarificationPending": True,
        "validatorRetryCount": 2,
        "askHumanCount": 4,
        "unsupportedCurrencies": {"VND"},
    }
    merged = _mergeSubgraphResult(state, result)

    assert merged.get("validatorEscalate") is True
    assert merged.get("clarificationPending") is True
    assert merged.get("validatorRetryCount") == 2
    assert merged.get("askHumanCount") == 4
    assert merged.get("unsupportedCurrencies") == {"VND"}


def test_mergeSubgraphResultOmitsAbsentKeys():
    """Keys absent from subgraph result must be absent from merged (no defaulting)."""
    from agentic_claims.agents.intake.node import _mergeSubgraphResult

    state = {"messages": [], "askHumanCount": 0, "validatorEscalate": False}
    result = {"messages": []}
    merged = _mergeSubgraphResult(state, result)

    # Phase 13 flag keys not in result must not appear in merged
    assert "validatorEscalate" not in merged
    assert "clarificationPending" not in merged
    assert "askHumanCount" not in merged
    assert "unsupportedCurrencies" not in merged


def test_mergeSubgraphResultMessagesAreDeltaOnly():
    """Messages in merged are only NEW messages (delta from prior count), not the full list."""
    from agentic_claims.agents.intake.node import _mergeSubgraphResult
    from langchain_core.messages import AIMessage, HumanMessage

    priorMessages = [HumanMessage(content="Upload receipt")]
    newMessage = AIMessage(content="Got it")
    state = {"messages": priorMessages}
    result = {"messages": priorMessages + [newMessage]}

    merged = _mergeSubgraphResult(state, result)

    # Only the new AIMessage should appear — not the prior HumanMessage
    assert merged.get("messages") == [newMessage]


# ---------------------------------------------------------------------------
# Phase 13: end-to-end integration — flag propagation through _mergeSubgraphResult
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preIntakeValidatorThroughIntakeNodeThroughPostIntakeRouterPropagatesFlags():
    """Integration: preIntakeValidator → intakeNode (mocked subgraph) → postIntakeRouter.

    Verifies that flags set by the mocked subgraph result flow through
    _mergeSubgraphResult and are visible to the outer postIntakeRouter.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from agentic_claims.agents.intake.node import (
        intakeNode,
        postIntakeRouter,
        preIntakeValidator,
    )

    # Subgraph returns validatorEscalate=True to trigger escalation path
    mockedSubgraphResult = {
        "messages": [],
        "validatorEscalate": True,
        "clarificationPending": True,
        "askHumanCount": 2,
    }

    mockSubgraph = MagicMock()
    mockSubgraph.ainvoke = AsyncMock(return_value=mockedSubgraphResult)

    initialState = {
        "claimId": "c-int-1",
        "threadId": "t-int-1",
        "messages": [],
        "turnIndex": 0,
        "askHumanCount": 0,
        "unsupportedCurrencies": set(),
        "status": "draft",
    }

    # Step 1: preIntakeValidator
    preUpdates = await preIntakeValidator(initialState)
    stateAfterPre = {**initialState, **preUpdates}

    # Step 2: intakeNode with mocked subgraph — patch both LLM construction and
    # subgraph singleton so no real settings/HTTP clients are needed
    with (
        patch("agentic_claims.agents.intake.node._buildLlmAndTools", return_value=(MagicMock(), [])),
        patch("agentic_claims.agents.intake.node._getIntakeSubgraph", return_value=mockSubgraph),
    ):
        intakeUpdates = await intakeNode(stateAfterPre, RunnableConfig())

    stateAfterIntake = {**stateAfterPre, **intakeUpdates}

    # Step 3: flags set by subgraph must be visible in the merged outer state
    assert stateAfterIntake.get("validatorEscalate") is True, (
        f"validatorEscalate must propagate through _mergeSubgraphResult. "
        f"intakeUpdates keys: {list(intakeUpdates.keys())}"
    )
    assert stateAfterIntake.get("clarificationPending") is True
    # askHumanCount must be >= 2 (subgraph set 2; postToolFlagSetter may increment further)
    assert stateAfterIntake.get("askHumanCount", 0) >= 2

    # Step 4: postIntakeRouter routes to humanEscalation on validatorEscalate
    branch = postIntakeRouter(stateAfterIntake)
    assert branch == "humanEscalation"


# ---------------------------------------------------------------------------
# Phase 13: humanEscalationNode — MCP call unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_humanEscalationNodeCallsUpdateClaimStatusMcp():
    """humanEscalationNode calls updateClaimStatus MCP with correct URL and argument shape.

    Verifies Bug 4 / Warning 4 fix: the URL is read from settings.db_mcp_url
    (not hardcoded), and the MCP arguments carry claimId=dbClaimId,
    newStatus='escalated', actor='intake_agent'.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from agentic_claims.agents.intake.nodes.humanEscalation import humanEscalationNode

    mockDbMcpUrl = "http://mcp-db:8000/mcp/"
    mockSettings = MagicMock()
    mockSettings.db_mcp_url = mockDbMcpUrl

    state = {
        "claimId": "c-esc-1",
        "threadId": "t-esc-1",
        "dbClaimId": 42,
        "status": "draft",
        "validatorEscalate": True,
        "askHumanCount": 1,
        "unsupportedCurrencies": {"VND"},
        "messages": [],
        "intakeFindings": {},
    }

    with (
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.getSettings",
            return_value=mockSettings,
        ),
        patch(
            "agentic_claims.agents.intake.nodes.humanEscalation.mcpCallTool",
            new=AsyncMock(return_value={"ok": True}),
        ) as mockMcp,
    ):
        result = await humanEscalationNode(state)

    # MCP called exactly once
    assert mockMcp.call_count == 1
    callKwargs = mockMcp.call_args.kwargs
    # URL comes from settings.db_mcp_url (not hardcoded)
    assert callKwargs.get("serverUrl") == mockDbMcpUrl
    assert callKwargs.get("toolName") == "updateClaimStatus"
    args = callKwargs.get("arguments", {})
    assert args.get("claimId") == 42  # dbClaimId passed through
    assert args.get("newStatus") == "escalated"
    assert args.get("actor") == "intake_agent"

    # Terminal state fields
    assert result.get("status") == "escalated"
    assert result.get("claimSubmitted") is False
    # Terminal AIMessage contains the non-negotiable template
    assert any(
        "couldn't complete this automatically" in getattr(m, "content", "")
        for m in result.get("messages", [])
    )
    # escalationMetadata merged into intakeFindings
    findings = result.get("intakeFindings", {})
    assert "escalationMetadata" in findings
    assert findings["escalationMetadata"].get("askHumanCount") == 1
