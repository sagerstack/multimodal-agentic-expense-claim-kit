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


def _makeSettings(*, intakeAgentMode="legacy", enableResponseStreaming=False):
    settings = MagicMock()
    settings.intake_agent_mode = intakeAgentMode
    settings.enable_response_streaming = enableResponseStreaming
    return settings


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


@pytest.mark.asyncio
async def test_llmCompletionLogsReasoningSummaryMetadataForIntakeGpt():
    """LLM completion log should capture reasoning-summary presence and length."""
    reasoning = "concise reasoning summary"
    reasoningChunk = MagicMock()
    reasoningChunk.content = ""
    reasoningChunk.additional_kwargs = {"reasoning_content": reasoning}
    reasoningChunk.response_metadata = {}

    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": reasoningChunk}},
        _makeLlmEndEvent(content="Hello there", toolCalls=[]),
    ]
    graph = _makeMockGraph(events)

    with (
        patch("agentic_claims.web.sseHelpers.logEvent") as mockLogEvent,
        patch(
            "agentic_claims.web.sseHelpers.getSettings",
            return_value=_makeSettings(intakeAgentMode="gpt"),
        ),
    ):
        await _collectEvents(graph)

    completedCalls = [
        call
        for call in mockLogEvent.call_args_list
        if len(call.args) >= 2 and call.args[1] == "llm.call_completed"
    ]
    assert completedCalls, "Expected llm.call_completed log event."

    completedKwargs = completedCalls[0].kwargs
    assert completedKwargs.get("agent") == "intake-gpt"
    assert completedKwargs.get("hasReasoningSummary") is True
    assert completedKwargs.get("reasoningLength") == len(reasoning)
    assert completedKwargs.get("reasoningContent") == reasoning


@pytest.mark.asyncio
async def test_fallbackThinkingSummaryLogsExplicitEventForIntakeGpt():
    """Direct no-tool turns should emit an explicit fallback-thinking log event."""
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(
            content="Hello there", additional_kwargs={}, response_metadata={}
        )}},
        _makeLlmEndEvent(content="Hello there", toolCalls=[]),
    ]
    graph = _makeMockGraph(events)

    with (
        patch("agentic_claims.web.sseHelpers.logEvent") as mockLogEvent,
        patch(
            "agentic_claims.web.sseHelpers.getSettings",
            return_value=_makeSettings(intakeAgentMode="gpt"),
        ),
    ):
        await _collectEvents(graph)

    fallbackCalls = [
        call
        for call in mockLogEvent.call_args_list
        if len(call.args) >= 2 and call.args[1] == "sse.fallback_thinking_summary_emitted"
    ]
    assert fallbackCalls, "Expected fallback thinking summary log event."

    fallbackKwargs = fallbackCalls[0].kwargs
    assert fallbackKwargs.get("agent") == "intake-gpt"
    assert fallbackKwargs.get("usedFallbackThinkingSummary") is True
    assert fallbackKwargs.get("hasReasoningSummary") is False
    assert fallbackKwargs.get("summary") == "Responding directly without tool calls."


