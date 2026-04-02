"""Per-session asyncio.Queue dict for decoupling POST from SSE GET."""

import asyncio

_queues: dict[str, asyncio.Queue] = {}


def getOrCreateQueue(threadId: str) -> asyncio.Queue:
    """Return existing queue for threadId, or create a new one."""
    if threadId not in _queues:
        _queues[threadId] = asyncio.Queue(maxsize=10)
    return _queues[threadId]


def removeQueue(threadId: str) -> None:
    """Remove queue for threadId. No-op if missing."""
    _queues.pop(threadId, None)
