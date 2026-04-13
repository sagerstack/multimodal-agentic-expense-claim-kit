"""Unit tests for sessionQueues helpers (Plan 13-13 + SSE session-stale gap)."""

import asyncio

import pytest

from agentic_claims.web.sessionQueues import (
    QueueRotationSignal,
    getOrCreateQueue,
    popQueue,
    removeQueue,
)


def test_rotationSignalCarriesNewThreadId():
    """QueueRotationSignal must expose the new threadId for in-band rebind."""
    signal = QueueRotationSignal(newThreadId="thread-new-123")
    assert signal.newThreadId == "thread-new-123"


def test_rotationSignalIsFrozen():
    """Frozen dataclass — tampering with newThreadId must fail."""
    signal = QueueRotationSignal(newThreadId="a")
    with pytest.raises((AttributeError, Exception)):
        signal.newThreadId = "b"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_popQueueReturnsRemovedQueue():
    """popQueue returns the Queue instance that was removed from the dict."""
    q = getOrCreateQueue("thread-A")
    popped = popQueue("thread-A")
    assert popped is q
    # Second pop returns None (already removed).
    assert popQueue("thread-A") is None


@pytest.mark.asyncio
async def test_popQueueAllowsRotationSignalPush():
    """Caller pushes a QueueRotationSignal onto the popped queue to wake + rebind the consumer."""
    q = getOrCreateQueue("thread-B")

    async def consumer():
        return await q.get()

    consumerTask = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let consumer block on get()

    popped = popQueue("thread-B")
    assert popped is q
    await popped.put(QueueRotationSignal(newThreadId="thread-B-new"))
    result = await asyncio.wait_for(consumerTask, timeout=1.0)
    assert isinstance(result, QueueRotationSignal)
    assert result.newThreadId == "thread-B-new"


def test_removeQueueStillWorksAsNoOpWrapper():
    """removeQueue is a backward-compat wrapper over popQueue (discards return)."""
    getOrCreateQueue("thread-C")
    removeQueue("thread-C")
    assert popQueue("thread-C") is None


def test_removeQueueMissingIsNoOp():
    """removeQueue on an unknown threadId is a no-op (no exception)."""
    removeQueue("never-existed")
