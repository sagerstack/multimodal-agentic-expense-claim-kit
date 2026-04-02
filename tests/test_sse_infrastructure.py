"""Unit tests for SSE infrastructure: events, session queues, helpers, chat router."""

import asyncio
import json
import re

import pytest
from httpx import ASGITransport, AsyncClient

from agentic_claims.web.sessionQueues import getOrCreateQueue, removeQueue
from agentic_claims.web.sseEvents import SseEvent
from agentic_claims.web.sseHelpers import (
    TOOL_LABELS,
    _formatElapsed,
    _stripThinkingTags,
    _stripToolCallJson,
    _summarizeToolOutput,
)

# ── SseEvent constants ──


def testSseEventTokenConstant():
    assert SseEvent.TOKEN == "token"


def testSseEventAllConstantsAreLowercaseHyphenated():
    pattern = re.compile(r"^[a-z][a-z-]+$")
    for attr in dir(SseEvent):
        if attr.startswith("_"):
            continue
        value = getattr(SseEvent, attr)
        assert pattern.match(value), f"SseEvent.{attr} = '{value}' does not match pattern"


# ── sessionQueues ──


def testGetOrCreateQueueCreatesNew():
    q = getOrCreateQueue("test-new-thread")
    assert isinstance(q, asyncio.Queue)
    removeQueue("test-new-thread")


def testGetOrCreateQueueReturnsSameInstance():
    q1 = getOrCreateQueue("test-same-thread")
    q2 = getOrCreateQueue("test-same-thread")
    assert q1 is q2
    removeQueue("test-same-thread")


def testRemoveQueueCleansUp():
    q1 = getOrCreateQueue("test-remove-thread")
    removeQueue("test-remove-thread")
    q2 = getOrCreateQueue("test-remove-thread")
    assert q1 is not q2
    removeQueue("test-remove-thread")


def testRemoveQueueNoOpForMissing():
    removeQueue("nonexistent-thread-id")


# ── sseHelpers (ported functions) ──


def testStripToolCallJsonRemovesTrailingJson():
    text = 'Some text {"name": "tool", "arguments": {}}'
    result = _stripToolCallJson(text)
    assert result == "Some text"


def testStripToolCallJsonPreservesCleanText():
    text = "This is clean text without any JSON"
    result = _stripToolCallJson(text)
    assert result == text


def testStripThinkingTagsRemovesTags():
    text = "Hello <think>internal</think> world"
    result = _stripThinkingTags(text)
    assert result == "Hello  world"


def testFormatElapsedSeconds():
    assert _formatElapsed(45) == "45s"


def testFormatElapsedMinutes():
    assert _formatElapsed(125) == "2m 5s"


def testFormatElapsedSubSecond():
    assert _formatElapsed(0.5) == "<1s"


def testSummarizeToolOutputExtractReceipt():
    toolOutput = json.dumps(
        {
            "fields": {
                "merchant": "Starbucks",
                "totalAmount": "4.50",
                "currency": "SGD",
            }
        }
    )
    result = _summarizeToolOutput("extractReceiptFields", toolOutput)
    assert "Starbucks" in result


def testToolLabelsHasFiveEntries():
    assert len(TOOL_LABELS) == 5


def testToolLabelsIncludesGetClaimSchema():
    assert "getClaimSchema" in TOOL_LABELS


# ── Chat router (FastAPI TestClient) ──


@pytest.fixture
def testApp():
    """Create a test FastAPI app with session middleware and chat router."""
    from unittest.mock import MagicMock

    from fastapi import FastAPI
    from starlette.middleware.sessions import SessionMiddleware

    from agentic_claims.web.routers.chat import router as chatRouter

    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="test-secret",
        session_cookie="test_session",
    )
    app.include_router(chatRouter)
    app.state.graph = MagicMock()
    return app


@pytest.mark.asyncio
async def testPostMessageReturns204(testApp):
    transport = ASGITransport(app=testApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat/message",
            data={"message": "Hello"},
        )
        assert response.status_code == 204


@pytest.mark.asyncio
async def testResetClearsSessionAndRedirects(testApp):
    transport = ASGITransport(app=testApp)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/chat/reset")
        assert response.status_code == 204
        assert response.headers.get("hx-redirect") == "/"
