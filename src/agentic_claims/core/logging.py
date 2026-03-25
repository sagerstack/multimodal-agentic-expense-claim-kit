"""Structured JSON logging setup with python-json-logger."""

import logging
import sys

from pythonjsonlogger import jsonlogger

from agentic_claims.core.config import getSettings


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
        static_fields={
            "service": "agentic-claims",
            "environment": settings.app_env
        }
    )

    # Configure root logger
    rootLogger = logging.getLogger()
    rootLogger.setLevel(getattr(logging, settings.log_level.upper(), logging.DEBUG))

    # Remove existing handlers to avoid duplicates
    rootLogger.handlers = []

    # Console handler (stdout) - always enabled
    consoleHandler = logging.StreamHandler(sys.stdout)
    consoleHandler.setFormatter(formatter)
    rootLogger.addHandler(consoleHandler)

    # File handler - only if log_file_path is set
    if settings.log_file_path:
        fileHandler = logging.FileHandler(settings.log_file_path)
        fileHandler.setFormatter(formatter)
        rootLogger.addHandler(fileHandler)
