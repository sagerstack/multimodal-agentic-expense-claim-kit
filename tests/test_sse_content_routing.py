"""Regression tests for SSE content routing: AIMessage with content + tool_calls.

UAT Gap 1 Fix A: when on_chat_model_end fires with non-empty content AND tool_calls,
the content must be emitted as SseEvent.MESSAGE (chat bubble) BEFORE being appended
to thinkingEntries — not suppressed into the thinking panel.

TDD cycle: Task 1 writes failing tests (RED), Task 2 implements the fix (GREEN).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from agentic_claims.web.sseEvents import SseEvent
from agentic_claims.web.sseHelpers import runGraph
from agentic_claims.web.templating import templates

# ── helpers ──────────────────────────────────────────────────────────────────


def _makeLlmEndOutput(content="", toolCalls=None, reasoningContent=None):
    """Build a mock AIMessage-shaped output for on_chat_model_end events."""
    output = MagicMock(spec=AIMessage)
    output.content = content
    output.tool_calls = toolCalls or []
    additionalKwargs = {}
    if reasoningContent:
        additionalKwargs["reasoning_content"] = reasoningContent
    output.additional_kwargs = additionalKwargs
    output.response_metadata = {}
    output.usage_metadata = None
    return output


def _makeLlmEndEvent(content="", toolCalls=None, reasoningContent=None):
    """Return a full event dict shaped like {'event': 'on_chat_model_end', 'data': {...}}."""
    output = _makeLlmEndOutput(
        content=content, toolCalls=toolCalls, reasoningContent=reasoningContent
    )
    return {"event": "on_chat_model_end", "data": {"output": output}}


def _makeAskHumanToolCall():
    return {
        "name": "askHuman",
        "args": {"question": "Do the details look correct?"},
        "id": "call_1",
    }


def _makeMockGraph(events, stateNext=None, stateTasks=None):
    """Create a mock graph yielding given events with optional state."""
    graph = MagicMock()

    async def astreamEvents(invokeInput, config, version):
        for event in events:
            yield event

    graph.astream_events = astreamEvents

    stateResult = MagicMock()
    stateResult.next = stateNext or []
    stateResult.tasks = stateTasks or []
    stateResult.values = {"messages": []}
    graph.aget_state = AsyncMock(return_value=stateResult)

    return graph


def _makeMockRequest():
    request = MagicMock()
    request.session = {}

    async def isDisconnected():
        return False

    request.is_disconnected = isDisconnected
    return request


def _baseGraphInput():
    return {
        "threadId": "test-thread-routing",
        "claimId": "test-claim-routing",
        "message": "Here is my receipt",
        "hasImage": False,
        "isResume": False,
    }


async def _collectEvents(graph, graphInput=None, request=None):
    events = []
    async for event in runGraph(
        graph,
        graphInput or _baseGraphInput(),
        request or _makeMockRequest(),
        templates,
    ):
        events.append(event)
    return events


MARKDOWN_TABLE = (
    "| Field | Value |\n"
    "|---|---|\n"
    "| Merchant | Kopitiam |\n"
    "| Date | 2026-04-12 |\n"
    "| Amount | SGD 12.50 |"
)


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contentPlusToolCallsEmitsMessageBubble():
    """AIMessage with markdown table + tool_call must emit SseEvent.MESSAGE bubble.

    RED: fails on current code because hasToolCalls branch never emits MESSAGE.
    """
    events = [
        _makeLlmEndEvent(
            content=MARKDOWN_TABLE,
            toolCalls=[_makeAskHumanToolCall()],
        )
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(messageEvents) >= 1, (
        f"Expected at least one SseEvent.MESSAGE but got none. "
        f"Events yielded: {[e.event for e in collected]}"
    )
    # Must contain the merchant text from the table
    messageHtml = " ".join(e.raw_data for e in messageEvents)
    assert "Kopitiam" in messageHtml, f"MESSAGE bubble missing 'Kopitiam'. Got: {messageHtml[:200]}"

    # MESSAGE must appear before any STEP_CONTENT event from the same turn
    eventTypes = [e.event for e in collected]
    lastMsgIdx = max(i for i, e in enumerate(collected) if e.event == SseEvent.MESSAGE)
    stepContentIndices = [i for i, e in enumerate(collected) if e.event == SseEvent.STEP_CONTENT]
    if stepContentIndices:
        firstStepContent = min(stepContentIndices)
        assert lastMsgIdx < firstStepContent, (
            f"MESSAGE ({lastMsgIdx}) must come before STEP_CONTENT ({firstStepContent}). "
            f"Full order: {eventTypes}"
        )


@pytest.mark.asyncio
async def test_contentPlusToolCallsShortFillerNotPromoted():
    """Short filler ('Ok.') with tool_call must NOT produce a chat bubble.

    GREEN on current code (existing behaviour preserved).
    After the fix, this must still pass — filler stays in thinking panel.
    """
    events = [
        _makeLlmEndEvent(
            content="Ok.",
            toolCalls=[_makeAskHumanToolCall()],
        )
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    # No MESSAGE event should arise from the "Ok." content
    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    # NOTE: a MESSAGE may be emitted at end-of-stream from finalResponse if
    # non-empty. Since the only LLM event above is the tool-calls one, finalResponse
    # is "" so no end-of-stream bubble fires. Any MESSAGE here is a false promotion.
    messageContents = [e.raw_data for e in messageEvents]
    okMessages = [c for c in messageContents if "Ok." in c]
    assert len(okMessages) == 0, (
        f"Short filler 'Ok.' must not be promoted to a bubble. "
        f"Got MESSAGE events: {messageContents}"
    )


@pytest.mark.asyncio
async def test_contentPlusToolCallsStripsToolCallJson():
    """Content containing a leaking tool-call JSON fragment must be stripped before emission.

    RED: fails on current code because no MESSAGE is emitted at all.
    After fix: MESSAGE is emitted with the json fragment removed.
    """
    leaky_content = (
        "Here are the extracted receipt details.\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Merchant | Kopitiam |\n"
        '```json\n{"name": "askHuman", "arguments": {"question": "confirm?"}}\n```'
    )
    events = [
        _makeLlmEndEvent(
            content=leaky_content,
            toolCalls=[_makeAskHumanToolCall()],
        )
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(messageEvents) >= 1, (
        "Expected MESSAGE bubble for content with tool-call JSON fragment."
    )
    messageHtml = " ".join(e.raw_data for e in messageEvents)
    # The raw tool-call JSON must be stripped
    assert "askHuman" not in messageHtml or "Kopitiam" in messageHtml, (
        "Emitted MESSAGE should not contain raw 'askHuman' JSON fragment. "
        f"Got: {messageHtml[:300]}"
    )
    # Actually stricter: verify the json fence is gone
    assert '{"name":' not in messageHtml and '"arguments"' not in messageHtml, (
        f"Tool-call JSON leaked into MESSAGE: {messageHtml[:300]}"
    )


@pytest.mark.asyncio
async def test_reasoningContentStillRoutesToThinkingPanel():
    """Private reasoning_content must flow to thinking panel; content flows to bubble.

    RED: fails because no MESSAGE bubble is emitted for content+tool_calls.
    After fix: MESSAGE has the prose; private reasoning (when streamed) goes to thinking panel.

    Note: reasoningBuffer is populated from on_chat_model_stream chunks (L905-916), not
    from the end event's output.additional_kwargs. To exercise STEP_CONTENT we include a
    stream chunk with reasoning_content in additional_kwargs.
    """
    reasoning = "internal chain-of-thought about the extraction"
    reasoningChunk = MagicMock()
    reasoningChunk.content = ""
    reasoningChunk.additional_kwargs = {"reasoning_content": reasoning}
    reasoningChunk.response_metadata = {}

    events = [
        # Stream chunk populates reasoningBuffer
        {"event": "on_chat_model_stream", "data": {"chunk": reasoningChunk}},
        # End event: markdown table content + tool_call
        _makeLlmEndEvent(
            content=MARKDOWN_TABLE,
            toolCalls=[_makeAskHumanToolCall()],
            reasoningContent=reasoning,
        ),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    # The content must appear as a MESSAGE bubble
    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(messageEvents) >= 1, (
        "Expected MESSAGE bubble for content+tool_calls even with reasoning."
    )

    messageHtml = " ".join(e.raw_data for e in messageEvents)
    assert "Kopitiam" in messageHtml, f"MESSAGE missing content. Got: {messageHtml[:200]}"

    # Private reasoning must NOT be duplicated into the chat bubble
    assert reasoning not in messageHtml, (
        f"Private reasoning_content leaked into chat bubble: {reasoning[:50]}"
    )

    # A STEP_CONTENT event should carry the reasoning preview (emitted from reasoningBuffer)
    stepContent = [e for e in collected if e.event == SseEvent.STEP_CONTENT]
    assert len(stepContent) >= 1, "Expected STEP_CONTENT event with reasoning preview."


@pytest.mark.asyncio
async def test_noToolCallsPathUnchanged():
    """When tool_calls is empty, existing end-of-stream MESSAGE behavior is preserved.

    GREEN on current code (guard against double-emission regression).
    NOTE: avoid the word "submitted" — BUG-013 guard detects it as hallucinated
    submission when no submitClaim tool was called.
    """
    longContent = "Your expense report looks good. All fields are filled in correctly."
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(
            content=longContent, additional_kwargs={}, response_metadata={}
        )}},
        _makeLlmEndEvent(content=longContent, toolCalls=[]),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    # Exactly one MESSAGE at end-of-stream (from finalResponse path)
    assert len(messageEvents) == 1, (
        f"No-tool-calls path must yield exactly 1 MESSAGE. Got {len(messageEvents)}."
    )
    assert "expense report" in messageEvents[0].raw_data, (
        f"MESSAGE must contain the response content. Got: {messageEvents[0].raw_data[:200]}"
    )


@pytest.mark.asyncio
async def test_suppressedContentLogsEventForObservability():
    """Suppressed filler with tool_calls must emit sse.content_suppressed_as_reasoning log.

    RED: fails on current code because the suppression logEvent does not exist.
    After fix: logEvent is called with the correct event name and kwargs.
    """
    with patch("agentic_claims.web.sseHelpers.logEvent") as mockLogEvent:
        events = [
            _makeLlmEndEvent(
                content="Ok.",
                toolCalls=[_makeAskHumanToolCall()],
            )
        ]
        graph = _makeMockGraph(events)
        collected = await _collectEvents(graph)

        # No MESSAGE bubble for filler
        messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
        messageContents = [e.raw_data for e in messageEvents]
        okMessages = [c for c in messageContents if "Ok." in c]
        assert len(okMessages) == 0, "Filler must not produce a MESSAGE bubble."

        # Suppression logEvent must have been called
        suppCalls = [
            call
            for call in mockLogEvent.call_args_list
            if len(call.args) >= 2 and call.args[1] == "sse.content_suppressed_as_reasoning"
        ]
        allCallNames = [
            c.args[1] for c in mockLogEvent.call_args_list if len(c.args) >= 2
        ]
        assert len(suppCalls) >= 1, (
            f"Expected logEvent('sse.content_suppressed_as_reasoning') to be called. "
            f"All logEvent calls: {allCallNames}"
        )

        # Verify contentLength and preview kwargs
        suppCall = suppCalls[0]
        callKwargs = suppCall.kwargs
        assert callKwargs.get("contentLength") == 3, (
            f"contentLength should be 3 (len of 'Ok.'). Got: {callKwargs.get('contentLength')}"
        )
        preview = callKwargs.get("preview", "")
        assert "Ok." in preview, (
            f"preview should contain 'Ok.'. Got: {preview!r}"
        )
