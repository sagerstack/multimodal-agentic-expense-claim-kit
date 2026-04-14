"""Per-session asyncio.Queue dict for decoupling POST from SSE GET.

Phase 13 (Plan 13-13): added `popQueue` returning the removed Queue so that
callers (specifically `postMessage` on auto_reset) can push a wake signal
onto the old queue before dropping the last reference — unblocking a
consumer that was `await queue.get()`-ing on the now-orphaned queue.

Post-13 gap (2026-04-13): replaced opaque sentinel with
`QueueRotationSignal`, which carries the new threadId in-band. This closes
the stale-session bug where SSE's frozen `request.session` could never learn
the rotated threadId from a cookie update.
"""

import asyncio
from dataclasses import dataclass

_queues: dict[str, asyncio.Queue] = {}


@dataclass(frozen=True)
class QueueRotationSignal:
    """In-band wake signal carrying the new threadId after session auto-reset.

    Placed on the OLD (popped) queue by the POST handler immediately before
    rotation. The streamChat consumer dequeues it, reads `newThreadId`
    directly, and rebinds to the new queue. This avoids depending on
    `request.session` on the long-lived SSE request, which is populated from
    the cookie at connection time and never refreshed.
    """

    newThreadId: str


def getOrCreateQueue(threadId: str) -> asyncio.Queue:
    """Return existing queue for threadId, or create a new one."""
    if threadId not in _queues:
        _queues[threadId] = asyncio.Queue(maxsize=10)
    return _queues[threadId]


def popQueue(threadId: str) -> asyncio.Queue | None:
    """Remove queue for threadId and return the Queue instance (or None).

    The caller may push a `QueueRotationSignal` onto the returned Queue to
    unblock and rebind a consumer that is awaiting `queue.get()` against
    this now-orphaned instance, then drop the reference.
    """
    return _queues.pop(threadId, None)


def removeQueue(threadId: str) -> None:
    """Backward-compat wrapper over `popQueue`: remove and discard.

    Retained so existing call sites that do NOT need the sentinel dance
    remain unchanged.
    """
    popQueue(threadId)
