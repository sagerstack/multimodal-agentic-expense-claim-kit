"""In-memory image store for passing receipt images between Chainlit and agent tools.

Avoids embedding large base64 strings in LangGraph messages which would exceed
the LLM context window. Images are stored by claimId and retrieved by tools directly.

Images are also persisted to disk at static/uploads/{claimId}.jpg so they survive
restarts and can be served from the review and audit pages.
"""

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_store: dict[str, str] = {}
# Secondary store: claimId -> relative image path (e.g. "uploads/abc123.jpg")
_pathStore: dict[str, str] = {}


def _uploadsDir() -> Path:
    """Resolve static/uploads directory, creating it if needed."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "static").is_dir() and (candidate / "templates").is_dir():
            break
    else:
        candidate = Path("/app")

    uploadsDir = candidate / "static" / "uploads"
    uploadsDir.mkdir(parents=True, exist_ok=True)
    return uploadsDir


def storeImage(claimId: str, imageB64: str) -> str | None:
    """Store a base64-encoded image for a claim.

    Saves to in-memory store and persists to static/uploads/{claimId}.jpg.

    Returns:
        Relative path "uploads/{claimId}.jpg" for use in receiptData.imagePath,
        or None if disk write fails.
    """
    _store[claimId] = imageB64
    try:
        uploadsDir = _uploadsDir()
        imagePath = uploadsDir / f"{claimId}.jpg"
        imagePath.write_bytes(base64.b64decode(imageB64))
        relPath = f"uploads/{claimId}.jpg"
        _pathStore[claimId] = relPath
        logger.debug("Receipt image persisted to disk", extra={"path": str(imagePath)})
        return relPath
    except Exception as e:
        logger.warning("Failed to persist receipt image to disk", extra={"claimId": claimId, "error": str(e)})
        return None


def getImage(claimId: str) -> str | None:
    """Retrieve a stored base64-encoded image by claimId.

    Falls back to reading from disk if not in memory.
    """
    if claimId in _store:
        return _store[claimId]
    # Try loading from disk
    try:
        uploadsDir = _uploadsDir()
        imagePath = uploadsDir / f"{claimId}.jpg"
        if imagePath.exists():
            imageBytes = imagePath.read_bytes()
            imageB64 = base64.b64encode(imageBytes).decode("utf-8")
            _store[claimId] = imageB64
            return imageB64
    except Exception as e:
        logger.warning("Failed to load receipt image from disk", extra={"claimId": claimId, "error": str(e)})
    return None


def getImagePath(claimId: str) -> str | None:
    """Return the relative image path for a claim (e.g. 'uploads/{claimId}.jpg')."""
    if claimId in _pathStore:
        return _pathStore[claimId]
    # Check if file exists on disk
    try:
        uploadsDir = _uploadsDir()
        imagePath = uploadsDir / f"{claimId}.jpg"
        if imagePath.exists():
            relPath = f"uploads/{claimId}.jpg"
            _pathStore[claimId] = relPath
            return relPath
    except Exception:
        pass
    return None


def clearImage(claimId: str) -> None:
    """Remove a stored image from memory (disk copy is kept for audit trail)."""
    _store.pop(claimId, None)
    _pathStore.pop(claimId, None)
