"""Integration test for post-auto-reset queue rebinding (Plan 13-13 gap closure)."""

import asyncio
import uuid

import pytest

from agentic_claims.web.sessionQueues import (
    _QUEUE_WAKE_SENTINEL,
    getOrCreateQueue,
    popQueue,
)


class _DummySession(dict):
    pass


class _DummyRequest:
    def __init__(self, threadId: str, claimId: str):
        self.session = _DummySession(thread_id=threadId, claim_id=claimId)
        self._disconnected = False

    async def is_disconnected(self):
        return self._disconnected


@pytest.mark.asyncio
async def test_streamChatRebindsQueueAfterAutoReset():
    """After auto_reset pushes a sentinel onto the OLD queue and rotates
    session['thread_id'], the streamChat loop must pick up the NEW queue on
    the next iteration and dequeue a graphInput placed there.
    """
    from agentic_claims.web.routers.chat import _reResolveSessionBindings  # new helper

    oldThreadId = str(uuid.uuid4())
    newThreadId = str(uuid.uuid4())
    request = _DummyRequest(oldThreadId, claimId=str(uuid.uuid4()))

    oldQueue = getOrCreateQueue(oldThreadId)

    # Initial resolution: returns the old (current) threadId + queue.
    tId, q = _reResolveSessionBindings(request, oldThreadId, oldQueue)
    assert tId == oldThreadId
    assert q is oldQueue

    # Simulate auto_reset: rotate the session thread_id, push sentinel onto
    # the old queue so the blocked get() unblocks, then pop it.
    request.session["thread_id"] = newThreadId
    await oldQueue.put(_QUEUE_WAKE_SENTINEL)
    popped = popQueue(oldThreadId)
    assert popped is oldQueue

    # Consumer wakes on sentinel, re-resolves bindings.
    sentinel = await asyncio.wait_for(oldQueue.get(), timeout=1.0)
    assert sentinel is _QUEUE_WAKE_SENTINEL
    tId2, q2 = _reResolveSessionBindings(request, oldThreadId, oldQueue)
    assert tId2 == newThreadId
    assert q2 is not oldQueue
    assert q2 is getOrCreateQueue(newThreadId)

    # POST enqueues graphInput on the NEW queue; consumer dequeues it.
    graphInput = {"sentinel": False, "payload": "hello"}
    await q2.put(graphInput)
    dequeued = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert dequeued is graphInput
