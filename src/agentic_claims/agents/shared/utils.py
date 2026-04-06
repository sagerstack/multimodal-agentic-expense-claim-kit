"""Shared utility functions for agent nodes."""

import re


def extractJsonBlock(text: str) -> str | None:
    """Extract the first JSON object from an LLM response string.

    Handles both ```json fenced blocks and raw inline JSON objects.

    Args:
        text: Raw LLM response text

    Returns:
        JSON string or None if no JSON object found
    """
    # 1. Try fenced code block: ```json { ... } ```
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)

    # 2. Try bare JSON object spanning the whole string
    raw = re.search(r"\{.*\}", text, re.DOTALL)
    if raw:
        return raw.group(0)

    return None
