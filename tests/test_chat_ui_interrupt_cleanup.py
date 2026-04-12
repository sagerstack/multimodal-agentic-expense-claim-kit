"""Tests for interrupt-target DOM cleanup + neutral styling on new turn (Plan 13-11 gap closure)."""

from pathlib import Path


def _readChatTemplate() -> str:
    return (Path(__file__).parent.parent / "templates" / "chat.html").read_text()


def test_interruptTargetIsClearedOnNewTurn():
    """Regression: #interruptTarget.innerHTML must be reset when a new turn starts.

    Fix direction (13-DEBUG-display-regression.md "Fix B"): clearing must happen on
    EITHER submitForm() OR the thinking-start SSE handler. Presence in either site
    satisfies this test.
    """
    html = _readChatTemplate()
    # We look for any of the canonical clearing patterns.
    candidates = [
        "document.getElementById('interruptTarget').innerHTML = ''",
        'document.getElementById("interruptTarget").innerHTML = ""',
        "interruptTarget.innerHTML = ''",
        'interruptTarget.innerHTML = ""',
    ]
    assert any(c in html for c in candidates), (
        "templates/chat.html must clear #interruptTarget on new turn. "
        "Expected one of the following patterns to appear in either submitForm() "
        "or the thinking-start handler:\n" + "\n".join(candidates)
    )


def test_interruptTargetStillHasSseSwap():
    """Guard: the existing HTMX sse-swap contract is preserved (not accidentally removed)."""
    html = _readChatTemplate()
    assert 'id="interruptTarget"' in html
    assert 'sse-swap="interrupt"' in html
    assert 'hx-swap="innerHTML"' in html


def test_interruptTargetUsesNeutralAgentStyling():
    """Regression (13-DEBUG-display-regression.md "Related issues" §1):
    #interruptTarget must NOT use the error-looking red-italic palette. It must
    mirror the neutral agent-bubble palette defined in partials/message_bubble.html
    (bg-surface-container-low + text-on-surface + border-outline-variant/5), so
    routine askHuman prompts are not confused with errors.
    """
    html = _readChatTemplate()
    # Isolate the #interruptTarget element by locating its id and grabbing its tag.
    import re
    match = re.search(r'<div\s+id="interruptTarget"[^>]*>', html)
    assert match is not None, "#interruptTarget element not found in template"
    tag = match.group(0)

    # Forbidden classes (the old error-looking palette).
    forbidden = ["italic", "text-tertiary", "bg-tertiary/5", "border-tertiary/10"]
    for cls in forbidden:
        assert cls not in tag, (
            f"#interruptTarget still carries forbidden class '{cls}'. "
            f"Expected neutral agent-bubble palette. Got tag: {tag}"
        )

    # Required classes (mirror partials/message_bubble.html AI bubble).
    required = ["bg-surface-container-low", "text-on-surface", "empty:hidden"]
    for cls in required:
        assert cls in tag, (
            f"#interruptTarget missing required neutral-palette class '{cls}'. "
            f"Expected parity with partials/message_bubble.html. Got tag: {tag}"
        )
