"""Request-scoped governance notice queue and block message for SSE emission.

Uses mutable-container pattern to cross LangGraph async task boundaries.
ContextVar.set() rebinds in child task context and is not visible to parent.
Mutating a shared list object works across all nested async tasks.
"""

from contextvars import ContextVar

governanceNoticeQueueVar: ContextVar[list[str] | None] = ContextVar(
    "governanceNoticeQueueVar", default=None
)

governanceBlockHolderVar: ContextVar[list[str] | None] = ContextVar(
    "governanceBlockHolderVar", default=None
)

# Background agent governance (compliance/fraud/advisor) - structured fired_controls
# Stores [{controlId, name, result, entityTypes, signalValue}, ...] for embedding in *Findings
backgroundGovernanceVar: ContextVar[list[dict] | None] = ContextVar(
    "backgroundGovernanceVar", default=None
)


def init_notice_queue() -> None:
    """Initialize an empty notice queue and block holder for this request.
    
    Creates mutable containers in PARENT context before graph runs.
    Child tasks (e.g., reasonNode) can mutate these shared objects.
    """
    governanceNoticeQueueVar.set([])
    governanceBlockHolderVar.set([])  # mutable holder for cross-task visibility
    backgroundGovernanceVar.set([])  # mutable holder for background agent governance


def append_notice(notice: str) -> None:
    """Append a governance notice to the current request's queue."""
    queue = governanceNoticeQueueVar.get(None)
    if queue is not None:
        queue.append(notice)  # MUTATE shared object


def drain_notices() -> list[str]:
    """Drain and return all pending notices, clearing the queue."""
    queue = governanceNoticeQueueVar.get(None)
    if queue is None:
        return []
    notices = list(queue)
    queue.clear()  # MUTATE shared object
    return notices


def set_block_message(message: str) -> None:
    """Set the governance block message for this request.
    
    Mutates shared holder (crosses async task boundary).
    """
    holder = governanceBlockHolderVar.get(None)
    if holder is not None:
        holder.append(message)  # MUTATE shared object


def get_block_message() -> str | None:
    """Get and clear the governance block message for this request."""
    holder = governanceBlockHolderVar.get(None)
    if not holder:
        return None
    message = holder[0]
    holder.clear()  # MUTATE shared object
    return message


def append_background_governance(fired_control: dict) -> None:
    """Append a fired governance control to background agent collection.
    
    Used by compliance/fraud/advisor to collect structured governance data
    for embedding in their *Findings JSONB (not chat notices).
    
    Args:
        fired_control: Structured control dict from ContentHookResult.fired_controls
                      {controlId, name, result, entityTypes, signalValue, ...}
    """
    holder = backgroundGovernanceVar.get(None)
    if holder is not None:
        holder.append(fired_control)  # MUTATE shared object


def drain_background_governance() -> list[dict]:
    """Drain and return all background agent governance controls, clearing the holder.
    
    Returns:
        List of structured fired_control dicts for embedding in *Findings.governance
    """
    holder = backgroundGovernanceVar.get(None)
    if holder is None:
        return []
    controls = list(holder)
    holder.clear()  # MUTATE shared object
    return controls
