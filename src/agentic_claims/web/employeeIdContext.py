"""Request-scoped employee ID context variable.

Set by the chat router before graph invocation.
Read by submitClaim tool at MCP call time.
Uses Python contextvars for async-safe request isolation.
"""

from contextvars import ContextVar

employeeIdVar: ContextVar[str | None] = ContextVar("employeeIdVar", default=None)
