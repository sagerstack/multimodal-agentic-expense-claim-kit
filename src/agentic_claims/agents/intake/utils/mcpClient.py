"""MCP client utility for Streamable HTTP tool calls."""

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def mcpCallTool(serverUrl: str, toolName: str, arguments: dict) -> list | dict:
    """Call an MCP server tool via Streamable HTTP transport.

    Args:
        serverUrl: Full URL to MCP server endpoint (e.g., "http://mcp-rag:8000/mcp/")
        toolName: Name of the tool to call
        arguments: Tool arguments as dict

    Returns:
        Result content list on success, error dict on failure
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

                # Return content list
                return result.content

    except ConnectionError as e:
        return {"error": f"Connection failed: {str(e)}"}
    except Exception as e:
        return {"error": f"MCP call failed: {str(e)}"}
