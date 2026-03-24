"""Tests for policy ingestion and chunking logic."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.ingest_policies import splitIntoChunks


def testSplitIntoChunksWithSections():
    """Test that markdown with section headers splits correctly."""
    markdown = """# SUTD Meal Policy

## Section 1: Scope

This is the scope section.

## Section 2: Caps

Daily caps apply.
"""
    filePath = Path("meals.md")

    chunks = splitIntoChunks(markdown, filePath)

    # Should have 3 chunks: intro, section 1, section 2
    assert len(chunks) >= 2

    # Check metadata structure
    for chunk in chunks:
        assert "text" in chunk
        assert "file" in chunk
        assert "category" in chunk
        assert "section" in chunk
        assert chunk["file"] == "meals.md"
        assert chunk["category"] == "meals"


def testChunkMetadataContainsRequiredFields():
    """Test that all chunks have required metadata fields."""
    markdown = """## Section 1: Test

Some content here.
"""
    filePath = Path("transport.md")

    chunks = splitIntoChunks(markdown, filePath)

    for chunk in chunks:
        assert isinstance(chunk["text"], str)
        assert len(chunk["text"]) > 0
        assert chunk["file"] == "transport.md"
        assert chunk["category"] == "transport"
        assert chunk["section"] != ""


def testAllPolicyFilesAreParseable():
    """Test that all policy files in the directory can be parsed without errors."""
    policyDir = Path(__file__).parent.parent / "src" / "agentic_claims" / "policy"

    # Check directory exists
    assert policyDir.exists(), f"Policy directory {policyDir} does not exist"

    policyFiles = list(policyDir.glob("*.md"))
    assert len(policyFiles) > 0, "No policy files found"

    # Parse all policy files
    for policyFile in policyFiles:
        content = policyFile.read_text(encoding="utf-8")
        chunks = splitIntoChunks(content, policyFile)

        # Basic checks
        assert len(chunks) > 0, f"No chunks created from {policyFile.name}"
        assert all("text" in c for c in chunks), f"Missing 'text' in chunks from {policyFile.name}"
        assert all(
            "category" in c for c in chunks
        ), f"Missing 'category' in chunks from {policyFile.name}"


def testLongSectionSplitsWithOverlap():
    """Test that sections longer than MAX_CHUNK_WORDS are split."""
    # Create a long section (> 400 words)
    longSection = "word " * 500  # 500 words
    markdown = f"""## Section 1: Long Section

{longSection}
"""
    filePath = Path("test.md")

    chunks = splitIntoChunks(markdown, filePath)

    # Should have multiple chunks for the long section
    sectionChunks = [c for c in chunks if "Long Section" in c["section"]]
    assert len(sectionChunks) > 1, "Long section should be split into multiple chunks"

    # Check part numbering
    for idx, chunk in enumerate(sectionChunks):
        if len(sectionChunks) > 1:
            assert "part" in chunk["section"], f"Chunk {idx} should have 'part' in section name"


def testEmptyOrWhitespaceContent():
    """Test handling of empty or whitespace-only markdown."""
    markdown = """


"""
    filePath = Path("empty.md")

    chunks = splitIntoChunks(markdown, filePath)

    # Should handle gracefully (may return 0 or minimal chunks)
    assert isinstance(chunks, list)
