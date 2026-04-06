"""In-memory image store for passing receipt images between Chainlit and agent tools.

Avoids embedding large base64 strings in LangGraph messages which would exceed
the LLM context window. Images are stored by claimId and retrieved by tools directly.
"""

_store: dict[str, str] = {}


def storeImage(claimId: str, imageB64: str) -> None:
    """Store a base64-encoded image for a claim."""
    _store[claimId] = imageB64


def getImage(claimId: str) -> str | None:
    """Retrieve a stored base64-encoded image by claimId."""
    return _store.get(claimId)


def clearImage(claimId: str) -> None:
    """Remove a stored image (cleanup after processing)."""
    _store.pop(claimId, None)
