"""Backend tests for Phase 14 Yes/No button interrupts."""

from pathlib import Path

from agentic_claims.agents.intake_gpt.tools.requestHumanInput import (
    _BUTTON_INTERRUPT_KINDS,
    _deriveButtonOptions,
    _deriveUiKind,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_PATH = _REPO_ROOT / "templates" / "partials" / "interrupt_buttons.html"


def test_deriveUiKindReturnsButtonsForFieldConfirmation():
    assert _deriveUiKind("field_confirmation") == "buttons"


def test_deriveUiKindReturnsButtonsForSubmitConfirmation():
    assert _deriveUiKind("submit_confirmation") == "buttons"


def test_deriveUiKindReturnsTextForPolicyJustification():
    assert _deriveUiKind("policy_justification") == "text"


def test_deriveUiKindReturnsTextForManualFxRate():
    assert _deriveUiKind("manual_fx_rate") == "text"


def test_deriveButtonOptionsReturnsYesNoForButtonKinds():
    for kind in _BUTTON_INTERRUPT_KINDS:
        opts = _deriveButtonOptions(kind)
        labels = [o["label"] for o in opts]
        values = [o["value"] for o in opts]
        assert labels == ["Yes", "No"], f"{kind}: {labels}"
        assert values == ["yes", "no"], f"{kind}: {values}"


def test_deriveButtonOptionsReturnsEmptyForTextKinds():
    assert _deriveButtonOptions("policy_justification") == []
    assert _deriveButtonOptions("manual_fx_rate") == []


def test_interruptButtonsPartialRendersYesNoButtons():
    """Partial template renders both Yes and No buttons with correct form fields.

    Template path is resolved relative to __file__ so the test passes regardless
    of pytest's invocation working directory.
    """
    assert _TEMPLATE_PATH.exists(), (
        f"Template file not found at {_TEMPLATE_PATH} — did Plan 14-04 Task 1b run?"
    )

    from agentic_claims.web.templating import templates

    template = templates.get_template("partials/interrupt_buttons.html")
    html = template.render(
        question="Do these extracted details look correct?",
        options=[
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    )
    assert "Do these extracted details look correct?" in html
    assert ">Yes</button>" in html
    assert ">No</button>" in html
    assert 'name="button_value"' in html
    assert 'value="yes"' in html
    assert 'value="no"' in html
    assert 'hx-post="/chat/message"' in html
