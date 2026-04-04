"""Server-side employee ID extraction from user messages."""

import re


def extractEmployeeId(text: str) -> str | None:
    """Extract employee ID from free-text user message.

    Strategy:
    1. Explicit patterns: EMP-XXX, EMPXXX, or any ALPHA-DIGITS pattern
    2. Contextual: "employee id" / "ID:" followed by alphanumeric
    3. "employee" followed by a bare number
    4. Last match wins (user correction pattern)

    Returns uppercase ID string or None.
    """
    matches: list[str] = []

    # Pattern 1: ALPHA-DIGITS (e.g., EMP-042, ABC-123)
    for m in re.finditer(r"\b([A-Za-z]{2,5})-(\d+)\b", text):
        full = m.group(0)
        # Skip dollar amounts like $45.20
        start = m.start()
        if start > 0 and text[start - 1] == "$":
            continue
        matches.append(full.upper())

    # Pattern 2: ALPHA+DIGITS no dash (e.g., EMP001)
    for m in re.finditer(r"\b([A-Za-z]{2,5})(\d{2,})\b", text):
        candidate = m.group(0).upper()
        if candidate not in matches:
            matches.append(candidate)

    # Pattern 3: "ID:" or "employee id" followed by alphanumeric (may include dash)
    for m in re.finditer(r"(?:employee\s+id|ID)\s*[:.]?\s*([\w][\w-]*\w|\w+)", text, re.IGNORECASE):
        candidate = m.group(1)
        # Skip if it's a common word
        if candidate.lower() in ("is", "my", "the", "a", "an"):
            continue
        # If purely numeric or alphanumeric, it's a candidate
        if re.match(r"^[A-Za-z0-9-]+$", candidate):
            normalized = candidate.upper() if re.search(r"[A-Za-z]", candidate) else candidate
            if normalized not in matches:
                matches.append(normalized)

    # Pattern 4: "employee" followed by bare number
    for m in re.finditer(r"\bemployee\s+(\d+)\b", text, re.IGNORECASE):
        candidate = m.group(1)
        if candidate not in matches:
            matches.append(candidate)

    if not matches:
        return None

    # Last match wins (user correction pattern)
    return matches[-1]
