"""Per-session asyncio.Queue dict for decoupling POST from SSE GET.

Phase 13 (Plan 13-13): added `popQueue` returning the removed Queue so that
callers (specifically `postMessage` on auto_reset) can push a wake sentinel
onto the old queue before dropping the last reference — unblocking a
consumer that was `await queue.get()`-ing on the now-orphaned queue.

Sources:
  - 13-DEBUG-post-reset-stuck.md (root cause: queue orphaning across
    threadId rotation)
  - 13-DEBUG-post-reset-stuck.md "Proposed fix outline" Option 1 + Option 4

TODO(post-13): Option 3 (session-indexed queues) is a more invasive refactor
that eliminates the rotation race entirely. Adopt if Option 1+4 proves flaky
under concurrent load.
"""

import asyncio
from typing import Any

_queues: dict[str, asyncio.Queue] = {}

# Module-level singleton used to wake a blocked streamChat consumer without
# yielding a client-visible SSE event. Compared via `is`, not by value.
_QUEUE_WAKE_SENTINEL: Any = object()


def getOrCreateQueue(threadId: str) -> asyncio.Queue:
    """Return existing queue for threadId, or create a new one."""
    if threadId not in _queues:
        _queues[threadId] = asyncio.Queue(maxsize=10)
    return _queues[threadId]


def popQueue(threadId: str) -> asyncio.Queue | None:
    """Remove queue for threadId and return the Queue instance (or None).

    The caller may push `_QUEUE_WAKE_SENTINEL` onto the returned Queue to
    unblock a consumer that is awaiting `queue.get()` against this
    now-orphaned instance, then drop the reference.
    """
    return _queues.pop(threadId, None)


def removeQueue(threadId: str) -> None:
    """Backward-compat wrapper over `popQueue`: remove and discard.

    Retained so existing call sites that do NOT need the sentinel dance
    remain unchanged.
    """
    popQueue(threadId)
