"""Request-scoped governance notice queue and block message for SSE emission."""

from contextvars import ContextVar

governanceNoticeQueueVar: ContextVar[list[str] | None] = ContextVar(
    "governanceNoticeQueueVar", default=None
)

governanceBlockMessageVar: ContextVar[str | None] = ContextVar(
    "governanceBlockMessageVar", default=None
)


def init_notice_queue() -> None:
    """Initialize an empty notice queue for this request."""
    governanceNoticeQueueVar.set([])
    governanceBlockMessageVar.set(None)


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


def set_block_message(message: str) -> None:
    """Set the governance block message for this request."""
    governanceBlockMessageVar.set(message)


def get_block_message() -> str | None:
    """Get and clear the governance block message for this request."""
    message = governanceBlockMessageVar.get(None)
    if message is not None:
        governanceBlockMessageVar.set(None)
    return message
