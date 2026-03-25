"""Tests for MCP client utility."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_claims.agents.intake.utils.mcpClient import mcpCallTool


@pytest.mark.asyncio
async def testMcpCallToolSendsCorrectRequest():
    """Verify mcpCallTool sends correct request to MCP server."""
    mockSession = AsyncMock()
    mockSession.initialize = AsyncMock()
    mockSession.call_tool = AsyncMock()

    mockResult = MagicMock()
    mockResult.content = [{"type": "text", "text": "Success"}]
    mockSession.call_tool.return_value = mockResult

    mockReadStream = AsyncMock()
    mockWriteStream = AsyncMock()
    mockCallback = AsyncMock()

    # Mock streamablehttp_client to return tuple (readStream, writeStream, callback)
    mockStreamContext = AsyncMock()
    mockStreamContext.__aenter__ = AsyncMock(return_value=(mockReadStream, mockWriteStream, mockCallback))
    mockStreamContext.__aexit__ = AsyncMock()

    # Mock ClientSession
    mockSessionContext = AsyncMock()
    mockSessionContext.__aenter__ = AsyncMock(return_value=mockSession)
    mockSessionContext.__aexit__ = AsyncMock()

    with patch("agentic_claims.agents.intake.utils.mcpClient.streamablehttp_client") as mockStreamableClient, \
         patch("agentic_claims.agents.intake.utils.mcpClient.ClientSession") as MockClientSession:

        mockStreamableClient.return_value = mockStreamContext
        MockClientSession.return_value = mockSessionContext

        result = await mcpCallTool(
            serverUrl="http://localhost:8001/mcp/", toolName="testTool", arguments={"key": "value"}
        )

        # Verify streamablehttp_client was called with correct URL
        mockStreamableClient.assert_called_once()
        callArgs = mockStreamableClient.call_args[0]
        assert "http://localhost:8001/mcp/" in str(callArgs)

        # Verify ClientSession was created with streams
        MockClientSession.assert_called_once_with(mockReadStream, mockWriteStream)

        # Verify call_tool was called with correct tool name and arguments
        mockSession.call_tool.assert_called_once()
        toolCallArgs = mockSession.call_tool.call_args[1]
        assert toolCallArgs["name"] == "testTool"
        assert toolCallArgs["arguments"] == {"key": "value"}


@pytest.mark.asyncio
async def testMcpCallToolReturnsContent():
    """Verify mcpCallTool returns content list from result."""
    mockSession = AsyncMock()
    mockSession.initialize = AsyncMock()
    mockSession.call_tool = AsyncMock()

    mockResult = MagicMock()
    expectedContent = [{"type": "text", "text": "Test response"}]
    mockResult.content = expectedContent
    mockSession.call_tool.return_value = mockResult

    mockReadStream = AsyncMock()
    mockWriteStream = AsyncMock()
    mockCallback = AsyncMock()

    # Mock streamablehttp_client to return tuple (readStream, writeStream, callback)
    mockStreamContext = AsyncMock()
    mockStreamContext.__aenter__ = AsyncMock(return_value=(mockReadStream, mockWriteStream, mockCallback))
    mockStreamContext.__aexit__ = AsyncMock()

    # Mock ClientSession
    mockSessionContext = AsyncMock()
    mockSessionContext.__aenter__ = AsyncMock(return_value=mockSession)
    mockSessionContext.__aexit__ = AsyncMock()

    with patch("agentic_claims.agents.intake.utils.mcpClient.streamablehttp_client") as mockStreamableClient, \
         patch("agentic_claims.agents.intake.utils.mcpClient.ClientSession") as MockClientSession:

        mockStreamableClient.return_value = mockStreamContext
        MockClientSession.return_value = mockSessionContext

        result = await mcpCallTool(
            serverUrl="http://localhost:8001/mcp/", toolName="testTool", arguments={}
        )

        assert result == expectedContent, "Should return content list from result"


@pytest.mark.asyncio
async def testMcpCallToolHandlesConnectionError():
    """Verify mcpCallTool returns error dict on connection failure."""
    with patch("agentic_claims.agents.intake.utils.mcpClient.streamablehttp_client") as mockStreamableClient:
        mockStreamableClient.side_effect = ConnectionError("Failed to connect")

        result = await mcpCallTool(
            serverUrl="http://localhost:8001/mcp/", toolName="testTool", arguments={}
        )

        assert isinstance(result, dict), "Should return dict on error"
        assert "error" in result, "Should have 'error' key"
        assert "connection" in result["error"].lower() or "failed" in result["error"].lower()
