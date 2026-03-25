"""MCP client utility for Streamable HTTP tool calls."""

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


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
    try:
        # Connect to MCP server via Streamable HTTP
        async with streamablehttp_client(serverUrl) as (readStream, writeStream, _):
            # Create client session
            async with ClientSession(readStream, writeStream) as session:
                # Initialize session
                await session.initialize()

                # Call tool
                result = await session.call_tool(name=toolName, arguments=arguments)

                # Parse MCP content: extract text from first TextContent and parse as JSON
                if result.content and hasattr(result.content[0], "text"):
                    try:
                        return json.loads(result.content[0].text)
                    except (json.JSONDecodeError, TypeError):
                        return result.content[0].text

                return result.content

    except ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": f"MCP call failed: {str(e)}"}
