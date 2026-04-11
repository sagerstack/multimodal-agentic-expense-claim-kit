"""MCP client utility for Streamable HTTP tool calls."""

import json
import logging
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from agentic_claims.core.logging import logEvent

logger = logging.getLogger(__name__)


def _claimFieldsFromPayload(payload: dict | list | str | None) -> dict:
    """Extract claim identifiers from MCP arguments/results for log filters."""
    if not isinstance(payload, dict):
        return {}
    claimNumber = payload.get("claimNumber") or payload.get("claim_number")
    claim = payload.get("claim")
    if isinstance(claim, dict):
        claimNumber = claimNumber or claim.get("claim_number") or claim.get("claimNumber")
        dbClaimId = claim.get("id")
    else:
        dbClaimId = payload.get("dbClaimId") or payload.get("claimId")
    fields = {}
    if claimNumber:
        if str(claimNumber).startswith("DRAFT-"):
            fields["draftClaimNumber"] = claimNumber
        else:
            fields["claimNumber"] = claimNumber
    if dbClaimId:
        fields["dbClaimId"] = dbClaimId
    return fields


async def mcpCallTool(serverUrl: str, toolName: str, arguments: dict) -> list | dict:
    """Call an MCP server tool via Streamable HTTP transport.

    Args:
        serverUrl: Full URL to MCP server endpoint (e.g., "http://mcp-rag:8000/mcp/")
        toolName: Name of the tool to call
        arguments: Tool arguments as dict

    Returns:
        Parsed result (dict or list) on success, error dict on failure.
        MCP TextContent is automatically parsed from JSON.
    """
    startTime = time.time()
    argumentClaimFields = _claimFieldsFromPayload(arguments)
    logEvent(
        logger,
        "mcp.call",
        logCategory="mcp_tool_call",
        actorType="app",
        toolName=toolName,
        mcpServer=serverUrl,
        status="started",
        payload={"arguments": arguments},
        **argumentClaimFields,
        message="MCP tool call started",
    )

    try:
        # Connect to MCP server via Streamable HTTP
        async with streamablehttp_client(serverUrl) as (readStream, writeStream, _):
            # Create client session
            async with ClientSession(readStream, writeStream) as session:
                # Initialize session
                logger.debug("Initializing MCP session")
                await session.initialize()

                # Call tool
                logger.debug("Calling MCP tool", extra={"toolName": toolName})
                result = await session.call_tool(name=toolName, arguments=arguments)

                # Parse MCP content: extract text from first TextContent and parse as JSON
                if result.content and hasattr(result.content[0], "text"):
                    rawText = result.content[0].text
                    logger.debug("Raw text from MCP", extra={"rawText": rawText[:200]})

                    try:
                        parsed = json.loads(rawText)
                        logEvent(
                            logger,
                            "mcp.result",
                            logCategory="mcp_tool_call",
                            actorType="app",
                            toolName=toolName,
                            mcpServer=serverUrl,
                            status="completed",
                            elapsedMs=round((time.time() - startTime) * 1000),
                            payload={"result": parsed},
                            **{**argumentClaimFields, **_claimFieldsFromPayload(parsed)},
                            message="MCP tool call completed",
                        )
                        return parsed
                    except (json.JSONDecodeError, TypeError) as e:
                        logEvent(
                            logger,
                            "mcp.result",
                            level=logging.WARNING,
                            logCategory="mcp_tool_call",
                            actorType="app",
                            toolName=toolName,
                            mcpServer=serverUrl,
                            status="completed_unparsed",
                            elapsedMs=round((time.time() - startTime) * 1000),
                            errorType=type(e).__name__,
                            payload={"result": rawText, "parseError": str(e)},
                            **argumentClaimFields,
                            message="MCP tool returned non-JSON text",
                        )
                        return rawText

                logEvent(
                    logger,
                    "mcp.result",
                    logCategory="mcp_tool_call",
                    actorType="app",
                    toolName=toolName,
                    mcpServer=serverUrl,
                    status="completed_raw",
                    elapsedMs=round((time.time() - startTime) * 1000),
                    payload={"result": result.content},
                    **argumentClaimFields,
                    message="MCP tool call completed with raw content",
                )
                return result.content

    except ConnectionError as e:
        logEvent(
            logger,
            "mcp.error",
            level=logging.ERROR,
            logCategory="mcp_tool_call",
            actorType="app",
            toolName=toolName,
            mcpServer=serverUrl,
            status="failed",
            elapsedMs=round((time.time() - startTime) * 1000),
            errorType=type(e).__name__,
            payload={"error": str(e), "arguments": arguments},
            **argumentClaimFields,
            message="MCP connection failed",
        )
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        logEvent(
            logger,
            "mcp.error",
            level=logging.ERROR,
            logCategory="mcp_tool_call",
            actorType="app",
            toolName=toolName,
            mcpServer=serverUrl,
            status="failed",
            elapsedMs=round((time.time() - startTime) * 1000),
            errorType=type(e).__name__,
            payload={"error": str(e), "arguments": arguments},
            **argumentClaimFields,
            message="MCP call failed",
        )
        return {"error": f"MCP call failed: {str(e)}"}
