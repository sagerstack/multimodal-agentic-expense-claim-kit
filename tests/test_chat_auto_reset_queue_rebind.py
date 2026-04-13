"""Integration test for post-auto-reset queue rebinding.

Plan 13-13 used a module-level sentinel + session re-read. The SSE
session-stale gap (2026-04-13) replaced that with an in-band
`QueueRotationSignal` carrying the new threadId — SSE can no longer
trust `request.session` (frozen at request entry).
"""

import asyncio
import uuid

import pytest

from agentic_claims.web.sessionQueues import (
    QueueRotationSignal,
    getOrCreateQueue,
    popQueue,
)


@pytest.mark.asyncio
async def test_streamChatRebindsQueueAfterAutoReset():
    """After auto_reset pushes a QueueRotationSignal onto the OLD queue and
    rotates to a new threadId, the consumer must rebind to the NEW queue
    using the threadId carried in the signal — NOT by re-reading
    `request.session` (which is stale on long-lived SSE).
    """
    oldThreadId = str(uuid.uuid4())
    newThreadId = str(uuid.uuid4())

    oldQueue = getOrCreateQueue(oldThreadId)

    # Simulate auto_reset: pop the old queue, push a rotation signal
    # carrying the new threadId onto it to wake the blocked consumer.
    popped = popQueue(oldThreadId)
    assert popped is oldQueue
    await oldQueue.put(QueueRotationSignal(newThreadId=newThreadId))

    # Consumer wakes on the signal and extracts the new threadId in-band.
    signal = await asyncio.wait_for(oldQueue.get(), timeout=1.0)
    assert isinstance(signal, QueueRotationSignal)
    assert signal.newThreadId == newThreadId

    # Consumer rebinds to the NEW queue purely from the signal payload.
    newQueue = getOrCreateQueue(signal.newThreadId)
    assert newQueue is not oldQueue

    # POST enqueues graphInput on the NEW queue; consumer dequeues it.
    graphInput = {"payload": "hello"}
    await newQueue.put(graphInput)
    dequeued = await asyncio.wait_for(newQueue.get(), timeout=1.0)
    assert dequeued is graphInput
