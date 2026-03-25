"""MCP client utility for Streamable HTTP tool calls."""

import json
import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


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
    # Log tool entry
    logger.info(
        "mcpCallTool called",
        extra={
            "serverUrl": serverUrl,
            "toolName": toolName,
            "argumentKeys": list(arguments.keys()),
        }
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
                logger.info("Calling MCP tool", extra={"toolName": toolName})
                result = await session.call_tool(name=toolName, arguments=arguments)

                # Log result details
                logger.info(
                    "MCP tool returned",
                    extra={
                        "contentCount": len(result.content) if result.content else 0,
                        "hasText": hasattr(result.content[0], "text") if result.content else False,
                    }
                )

                # Parse MCP content: extract text from first TextContent and parse as JSON
                if result.content and hasattr(result.content[0], "text"):
                    rawText = result.content[0].text
                    logger.debug("Raw text from MCP", extra={"rawText": rawText[:200]})

                    try:
                        parsed = json.loads(rawText)
                        logger.info(
                            "JSON parse successful",
                            extra={"parsedType": type(parsed).__name__}
                        )
                        return parsed
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(
                            "JSON parse failed, returning raw text",
                            extra={"error": str(e)}
                        )
                        return rawText

                logger.info("Returning raw content list")
                return result.content

    except ConnectionError as e:
        logger.error(
            "MCP connection failed",
            extra={"serverUrl": serverUrl, "error": str(e)},
            exc_info=True
        )
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        logger.error(
            "MCP call failed",
            extra={"serverUrl": serverUrl, "toolName": toolName, "error": str(e)},
            exc_info=True
        )
        return {"error": f"MCP call failed: {str(e)}"}
