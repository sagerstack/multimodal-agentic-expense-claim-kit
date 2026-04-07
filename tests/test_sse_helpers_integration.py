"""Integration tests for runGraph, interrupt detection, and template rendering."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_claims.web.sseEvents import SseEvent
from agentic_claims.web.sseHelpers import _extractSummaryData, runGraph
from agentic_claims.web.templating import templates


def _makeChunk(content="", additionalKwargs=None, responseMetadata=None):
    """Create a mock LLM chunk with content and optional reasoning."""
    chunk = MagicMock()
    chunk.content = content
    chunk.additional_kwargs = additionalKwargs or {}
    chunk.response_metadata = responseMetadata or {}
    return chunk


def _makeToolOutput(toolName, outputDict):
    """Create a mock output object for tool end events."""
    output = MagicMock()
    output.content = json.dumps(outputDict)
    return output


def _makeMockRequest(disconnectAfter=None):
    """Create a mock request with session and is_disconnected."""
    request = MagicMock()
    request.session = {}
    callCount = 0

    async def isDisconnected():
        nonlocal callCount
        callCount += 1
        if disconnectAfter is not None and callCount > disconnectAfter:
            return True
        return False

    request.is_disconnected = isDisconnected
    return request


def _makeMockGraph(events, stateNext=None, stateTasks=None, stateMessages=None):
    """Create a mock graph that yields given events and returns given state."""
    graph = MagicMock()

    async def astream(invokeInput, config, version):
        for event in events:
            yield event

    graph.astream_events = astream

    stateResult = MagicMock()
    stateResult.next = stateNext or []
    stateResult.tasks = stateTasks or []
    stateResult.values = {"messages": stateMessages or []}
    graph.aget_state = AsyncMock(return_value=stateResult)

    return graph


def _baseGraphInput():
    return {
        "threadId": "test-thread",
        "claimId": "test-claim",
        "message": "Hello",
        "hasImage": False,
        "isResume": False,
    }


async def _collectEvents(graph, graphInput, request):
    events = []
    async for event in runGraph(graph, graphInput, request, templates):
        events.append(event)
    return events


# ── runGraph event sequence tests ──


@pytest.mark.asyncio
async def testRunGraphYieldsThinkingStartFirst():
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Hi")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    assert collected[0].event == SseEvent.THINKING_START


@pytest.mark.asyncio
async def testRunGraphYieldsTokenEvents(monkeypatch):
    """TOKEN events are only emitted when enable_response_streaming is True."""
    from agentic_claims.core.config import getSettings
    realSettings = getSettings()
    realSettings.enable_response_streaming = True
    monkeypatch.setattr("agentic_claims.web.sseHelpers.getSettings", lambda: realSettings)

    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Hello")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk(" world")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    tokenEvents = [e for e in collected if e.event == SseEvent.TOKEN]
    assert len(tokenEvents) == 2
    assert tokenEvents[0].raw_data == "Hello"
    assert tokenEvents[1].raw_data == " world"


@pytest.mark.asyncio
async def testRunGraphYieldsStepNameOnToolStart():
    events = [
        {"event": "on_tool_start", "name": "extractReceiptFields", "data": {}},
        {
            "event": "on_tool_end",
            "name": "extractReceiptFields",
            "data": {"output": json.dumps({"fields": {"merchant": "Test"}})},
        },
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    stepNames = [e for e in collected if e.event == SseEvent.STEP_NAME]
    assert any("Extracting receipt fields" in e.raw_data for e in stepNames)


@pytest.mark.asyncio
async def testRunGraphYieldsThinkingDoneSummary():
    events = [
        {"event": "on_tool_start", "name": "searchPolicies", "data": {}},
        {
            "event": "on_tool_end",
            "name": "searchPolicies",
            "data": {"output": json.dumps({"results": []})},
        },
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Done")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    doneEvents = [e for e in collected if e.event == SseEvent.THINKING_DONE]
    assert len(doneEvents) == 1
    assert "Thought for" in doneEvents[0].raw_data
    assert "1 tool" in doneEvents[0].raw_data


@pytest.mark.asyncio
async def testRunGraphYieldsMessageWithRenderedHtml():
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Here is your result")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    msgEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(msgEvents) == 1
    assert "bg-surface-container-low" in msgEvents[0].raw_data
    assert "Here is your result" in msgEvents[0].raw_data


@pytest.mark.asyncio
async def testRunGraphDetectsInterruptAndYieldsInterruptEvent():
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("thinking")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    interruptTask = MagicMock()
    interruptPayload = MagicMock()
    interruptPayload.value = {"question": "Please confirm the amount"}
    interruptTask.interrupts = [interruptPayload]

    graph = _makeMockGraph(events, stateNext=["intake"], stateTasks=[interruptTask])
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    interruptEvents = [e for e in collected if e.event == SseEvent.INTERRUPT]
    assert len(interruptEvents) == 1
    assert "confirm the amount" in interruptEvents[0].raw_data
    assert request.session["awaiting_clarification"] is True


@pytest.mark.asyncio
async def testRunGraphDoesNotYieldMessageOnInterrupt():
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("response")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    interruptTask = MagicMock()
    interruptPayload = MagicMock()
    interruptPayload.value = {"question": "Confirm?"}
    interruptTask.interrupts = [interruptPayload]

    graph = _makeMockGraph(events, stateNext=["intake"], stateTasks=[interruptTask])
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    msgEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(msgEvents) == 0


@pytest.mark.asyncio
async def testRunGraphLastEventIsMessage():
    """runGraph ends with MESSAGE event (DONE is added by the chat router)."""
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Hi")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    graph = _makeMockGraph(events)
    request = _makeMockRequest()
    collected = await _collectEvents(graph, _baseGraphInput(), request)
    assert collected[-1].event == SseEvent.MESSAGE


# ── _extractSummaryData tests ──


def testExtractSummaryDataFromReceiptTool():
    entries = [
        {
            "type": "tool",
            "name": "extractReceiptFields",
            "elapsed": 1.0,
            "output": json.dumps(
                {
                    "fields": {
                        "merchant": "Starbucks",
                        "totalAmount": "4.50",
                        "currency": "SGD",
                        "category": "meals",
                    }
                }
            ),
        }
    ]
    result = _extractSummaryData(entries)
    assert result is not None
    assert result["totalAmount"] == "SGD 4.50"
    assert result["topCategory"] == "meals"
    assert result["itemCount"] == 1
    assert result["batchItems"][0]["merchant"] == "Starbucks"


def testExtractSummaryDataReturnsNoneForEmpty():
    assert _extractSummaryData([]) is None


# ── Disconnect handling ──


@pytest.mark.asyncio
async def testRunGraphBreaksOnDisconnect(monkeypatch):
    """Disconnected run should have fewer events when streaming is enabled."""
    from agentic_claims.core.config import getSettings
    realSettings = getSettings()
    realSettings.enable_response_streaming = True
    monkeypatch.setattr("agentic_claims.web.sseHelpers.getSettings", lambda: realSettings)

    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("token1")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("token2")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("token3")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("token4")}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("token5")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]
    # Disconnect after 1 is_disconnected call — should stop mid-stream
    disconnectedRequest = _makeMockRequest(disconnectAfter=1)
    disconnectedGraph = _makeMockGraph(events)
    collected = await _collectEvents(disconnectedGraph, _baseGraphInput(), disconnectedRequest)

    fullRequest = _makeMockRequest()
    fullGraph = _makeMockGraph(events)
    fullCollected = await _collectEvents(fullGraph, _baseGraphInput(), fullRequest)

    # Disconnected run should have fewer events (no full token stream + no MESSAGE)
    assert len(collected) < len(fullCollected)


# ── BUG-016 tests ──


@pytest.mark.asyncio
async def testRunGraphIntakeResponseNotOverwrittenByAdvisor():
    """BUG-016: advisor LLM output after submitClaim must NOT overwrite the intake response."""
    from unittest.mock import patch

    submitOutput = json.dumps({"claim": {"id": 42, "claim_number": "CLM-042"}, "receipt": {}})

    events = [
        # Intake agent: tool call then clean summary
        {"event": "on_tool_start", "name": "submitClaim", "data": {}},
        {"event": "on_tool_end", "name": "submitClaim", "data": {"output": submitOutput}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Your claim CLM-042 has been submitted.")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
        # Advisor agent: raw JSON leaks as subsequent LLM generation
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk('{"decision": "escalate", "reasoning": "over limit"}')}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]

    stateValues = {"messages": [], "claimSubmitted": True}
    graph = _makeMockGraph(events)
    graph.aget_state.return_value.values = stateValues

    dbClaims = [
        {
            "merchant": "Test",
            "receipt_date": "2026-04-05",
            "total_amount": "42.00",
            "currency": "SGD",
            "status": "pending",
            "created_at": "2026-04-05 10:00",
            "claim_number": "CLM-042",
        }
    ]

    request = _makeMockRequest()
    with patch(
        "agentic_claims.web.sseHelpers.fetchClaimsForTable",
        new=AsyncMock(return_value=dbClaims),
    ):
        collected = await _collectEvents(graph, _baseGraphInput(), request)

    msgEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(msgEvents) == 1
    # The rendered message must contain the intake summary, not the advisor JSON
    assert "CLM-042 has been submitted" in msgEvents[0].raw_data
    assert '"decision"' not in msgEvents[0].raw_data


@pytest.mark.asyncio
async def testRunGraphFinalTableUpdateEmittedAfterAdvisorStatusChange():
    """BUG-016: a TABLE_UPDATE is emitted after the graph loop if advisor changed claim status."""
    from unittest.mock import patch

    submitOutput = json.dumps({"claim": {"id": 7, "claim_number": "CLM-007"}, "receipt": {}})

    events = [
        {"event": "on_tool_start", "name": "submitClaim", "data": {}},
        {"event": "on_tool_end", "name": "submitClaim", "data": {"output": submitOutput}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Claim submitted.")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
    ]

    # Graph state after advisor ran: status is now "escalated"
    stateValues = {"messages": [], "claimSubmitted": True, "status": "escalated"}
    graph = _makeMockGraph(events)
    graph.aget_state.return_value.values = stateValues

    dbClaims = [
        {
            "merchant": "Test Merchant",
            "receipt_date": "2026-04-05",
            "total_amount": "120.00",
            "currency": "SGD",
            "status": "escalated",
            "created_at": "2026-04-05 10:00",
            "claim_number": "CLM-007",
        }
    ]

    request = _makeMockRequest()
    with patch(
        "agentic_claims.web.sseHelpers.fetchClaimsForTable",
        new=AsyncMock(return_value=dbClaims),
    ):
        collected = await _collectEvents(graph, _baseGraphInput(), request)

    tableEvents = [e for e in collected if e.event == SseEvent.TABLE_UPDATE]
    # At least one TABLE_UPDATE must have the final advisor status (CSS uppercase renders it;
    # HTML source uses title case "Escalated" from the 8-state badge template)
    assert any("Escalated" in e.raw_data or "escalated" in e.raw_data for e in tableEvents)


# ── BUG-026/027/029 early termination tests ──


@pytest.mark.asyncio
async def testRunGraphSetsBackgroundTaskWhenClaimSubmitted():
    """BUG-026/029: after submitClaim, backgroundTask must be set on request.state."""
    from unittest.mock import patch

    submitOutput = json.dumps({"claim": {"id": 55, "claim_number": "CLM-055"}, "receipt": {}})

    events = [
        {"event": "on_tool_start", "name": "submitClaim", "data": {}},
        {"event": "on_tool_end", "name": "submitClaim", "data": {"output": submitOutput}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Claim CLM-055 submitted.")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
        # Simulate intakeNode completing and evaluatorGate routing to postSubmission
        {"event": "on_chain_start", "name": "postSubmission", "data": {}},
    ]

    stateValues = {"messages": [], "claimSubmitted": True}
    graph = _makeMockGraph(events)
    graph.aget_state.return_value.values = stateValues

    dbClaims = [
        {
            "merchant": "Test",
            "receipt_date": "2026-04-07",
            "total_amount": "55.00",
            "currency": "SGD",
            "status": "pending",
            "created_at": "2026-04-07 10:00",
            "claim_number": "CLM-055",
        }
    ]

    request = _makeMockRequest()
    with patch(
        "agentic_claims.web.sseHelpers.fetchClaimsForTable",
        new=AsyncMock(return_value=dbClaims),
    ):
        collected = await _collectEvents(graph, _baseGraphInput(), request)

    # Background task must be set on request.state
    assert hasattr(request.state, "backgroundTask")
    bgTask = request.state.backgroundTask
    assert bgTask is not None
    assert bgTask["threadId"] == "test-thread"
    assert bgTask["claimId"] == "test-claim"


@pytest.mark.asyncio
async def testRunGraphSuppressesTokensAfterClaimSubmitted():
    """BUG-027/029: tokens after submitClaim completes must not be emitted as SSE TOKEN events."""
    from unittest.mock import patch

    submitOutput = json.dumps({"claim": {"id": 56, "claim_number": "CLM-056"}, "receipt": {}})

    events = [
        {"event": "on_tool_start", "name": "submitClaim", "data": {}},
        {"event": "on_tool_end", "name": "submitClaim", "data": {"output": submitOutput}},
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("Submitted.")}},
        {"event": "on_chat_model_end", "data": {"output": MagicMock(tool_calls=None)}},
        # Post-submission intakeNode cleanup would generate more tokens — must be suppressed
        {"event": "on_chat_model_stream", "data": {"chunk": _makeChunk("extra post-submission token")}},
        {"event": "on_chain_start", "name": "postSubmission", "data": {}},
    ]

    stateValues = {"messages": [], "claimSubmitted": True}
    graph = _makeMockGraph(events)
    graph.aget_state.return_value.values = stateValues

    request = _makeMockRequest()
    with patch(
        "agentic_claims.web.sseHelpers.fetchClaimsForTable",
        new=AsyncMock(return_value=[]),
    ):
        from agentic_claims.core.config import getSettings
        realSettings = getSettings()
        realSettings.enable_response_streaming = True
        with patch("agentic_claims.web.sseHelpers.getSettings", lambda: realSettings):
            collected = await _collectEvents(graph, _baseGraphInput(), request)

    tokenEvents = [e for e in collected if e.event == SseEvent.TOKEN]
    # "extra post-submission token" must not appear
    assert not any("extra post-submission" in e.raw_data for e in tokenEvents)