@pytest.mark.asyncio
async def test_receiptUploadTranscriptRendersTableNotJsonLeak():
    """Receipt-upload transcript should show the table + interrupt, never the raw payload."""

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeTask:
        def __init__(self, interrupts):
            self.interrupts = interrupts

    fencedJson = (
        "```json\n"
        "{\n"
        '  "fields": {\n'
        '    "merchant": "DIG.",\n'
        '    "date": "2024-05-28",\n'
        '    "totalAmount": 16.2,\n'
        '    "currency": "USD"\n'
        "  },\n"
        '  "confidence": {\n'
        '    "merchant": 0.95,\n'
        '    "date": 0.92,\n'
        '    "totalAmount": 0.98,\n'
        '    "currency": 0.99\n'
        "  }\n"
        "}\n"
        "```"
    )
    interruptPayload = {
        "contextMessage": (
            "| Field | Value | Confidence |\n"
            "|---|---|---|\n"
            "| Merchant | DIG. | High |\n"
            "| Date | 2024-05-28 | High |\n"
            "| Total | USD 16.20 | High |\n"
            "| Currency | USD | High |\n"
            "\n\nTotal: USD 16.2 → SGD 20.64 (rate: 1.2739)"
        ),
        "question": "Does the extracted receipt information look correct?",
    }
    events = [
        _makeLlmEndEvent(
            content="",
            toolCalls=[
                {
                    "name": "extractReceiptFields",
                    "args": {"claimId": "claim-tx-001"},
                    "id": "call_extract",
                }
            ],
        ),
        {
            "event": "on_tool_start",
            "name": "extractReceiptFields",
            "data": {"input": {"claimId": "claim-tx-001"}},
        },
        _makeLlmEndEvent(content=fencedJson, toolCalls=[]),
    ]
    graph = _makeMockGraph(
        events,
        stateNext=["intake"],
        stateTasks=[FakeTask((FakeInterrupt(interruptPayload),))],
    )
    graphInput = {
        "threadId": "thread-tx-001",
        "claimId": "claim-tx-001",
        "message": "",
        "hasImage": True,
        "isResume": False,
    }

    collected = await _collectEvents(graph, graphInput=graphInput)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    messageHtml = " ".join(e.raw_data for e in messageEvents)
    interruptEvents = [e for e in collected if e.event == SseEvent.INTERRUPT]

    assert "| Field | Value | Confidence |" in messageHtml
    assert "DIG." in messageHtml
    assert "Does the extracted receipt information look correct?" == interruptEvents[-1].raw_data
    assert "```json" not in messageHtml
    assert '"fields"' not in messageHtml
    assert '"confidence"' not in messageHtml


