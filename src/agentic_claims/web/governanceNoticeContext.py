"""Request-scoped governance notice queue for SSE emission."""

from contextvars import ContextVar

governanceNoticeQueueVar: ContextVar[list[str] | None] = ContextVar(
    "governanceNoticeQueueVar", default=None
)


def init_notice_queue() -> None:
    """Initialize an empty notice queue for this request."""
    governanceNoticeQueueVar.set([])


def append_notice(notice: str) -> None:
    """Append a governance notice to the current request's queue."""
    queue = governanceNoticeQueueVar.get(None)
    if queue is not None:
        queue.append(notice)


def drain_notices() -> list[str]:
    """Drain and return all pending notices, clearing the queue."""
    queue = governanceNoticeQueueVar.get(None)
    if queue is None:
        return []
    notices = list(queue)
    queue.clear()
    return notices
