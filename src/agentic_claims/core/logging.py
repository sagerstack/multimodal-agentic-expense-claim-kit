"""Structured JSON logging setup with python-json-logger."""

import json
import logging
import re
import sys
import urllib.request
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from pythonjsonlogger import jsonlogger

from agentic_claims.core.config import getSettings

APP_EVENT_LOGGER = "agentic_claims.app_events"
LOCAL_PAYLOAD_ENVS = {"local", "dev", "development"}
SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|auth[_-]?header|cookie|password|passwd|secret|token|image|base64|b64)",
    re.IGNORECASE,
)
LONG_TEXT_LIMIT = 5000


def _redactedString(value: str) -> str:
    """Redact long/base64-looking strings while keeping useful diagnostics."""
    compact = value.strip()
    if len(compact) > LONG_TEXT_LIMIT:
        return f"<redacted:length={len(value)}>"
    if len(compact) > 512 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", compact):
        return f"<redacted:base64-like:length={len(value)}>"
    return value


def redactForLogging(value: Any) -> Any:
    """Recursively redact secrets and large binary payloads from log payloads."""
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            keyStr = str(key)
            if SENSITIVE_KEY_RE.search(keyStr):
                redacted[keyStr] = "<redacted>"
            else:
                redacted[keyStr] = redactForLogging(item)
        return redacted
    if isinstance(value, str):
        return _redactedString(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redactForLogging(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return f"<redacted:bytes:length={len(value)}>"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def localPayloadEnabled() -> bool:
    """Return whether full payload logs may be emitted for this environment."""
    return getSettings().app_env.lower() in LOCAL_PAYLOAD_ENVS


def logEvent(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    message: str | None = None,
    payload: Any | None = None,
    **fields: Any,
) -> None:
    """Emit a normalized structured application event.

    `payload` is included only in local/dev environments and is redacted before
    logging. Metadata fields are always included so Seq can filter by
    `logCategory`, `claimNumber`, `draftClaimNumber`, agent, tool, and user.
    """
    extra = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    if payload is not None and localPayloadEnabled():
        extra["payload"] = redactForLogging(payload)
    logger.log(level, message or event, extra=extra)


class SeqHandler(logging.Handler):
    """HTTP handler that POSTs log events to Seq in CLEF format.

    CLEF (Compact Log Event Format) is JSON with:
    - @t: ISO 8601 timestamp
    - @l: level (Debug, Information, Warning, Error, Fatal)
    - @mt: message template
    - @x: exception (optional)
    - Additional properties are indexed by Seq

    Errors during HTTP POST are handled silently (Seq may not be running).
    """

    LEVEL_MAP = {
        logging.DEBUG: "Debug",
        logging.INFO: "Information",
        logging.WARNING: "Warning",
        logging.ERROR: "Error",
        logging.CRITICAL: "Fatal",
    }

    def __init__(self, seqUrl: str, apiKey: str = ""):
        """Initialize Seq HTTP handler.

        Args:
            seqUrl: Seq CLEF ingestion endpoint (e.g. http://seq/api/events/raw)
            apiKey: Optional Seq API key for authentication
        """
        super().__init__()
        self.seqUrl = seqUrl
        self.apiKey = apiKey

    def emit(self, record: logging.LogRecord) -> None:
        """Format log record as CLEF and POST to Seq.

        Args:
            record: Log record to send
        """
        try:
            # Build CLEF JSON
            settings = getSettings()
            clefEvent = {
                "@t": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "@l": self.LEVEL_MAP.get(record.levelno, "Information"),
                "@mt": record.getMessage(),
                "logger": record.name,
                "function": record.funcName,
                "line": record.lineno,
                "service": "agentic-claims",
                "environment": settings.app_env,
            }

            # Add exception info if present
            if record.exc_info:
                clefEvent["@x"] = self.format(record)

            # Add any extra fields from record
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                ]:
                    clefEvent[key] = value

            # POST to Seq
            clefJson = json.dumps(clefEvent).encode("utf-8")
            req = urllib.request.Request(
                self.seqUrl,
                data=clefJson,
                headers={
                    "Content-Type": "application/vnd.serilog.clef",
                    "X-Seq-ApiKey": self.apiKey,
                },
            )
            urllib.request.urlopen(req, timeout=5)

        except Exception:
            # Silently handle errors (Seq may not be running).
            pass


class AppLogContextFilter(logging.Filter):
    """Add default structured filter fields to app-owned logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith("agentic_claims.agents.") and not hasattr(record, "logCategory"):
            record.logCategory = "agent"
            parts = record.name.split(".")
            if len(parts) >= 3 and not hasattr(record, "agent"):
                record.agent = parts[2]
        return True


def setupLogging() -> None:
    """Configure structured JSON logging for the application.

    Sets up a JSON formatter that outputs structured log entries suitable
    for ingestion by Seq or other log aggregation systems.

    The formatter includes:
    - timestamp: ISO 8601 formatted timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - name: Logger name (module path)
    - function: Function name where log was called
    - line: Line number where log was called
    - message: Log message
    - service: Static field identifying the application
    - environment: Environment name (local, prod)

    Handlers:
    - Console (stdout): Always enabled
    - File: Enabled when log_file_path setting is non-empty
    """
    settings = getSettings()

    # Create JSON formatter with standard fields
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(funcName)s %(lineno)d %(message)s",
        static_fields={"service": "agentic-claims", "environment": settings.app_env},
    )

    # Configure root logger
    rootLogger = logging.getLogger()
    rootLogger.setLevel(getattr(logging, settings.log_level.upper(), logging.DEBUG))

    # Remove existing handlers to avoid duplicates
    rootLogger.handlers = []

    # Console handler (stdout) - always enabled
    contextFilter = AppLogContextFilter()
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.addFilter(contextFilter)
    consoleHandler.setFormatter(formatter)
    rootLogger.addHandler(consoleHandler)

    # File handler - only if log_file_path is set
    if settings.log_file_path:
        fileHandler = logging.FileHandler(settings.log_file_path)
        fileHandler.addFilter(contextFilter)
        fileHandler.setFormatter(formatter)
        rootLogger.addHandler(fileHandler)

    # Seq handler - only if seq_ingestion_url is set
    if settings.seq_ingestion_url:
        seqHandler = SeqHandler(seqUrl=settings.seq_ingestion_url, apiKey=settings.seq_password)
        seqHandler.addFilter(contextFilter)
        rootLogger.addHandler(seqHandler)

    # Filter third-party loggers to WARNING. App-owned MCP logs remain under
    # agentic_claims.* and continue to flow through logEvent().
    for noisyLogger in [
        "openai",
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "python_multipart",
        "mcp",
        "mcp.client",
        "fastmcp",
        "uvicorn.access",
    ]:
        logging.getLogger(noisyLogger).setLevel(logging.WARNING)