@pytest.mark.asyncio
async def test_requestHumanInputDoesNotLeakIntoThinkingPanel():
    """Structured intake-gpt interrupt tool should be suppressed like askHuman."""
    events = [
        {"event": "on_tool_start", "name": "requestHumanInput", "data": {"input": {}}},
        {
            "event": "on_tool_end",
            "name": "requestHumanInput",
            "data": {"output": {"response": "yes"}},
        },
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    stepNames = [e.raw_data for e in collected if e.event == SseEvent.STEP_NAME]
    stepContents = [e.raw_data for e in collected if e.event == SseEvent.STEP_CONTENT]

    assert "Waiting for your input..." not in stepNames
    assert not any("Asked for clarification" in content for content in stepContents)


@pytest.mark.asyncio
async def test_contentDuringPendingToolCallsEmitsBubble():
    """Regression: Qwen3-class models split content+tool_call across separate
    on_chat_model_end events. When the prose-only end event fires while a
    prior tool is still counted as pending, the content must still emit a
    MESSAGE bubble — not be silently dropped by the pendingToolCalls>0 guard.

    Reproduces the bug where the extraction table never appeared in chat
    before the askHuman question (see 13-DEBUG-extraction-bubble-dropped).
    """
    events = [
        # Prior tool fires → pendingToolCalls becomes 1
        {
            "event": "on_tool_start",
            "name": "extractReceiptFields",
            "data": {"input": {}},
        },
        # Model emits user-facing prose WITHOUT tool_calls while pending > 0
        _makeLlmEndEvent(content=MARKDOWN_TABLE, toolCalls=[]),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(messageEvents) >= 1, (
        f"Content during pendingToolCalls>0 must emit MESSAGE bubble. "
        f"Events yielded: {[e.event for e in collected]}"
    )
    messageHtml = " ".join(e.raw_data for e in messageEvents)
    assert "Kopitiam" in messageHtml, (
        f"MESSAGE bubble missing table content. Got: {messageHtml[:300]}"
    )


@pytest.mark.asyncio
async def test_fencedJsonDuringPendingToolCallsDoesNotEmitBubble():
    """A fenced JSON payload during pendingToolCalls>0 must not render as chat."""
    fencedJson = (
        "```json\n"
        "{\n"
        '  "fields": {\n'
        '    "merchant": "DIG."\n'
        "  },\n"
        '  "confidence": {\n'
        '    "merchant": 0.95\n'
        "  }\n"
        "}\n"
        "```"
    )
    events = [
        {
            "event": "on_tool_start",
            "name": "extractReceiptFields",
            "data": {"input": {}},
        },
        _makeLlmEndEvent(content=fencedJson, toolCalls=[]),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert len(messageEvents) == 0, (
        f"Fenced JSON during pendingToolCalls>0 must not emit MESSAGE bubble. Got: {messageEvents}"
    )


@pytest.mark.asyncio
async def test_shortFillerDuringPendingToolCallsNotPromoted():
    """Counterpart to the above: short filler ('Ok.') during pendingToolCalls>0
    must NOT produce a bubble. Preserves the existing reasoning-panel behaviour
    for trivial acknowledgements.
    """
    events = [
        {
            "event": "on_tool_start",
            "name": "extractReceiptFields",
            "data": {"input": {}},
        },
        _makeLlmEndEvent(content="Ok.", toolCalls=[]),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    okMessages = [e.raw_data for e in messageEvents if "Ok." in e.raw_data]
    assert len(okMessages) == 0, (
        f"Short filler during pending must not emit a bubble. Got: {okMessages}"
    )


# ── Bug 1 (screenshot #7): raw JSON root content must not render as a bubble ──
# Source: 13-DEBUG-raw-json-bubble.md (CLAIM-018). `_stripToolCallJson` only
# strips ```json fenced blocks; qwen3 frequently emits bare JSON payloads
# while pendingToolCalls>0 which previously passed `_isUserFacingProse`
# (length >= 40 → True) and rendered as a raw dict in the main chat.


def test_isUserFacingProseRejectsJsonRootObject():
    """A bare JSON object (no ```json fence) must route to thinking, not bubble."""
    from agentic_claims.web.sseHelpers import _isUserFacingProse

    rawJson = '{"name": "searchPolicies", "arguments": {"query": "meals", "limit": 5}}'
    assert _isUserFacingProse(rawJson) is False, (
        "JSON-root content must NOT render as chat bubble"
    )


def test_isUserFacingProseRejectsJsonRootArray():
    """A bare JSON array also routes to thinking."""
    from agentic_claims.web.sseHelpers import _isUserFacingProse

    rawJson = '[{"name": "searchPolicies", "arguments": {}}]'
    assert _isUserFacingProse(rawJson) is False


def test_isUserFacingProseAllowsSentenceContainingBraces():
    """A real sentence that happens to contain '{' mid-line must still bubble.
    Only root-level JSON (parses cleanly) is rejected — inline braces are fine.
    """
    from agentic_claims.web.sseHelpers import _isUserFacingProse

    sentence = "The merchant field is {{MERCHANT}} — please confirm it matches."
    assert _isUserFacingProse(sentence) is True


def test_isUserFacingProseAllowsMarkdownTableWithPipes():
    """Regression guard: the markdown-table branch must still fire for
    well-formed extraction tables (not accidentally caught by the JSON check)."""
    from agentic_claims.web.sseHelpers import _isUserFacingProse

    table = "| Field | Value | Confidence |\n|---|---|---|\n| Merchant | X | High |"
    assert _isUserFacingProse(table) is True


def test_looksLikeJsonRootNegativeCases():
    """_looksLikeJsonRoot must not false-positive on non-JSON content."""
    from agentic_claims.web.sseHelpers import _looksLikeJsonRoot

    assert _looksLikeJsonRoot("") is False
    assert _looksLikeJsonRoot("Ready to submit this claim?") is False
    assert _looksLikeJsonRoot("{broken json") is False  # unparseable
    assert _looksLikeJsonRoot("Please review { the details } carefully.") is False


def test_isUserFacingProseRejectsPrettyPrintedPayloadLeak():
    """Pretty-printed object-like payloads must not route to the chat bubble."""
    from agentic_claims.web.sseHelpers import _isUserFacingProse

    payload = '{\n  "fields": {\n    "merchant": "DIG."\n  },\n  "confidence": {\n    "merchant": 0.95\n  }\n}'
    assert _isUserFacingProse(payload) is False


# ── Bug 1 follow-up (CLAIM-020): JSON prefix + trailing prose ────────────────
# Original fix rejected content that parsed fully as JSON. CLAIM-020 showed the
# model emits `{json dump}\n\nAnalysis Complete\n| table |...` — JSON prefix
# with trailing prose. _stripToolCallJson now consumes the JSON prefix via
# raw_decode so the prose survives and the JSON dump doesn't reach the bubble.


def test_stripToolCallJsonRemovesLeadingJsonObject():
    """`{"fields": {...}}\\nAnalysis Complete\\n...` → only the prose remains."""
    from agentic_claims.web.sseHelpers import _stripToolCallJson

    payload = (
        '{"fields": {"merchant": "X", "totalAmount": 727.09}, '
        '"confidence": {"merchant": 0.95}}\n\n'
        "Analysis Complete\n| Field | Value |"
    )
    cleaned = _stripToolCallJson(payload)
    assert "fields" not in cleaned
    assert "confidence" not in cleaned
    assert "Analysis Complete" in cleaned
    assert "| Field | Value |" in cleaned


def test_stripToolCallJsonPreservesBareProse():
    """Prose that doesn't start with { or [ passes through unchanged."""
    from agentic_claims.web.sseHelpers import _stripToolCallJson

    prose = "Policy check: Your meals expense is within the per-person cap."
    assert _stripToolCallJson(prose) == prose


def test_stripToolCallJsonHandlesPureJsonDump():
    """If the whole content is JSON, return empty (no prose to keep)."""
    from agentic_claims.web.sseHelpers import _stripToolCallJson

    payload = '{"fields": {"merchant": "X"}}'
    assert _stripToolCallJson(payload) == ""


def test_stripToolCallJsonHandlesPureFencedJsonDump():
    """A fenced JSON payload with no trailing prose should strip to empty."""
    from agentic_claims.web.sseHelpers import _stripToolCallJson

    payload = '```json\n{\n  "fields": {"merchant": "DIG."},\n  "confidence": {"merchant": 0.95}\n}\n```'
    assert _stripToolCallJson(payload) == ""


# ── Issue A (CLAIM-020): askHuman(...) prose leak stripping ──────────────────


def test_stripToolCallExpressionsRemovesAskHumanLeak():
    """The literal `askHuman("...")` leaked in the analysis bubble must be
    stripped. Structured tool_calls still go through LangGraph intact — only
    the prose copy is removed."""
    from agentic_claims.web.sseHelpers import _stripToolCallExpressions

    text = (
        "Analysis Complete\n"
        "| Field | Value |\n"
        "| Merchant | X |\n\n"
        'askHuman("Do the details above look correct? Let me know if anything needs correcting.")'
    )
    cleaned = _stripToolCallExpressions(text)
    assert "askHuman" not in cleaned
    assert "Do the details above look correct" not in cleaned
    assert "Analysis Complete" in cleaned
    assert "| Merchant | X |" in cleaned


def test_stripToolCallExpressionsHandlesMultipleTools():
    """Multiple tool-call expressions on different lines all get stripped."""
    from agentic_claims.web.sseHelpers import _stripToolCallExpressions

    text = (
        'Step 1: askHuman("rate?")\n'
        "Step 2: something\n"
        'Step 3: submitClaim(claimData={"x": 1}, receiptData={})'
    )
    cleaned = _stripToolCallExpressions(text)
    assert "askHuman" not in cleaned
    assert "submitClaim" not in cleaned
    assert "rate?" not in cleaned
    assert "Step 2: something" in cleaned


def test_stripToolCallExpressionsHandlesNestedParens():
    """Nested parens inside the call args don't confuse the depth scanner."""
    from agentic_claims.web.sseHelpers import _stripToolCallExpressions

    text = 'Summary.\n\naskHuman("Rate (to SGD) please?")\nTail prose.'
    cleaned = _stripToolCallExpressions(text)
    assert "askHuman" not in cleaned
    assert "Summary." in cleaned
    assert "Tail prose." in cleaned


def test_stripToolCallExpressionsLeavesUnrelatedTextAlone():
    """Prose mentioning 'ask' in plain language (not as a call) survives."""
    from agentic_claims.web.sseHelpers import _stripToolCallExpressions

    text = "I will ask you to confirm the details shortly."
    assert _stripToolCallExpressions(text) == text


@pytest.mark.asyncio
async def test_structuredInterruptPayloadEmitsContextBubbleBeforeInterrupt():
    """Structured interrupt payload should render context in chat and question in interrupt."""

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeTask:
        def __init__(self, interrupts):
            self.interrupts = interrupts

    payload = {
        "contextMessage": "Policy summary complete. I need one more input.",
        "question": "Please confirm whether you want to proceed.",
    }
    graph = _makeMockGraph(
        events=[],
        stateNext=["intake"],
        stateTasks=[FakeTask((FakeInterrupt(payload),))],
    )

    collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    interruptEvents = [e for e in collected if e.event == SseEvent.INTERRUPT]

    assert messageEvents, "Expected a MESSAGE bubble for contextMessage"
    assert interruptEvents, "Expected an INTERRUPT event for question"
    assert "Policy summary complete" in " ".join(e.raw_data for e in messageEvents)
    assert interruptEvents[-1].raw_data == "Please confirm whether you want to proceed."


@pytest.mark.asyncio
async def test_intakeGptFieldConfirmationSuppressesDuplicateProseBubble():
    """If intake-gpt emits prose alongside requestHumanInput(field_confirmation),
    the prose must be suppressed so only the structured interrupt payload renders.
    """

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeTask:
        def __init__(self, interrupts):
            self.interrupts = interrupts

    duplicateProse = (
        "I've extracted the following details from your receipt:\n\n"
        "Merchant: SERVUS GERMAN BURGER GRILL\n"
        "Date: 2025-03-27\n"
        "Total Amount: SGD 727.09\n"
        "Please confirm if this information is accurate."
    )
    fieldConfirmationCall = {
        "name": "requestHumanInput",
        "args": {
            "kind": "field_confirmation",
            "blockingStep": "field_confirmation",
            "question": "Do the extracted receipt details look correct to you?",
            "contextMessage": (
                "| Field | Value | Confidence |\n"
                "|---|---|---|\n"
                "| Merchant | SERVUS GERMAN BURGER GRILL | High |"
            ),
        },
        "id": "call_field_confirmation",
    }
    payload = {
        "kind": "field_confirmation",
        "contextMessage": fieldConfirmationCall["args"]["contextMessage"],
        "question": fieldConfirmationCall["args"]["question"],
    }
    graph = _makeMockGraph(
        events=[_makeLlmEndEvent(content=duplicateProse, toolCalls=[fieldConfirmationCall])],
        stateNext=["intake"],
        stateTasks=[FakeTask((FakeInterrupt(payload),))],
    )
    graphInput = dict(_baseGraphInput())
    graphInput["hasImage"] = True

    with patch("agentic_claims.web.sseHelpers.getSettings", return_value=_makeSettings(intakeAgentMode="gpt")):
        collected = await _collectEvents(graph, graphInput=graphInput)

    messageEvents = [e.raw_data for e in collected if e.event == SseEvent.MESSAGE]
    interruptEvents = [e.raw_data for e in collected if e.event == SseEvent.INTERRUPT]

    assert any("| Merchant | SERVUS GERMAN BURGER GRILL | High |" in html for html in messageEvents)
    assert all("I've extracted the following details from your receipt" not in html for html in messageEvents)
    assert interruptEvents[-1] == "Do the extracted receipt details look correct to you?"


@pytest.mark.asyncio
async def test_plainDirectResponseEmitsFallbackThinkingSummary():
    """Direct no-tool turns should not leave the Thinking panel body empty."""
    events = [
        _makeLlmEndEvent(content="Hello! How can I assist you today?"),
    ]
    graph = _makeMockGraph(events)
    collected = await _collectEvents(graph)

    stepContentEvents = [e for e in collected if e.event == SseEvent.STEP_CONTENT]
    assert stepContentEvents, "Expected at least one STEP_CONTENT event for direct reply"
    assert any(
        "Responding directly without tool calls." in e.raw_data for e in stepContentEvents
    ), "Fallback direct-response thinking summary should be emitted"


@pytest.mark.asyncio
async def test_finalResponseStructuredPayloadIsSuppressed():
    """Final fallback render must not emit a raw structured payload bubble."""
    payload = '{\n  "fields": {\n    "merchant": "DIG."\n  },\n  "confidence": {\n    "merchant": 0.95\n  }\n}'
    events = [
        {"event": "on_chat_model_stream", "data": {"chunk": MagicMock(
            content=payload, additional_kwargs={}, response_metadata={}
        )}},
        _makeLlmEndEvent(content=payload, toolCalls=[]),
    ]
    graph = _makeMockGraph(events)

    with patch("agentic_claims.web.sseHelpers.logEvent") as mockLogEvent:
        collected = await _collectEvents(graph)

    messageEvents = [e for e in collected if e.event == SseEvent.MESSAGE]
    assert not messageEvents, (
        f"Structured payload leak must not render as a MESSAGE bubble. Got: {messageEvents}"
    )

    suppressionCalls = [
        call
        for call in mockLogEvent.call_args_list
        if len(call.args) >= 2 and call.args[1] == "sse.final_response_suppressed_as_payload"
    ]
    assert suppressionCalls, "Expected structured-payload suppression log event."
