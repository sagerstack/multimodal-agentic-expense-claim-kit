"""RAG MCP Server for semantic policy search using Qdrant."""

import os
from typing import Any

from fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

# Environment configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "expense_policies")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# Initialize FastMCP server
mcp = FastMCP("rag-server")

# Global clients (initialized on startup)
qdrantClient: QdrantClient | None = None
encoder: SentenceTransformer | None = None


@mcp.tool()
def searchPolicies(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Semantic search against Qdrant expense_policies collection.

    Args:
        query: Natural language search query
        limit: Maximum number of results to return (default 5)

    Returns:
        List of matching policy chunks with text, file, score, category
    """
    if not qdrantClient or not encoder:
        return [{"error": "RAG server not initialized. Ensure Qdrant is running."}]

    # Encode query to vector
    queryVector = encoder.encode(query).tolist()

    # Search Qdrant (query_points replaces deprecated search in qdrant-client >= 1.12)
    response = qdrantClient.query_points(
        collection_name=COLLECTION_NAME, query=queryVector, limit=limit
    )

    # Format results
    return [
        {
            "text": r.payload.get("text", ""),
            "file": r.payload.get("file", "unknown"),
            "category": r.payload.get("category", "unknown"),
            "section": r.payload.get("section", ""),
            "score": round(r.score, 4),
        }
        for r in response.points
    ]


@mcp.tool()
def getPolicyByCategory(category: str) -> list[dict[str, Any]]:
    """
    Filter policies by category metadata.

    Args:
        category: Policy category (e.g., "meals", "transport", "accommodation")

    Returns:
        List of all policy chunks in the specified category
    """
    if not qdrantClient or not encoder:
        return [{"error": "RAG server not initialized. Ensure Qdrant is running."}]

    # Scroll through all points with category filter
    scrollResults = qdrantClient.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="category", match=MatchValue(value=category))]
        ),
        limit=100,
    )

    points, _ = scrollResults

    return [
        {
            "text": p.payload.get("text", ""),
            "file": p.payload.get("file", "unknown"),
            "category": p.payload.get("category", "unknown"),
            "section": p.payload.get("section", ""),
        }
        for p in points
    ]


@mcp.resource("qdrant://health")
def getQdrantHealth() -> str:
    """Check Qdrant connection health."""
    if not qdrantClient:
        return "Disconnected"
    try:
        collections = qdrantClient.get_collections()
        return f"Connected. Collections: {len(collections.collections)}"
    except Exception as e:
        return f"Error: {e}"


def initializeClients():
    """Initialize Qdrant and SentenceTransformer at startup."""
    global qdrantClient, encoder

    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    qdrantClient = QdrantClient(url=QDRANT_URL)

    print(f"Loading embedding model {EMBEDDING_MODEL}...")
    encoder = SentenceTransformer(EMBEDDING_MODEL)

    print("RAG MCP server initialized successfully.")


if __name__ == "__main__":
    # Initialize clients before starting server
    initializeClients()

    # Start FastMCP server with Streamable HTTP transport
    mcp.run(transport="streamable-http")
