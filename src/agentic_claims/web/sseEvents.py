"""SSE event type constants — single source of truth for all event names."""


class SseEvent:
    TOKEN = "token"
    THINKING_START = "thinking-start"
    STEP_NAME = "step-name"
    STEP_CONTENT = "step-content"
    THINKING_DONE = "thinking-done"
    MESSAGE = "message"
    SUMMARY_UPDATE = "summary-update"
    PATHWAY_UPDATE = "pathway-update"
    TABLE_UPDATE = "table-update"
    DONE = "done"
    ERROR = "error"
    INTERRUPT = "interrupt"
    GOVERNANCE_NOTICE = "governance-notice"  # Informational → thinking panel (deprecated, use GOVERNANCE_PERSISTENT)
    GOVERNANCE_PERSISTENT = "governance-persistent"  # Actionable notices → persistent strip
    GOVERNANCE_MESSAGE = "governance-message"  # Enforcement → main thread
