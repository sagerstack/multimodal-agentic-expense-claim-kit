"""Checkpointer-based interrupt detection for the resume contract.

Replaces the session-cookie-based resume gate. The LangGraph checkpointer
is the authoritative source of whether a thread is paused at an interrupt:
when a node calls interrupt(), the paused task is persisted along with its
interrupt payload. Reading StateSnapshot.tasks[*].interrupts on the next
HTTP request tells us whether to build Command(resume=...) or a fresh input.

This removes the drift class of bugs where the session cookie and the
checkpointer disagreed (e.g., SSE stream setting the flag after headers
already flushed, so the browser never received Set-Cookie).
"""

from typing import Any


def isPausedAtInterrupt(snapshot: Any | None) -> bool:
    """Return True when the given StateSnapshot has a pending interrupt.

    A StateSnapshot as produced by graph.aget_state(config) exposes a
    `tasks` collection. Each task may carry an `interrupts` tuple containing
    the pending Interrupt(value=...) payloads. A non-empty interrupt tuple
    on any task means the thread is paused and the next graph invocation
    must be Command(resume=...).

    Returns False defensively when snapshot is missing, tasks attribute is
    absent, tasks collection is empty, or no task has interrupts.
    """
    if snapshot is None:
        return False
    tasks = getattr(snapshot, "tasks", None)
    if not tasks:
        return False
    return any(getattr(task, "interrupts", None) for task in tasks)
