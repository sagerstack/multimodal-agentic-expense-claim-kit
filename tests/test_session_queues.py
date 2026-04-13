"""Unit tests for sessionQueues helpers (Plan 13-13 gap closure)."""

import asyncio

import pytest

from agentic_claims.web.sessionQueues import (
    _QUEUE_WAKE_SENTINEL,
    getOrCreateQueue,
    popQueue,
    removeQueue,
)


def test_sentinelIsSingleton():
    """Sentinel compares by identity (is), not by value."""
    assert _QUEUE_WAKE_SENTINEL is _QUEUE_WAKE_SENTINEL
    # Comparing a freshly built object() to the sentinel must be False.
    assert _QUEUE_WAKE_SENTINEL is not object()


@pytest.mark.asyncio
async def test_popQueueReturnsRemovedQueue():
    """popQueue returns the Queue instance that was removed from the dict."""
    q = getOrCreateQueue("thread-A")
    popped = popQueue("thread-A")
    assert popped is q
    # Second pop returns None (already removed).
    assert popQueue("thread-A") is None


@pytest.mark.asyncio
async def test_popQueueAllowsSentinelPush():
    """Caller can push sentinel onto the popped queue to wake a blocked consumer."""
    q = getOrCreateQueue("thread-B")

    async def consumer():
        return await q.get()

    consumerTask = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let consumer block on get()

    popped = popQueue("thread-B")
    assert popped is q
    await popped.put(_QUEUE_WAKE_SENTINEL)
    result = await asyncio.wait_for(consumerTask, timeout=1.0)
    assert result is _QUEUE_WAKE_SENTINEL


def test_removeQueueStillWorksAsNoOpWrapper():
    """removeQueue is a backward-compat wrapper over popQueue (discards return)."""
    getOrCreateQueue("thread-C")
    # Should not raise, should clear the entry.
    removeQueue("thread-C")
    assert popQueue("thread-C") is None


def test_removeQueueMissingIsNoOp():
    """removeQueue on an unknown threadId is a no-op (no exception)."""
    removeQueue("never-existed")
