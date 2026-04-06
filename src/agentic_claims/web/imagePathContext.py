"""Request-scoped image path context variable.

Set by the chat router before graph invocation (after image is stored).
Read by submitClaim tool at MCP call time to inject the receipt image path
into the insertClaim MCP call without relying on the LLM to pass it through.

Uses Python contextvars for async-safe request isolation.
"""

from contextvars import ContextVar

imagePathVar: ContextVar[str | None] = ContextVar("imagePathVar", default=None)
