"""Tests for structured application logging helpers."""

import logging
from unittest.mock import patch

from agentic_claims.core.logging import AppLogContextFilter, logEvent, redactForLogging


def testRedactForLoggingRedactsSensitiveKeysAndLargeImages():
    payload = {
        "apiKey": "secret",
        "headers": {"Authorization": "Bearer token"},
        "receiptImageBase64": "a" * 600,
        "message": "hello",
    }

    redacted = redactForLogging(payload)

    assert redacted["apiKey"] == "<redacted>"
    assert redacted["headers"]["Authorization"] == "<redacted>"
    assert redacted["receiptImageBase64"] == "<redacted>"
    assert redacted["message"] == "hello"


def testLogEventIncludesLocalPayloadAndFilterKeywords(caplog):
    logger = logging.getLogger("agentic_claims.tests.logging")

    with patch("agentic_claims.core.logging.localPayloadEnabled", return_value=True):
        with caplog.at_level(logging.INFO, logger=logger.name):
            logEvent(
                logger,
                "mcp.call",
                logCategory="mcp_tool_call",
                claimNumber="CLAIM-002",
                draftClaimNumber="DRAFT-abc123",
                toolName="searchPolicies",
                payload={"password": "secret", "query": "meals"},
            )

    record = caplog.records[-1]
    assert record.event == "mcp.call"
    assert record.logCategory == "mcp_tool_call"
    assert record.claimNumber == "CLAIM-002"
    assert record.draftClaimNumber == "DRAFT-abc123"
    assert record.toolName == "searchPolicies"
    assert record.payload["password"] == "<redacted>"
    assert record.payload["query"] == "meals"


def testAppLogContextFilterTagsAgentLogs():
    record = logging.LogRecord(
        name="agentic_claims.agents.fraud.node",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="test",
        args=(),
        exc_info=None,
    )

    assert AppLogContextFilter().filter(record) is True
    assert record.logCategory == "agent"
    assert record.agent == "fraud"
