"""Policy ingestion script for embedding and storing in Qdrant."""

import os
import re
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "expense_policies")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
POLICY_DIR = Path(os.getenv("POLICY_DIR", str(Path(__file__).parent.parent / "src" / "agentic_claims" / "policy")))

# Constants
VECTOR_DIMENSION = 384  # all-MiniLM-L6-v2 dimension
MAX_CHUNK_WORDS = 400
CHUNK_OVERLAP_WORDS = 50


def splitIntoChunks(text: str, filePath: Path) -> list[dict[str, Any]]:
    """
    Split markdown text into semantic chunks based on section headers.

    Strategy:
    1. Split on ## Section headers (preserve section as metadata)
    2. If a section exceeds MAX_CHUNK_WORDS, split further with overlap
    3. Store metadata: text, file, category, section

    Args:
        text: Markdown content
        filePath: Path to the source file

    Returns:
        List of chunks with metadata
    """
    chunks = []
    category = filePath.stem  # e.g., "meals" from "meals.md"

    # Split on ## Section headers
    sectionPattern = re.compile(r"^## (Section \d+(?:\.\d+)?:? .+)$", re.MULTILINE)
    sections = sectionPattern.split(text)

    # First element is content before first section (policy title, etc.)
    if sections[0].strip():
        chunks.append(
            {
                "text": sections[0].strip(),
                "file": filePath.name,
                "category": category,
                "section": "Introduction",
            }
        )

    # Process section pairs (header, content)
    for i in range(1, len(sections), 2):
        if i + 1 < len(sections):
            sectionHeader = sections[i].strip()
            sectionContent = sections[i + 1].strip()
            fullSection = f"## {sectionHeader}\n\n{sectionContent}"

            # Check if section is too long
            words = fullSection.split()
            if len(words) <= MAX_CHUNK_WORDS:
                # Section fits in one chunk
                chunks.append(
                    {
                        "text": fullSection,
                        "file": filePath.name,
                        "category": category,
                        "section": sectionHeader,
                    }
                )
            else:
                # Split long section with overlap
                chunkStartIdx = 0
                chunkNum = 1
                while chunkStartIdx < len(words):
                    chunkEndIdx = min(chunkStartIdx + MAX_CHUNK_WORDS, len(words))
                    chunkWords = words[chunkStartIdx:chunkEndIdx]
                    chunkText = " ".join(chunkWords)

                    chunks.append(
                        {
                            "text": chunkText,
                            "file": filePath.name,
                            "category": category,
                            "section": f"{sectionHeader} (part {chunkNum})",
                        }
                    )

                    # Move start index forward (with overlap)
                    chunkStartIdx += MAX_CHUNK_WORDS - CHUNK_OVERLAP_WORDS
                    chunkNum += 1

    return chunks


def ingestPolicies():
    """Main ingestion function."""
    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL)

    print(f"Loading embedding model {EMBEDDING_MODEL}...")
    encoder = SentenceTransformer(EMBEDDING_MODEL)

    # Recreate collection (idempotent)
    print(f"Recreating collection '{COLLECTION_NAME}'...")
    try:
        client.delete_collection(collection_name=COLLECTION_NAME)
        print(f"Deleted existing collection '{COLLECTION_NAME}'")
    except Exception:
        print(f"Collection '{COLLECTION_NAME}' did not exist (first run)")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_DIMENSION, distance=Distance.COSINE),
    )
    print(f"Created collection '{COLLECTION_NAME}' with {VECTOR_DIMENSION} dimensions")

    # Process all markdown files
    allChunks = []
    policyFiles = sorted(POLICY_DIR.glob("*.md"))

    if not policyFiles:
        print(f"WARNING: No policy files found in {POLICY_DIR}")
        return

    print(f"\nProcessing {len(policyFiles)} policy files...")
    for policyFile in policyFiles:
        print(f"  - {policyFile.name}")
        content = policyFile.read_text(encoding="utf-8")
        chunks = splitIntoChunks(content, policyFile)
        allChunks.extend(chunks)
        print(f"    Created {len(chunks)} chunks")

    # Embed all chunks
    print(f"\nEmbedding {len(allChunks)} chunks...")
    texts = [chunk["text"] for chunk in allChunks]
    embeddings = encoder.encode(texts, show_progress_bar=True)

    # Upsert to Qdrant
    print(f"\nUpserting {len(allChunks)} points to Qdrant...")
    points = [
        PointStruct(
            id=idx,
            vector=embeddings[idx].tolist(),
            payload={
                "text": chunk["text"],
                "file": chunk["file"],
                "category": chunk["category"],
                "section": chunk["section"],
            },
        )
        for idx, chunk in enumerate(allChunks)
    ]

    client.upsert(collection_name=COLLECTION_NAME, points=points)

    # Summary
    print("\n=== Ingestion Complete ===")
    print(f"Files processed: {len(policyFiles)}")
    print(f"Total chunks created: {len(allChunks)}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Vector dimension: {VECTOR_DIMENSION}")
    print(f"Distance metric: COSINE")

    # Show collection info
    collectionInfo = client.get_collection(collection_name=COLLECTION_NAME)
    print(f"\nCollection points count: {collectionInfo.points_count}")
    print(f"Collection status: {collectionInfo.status}")


if __name__ == "__main__":
    ingestPolicies()
