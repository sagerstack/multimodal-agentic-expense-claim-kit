"""Browser E2E coverage for the current intake-gpt slices.

These tests drive the real web UI with Playwright against the live app.

Prerequisites:
  - app running at http://localhost:8000
  - INTAKE_AGENT_MODE=gpt set in the app environment
  - valid login credentials available for user sagar / sagar123
  - browser dependencies installed: `playwright install chromium`

Scope intentionally matches the current intake-gpt implementation boundary:
  - restaurant receipt happy path only validates through extraction + confirmation prompt
  - VND/manual-FX browser flow is documented as the next slice and marked xfail
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright


APP_URL = os.environ.get("INTAKE_E2E_APP_URL", "http://localhost:8000")
RESTAURANT_RECEIPT = Path("artifacts/receipts/receipt-pass-restaurant.jpeg")
VND_RECEIPT = Path("artifacts/receipts/vietnamese_receipts.jpg")
USERNAME = os.environ.get("INTAKE_E2E_USERNAME", "sagar")
PASSWORD = os.environ.get("INTAKE_E2E_PASSWORD", "sagar123")


def _require_services_up() -> None:
    try:
        response = httpx.get(f"{APP_URL}/login", timeout=5.0, follow_redirects=False)
    except Exception as exc:  # pragma: no cover - exercised only in live E2E runs
        pytest.fail(f"App not reachable at {APP_URL}: {exc}")
    if response.status_code not in (200, 302):
        pytest.fail(f"Unexpected status from {APP_URL}/login: {response.status_code}")


def _login(page) -> None:
    page.goto(f"{APP_URL}/login", wait_until="networkidle")
    page.locator('input[name="username"]').fill(USERNAME)
    page.locator('input[name="password"]').fill(PASSWORD)
    # no_wait_after=True avoids Playwright blocking on the long-lived SSE
    # stream that the chat page opens immediately after redirect.
    page.get_by_role("button", name="Sign In").click(no_wait_after=True)
    page.wait_for_url(f"{APP_URL}/", timeout=60_000)
    page.locator("#chatHistory").wait_for(state="visible", timeout=30_000)


def _upload_receipt(page, receipt_path: Path, prompt: str) -> None:
    page.locator('textarea[name="message"]').fill(prompt)
    page.locator('input[name="receipt"]').set_input_files(str(receipt_path.resolve()))
    page.locator('#chatForm button[type="submit"]').click()


def _send_text_message(page, text: str) -> None:
    """Type a text message and submit the chat form."""
    page.locator('textarea[name="message"]').fill(text)
    page.locator('#chatForm button[type="submit"]').click()


def _interrupt_button_count(page) -> int:
    """Return the total number of Yes-button instances visible in chat history.

    `freezeTurn()` clones the interrupt content (Yes/No buttons) into the static
    frozen history and clears #interruptTarget. So after each completed turn, the
    buttons live in frozen divs before #thinkingPanel, NOT in #interruptTarget.

    Each re-presentation of an interrupt adds one more pair of buttons to the frozen
    history. We use the count to verify re-presentation: after a side question, the
    count must increase by at least 1 compared to before the side question.
    """
    return page.locator('button[data-value="yes"]').count()


def _click_latest_yes_button(page) -> None:
    """Click the most recently rendered Yes button (last in document order)."""
    page.locator('button[data-value="yes"]').last.click()


def _wait_for_interrupt_buttons(page, timeout_ms: int = 30_000) -> bool:
    """Wait until at least one Yes button exists in the page. Returns True if found."""
    try:
        page.locator('button[data-value="yes"]').first.wait_for(
            state="visible", timeout=timeout_ms
        )
        return True
    except Exception:
        return False


def _wait_for_processing_to_finish(page) -> None:
    page.locator("#thinkingPanel").wait_for(state="visible", timeout=30_000)
    page.locator("#thinkingPanel").wait_for(state="hidden", timeout=300_000)


def _chat_text(page) -> str:
    return page.locator("#chatHistory").inner_text()


def _print_turn(label: str, page) -> str:
    """Print the full chat history at a turn boundary and return it.

    Always prints regardless of pass/fail so agent responses are visible in
    pytest -s output. Returns the history text so callers can reuse it.
    """
    history = _chat_text(page)
    divider = "─" * 72
    print(f"\n{divider}")
    print(f"[{label}] chat history ({len(history)} chars):")
    print(divider)
    print(history[-1200:] if len(history) > 1200 else history)
    print(divider)
    return history


def _latest_ai_markdown_table(page):
    return page.locator(".ai-markdown table").last


@pytest.mark.e2e
def test_browser_restaurant_receipt_renders_table_and_confirmation():
    """Current browser slice: upload restaurant receipt -> table + confirmation prompt."""
    assert RESTAURANT_RECEIPT.exists(), f"Missing receipt fixture: {RESTAURANT_RECEIPT}"
    _require_services_up()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        try:
            _login(page)
            _upload_receipt(
                page,
                RESTAURANT_RECEIPT,
                "Here is my lunch receipt from DIG restaurant.",
            )
            _wait_for_processing_to_finish(page)

            history = _chat_text(page)
            table = _latest_ai_markdown_table(page)

            if table.count():
                table.wait_for(state="visible", timeout=30_000)
                header_text = table.locator("thead").inner_text().lower()
                body_text = table.locator("tbody").inner_text()
                assert "field" in header_text and "value" in header_text and "confidence" in header_text
                assert "Merchant" in body_text and "DIG" in body_text
            else:
                flattened_history = history.lower()
                assert "field" in flattened_history and "value" in flattened_history and "confidence" in flattened_history
                assert "merchant" in flattened_history and "dig" in flattened_history

            assert "Merchant" in history and "DIG" in history
            confirmation_prompts = (
                "Does the extracted receipt information look correct?",
                "Please confirm if the extracted receipt details are correct.",
                "Do the extracted receipt details look correct?",
            )
            assert any(prompt in history for prompt in confirmation_prompts)

            assert "```json" not in history
            assert '"fields"' not in history
            assert '"confidence"' not in history

            thinking_panel = page.locator("#thinkingPanel")
            assert thinking_panel.count() == 1
        finally:
            browser.close()


@pytest.mark.e2e
def test_browser_restaurant_receipt_renders_table_and_confirmation_with_early_policy_sideq():
    """Upload receipt → policy side question → searchPolicies called → field_confirmation re-presented.

    Extends the basic confirmation test with one side question that requires a policy
    lookup before the user has clicked Yes/No on field_confirmation.

    Turn 1: upload DIG restaurant receipt
            → agent extracts fields, renders table, presents field_confirmation (Yes/No)
    Turn 2: ask "what is my daily meal allowance"
            → agent calls searchPolicies (policy lookup)
            → agent answers with SGD amounts from the meals policy
            → field_confirmation re-presented (button count must increase)

    Key assertion: button count after Turn 2 > button count after Turn 1, proving
    that the pending field_confirmation interrupt survived the side question and was
    re-shown after the policy answer, rather than being silently dropped.
    """
    assert RESTAURANT_RECEIPT.exists(), f"Missing receipt fixture: {RESTAURANT_RECEIPT}"
    _require_services_up()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        try:
            _login(page)

            # ── Turn 1: upload DIG restaurant receipt ─────────────────────────
            _upload_receipt(
                page,
                RESTAURANT_RECEIPT,
                "Here is my lunch receipt from DIG restaurant.",
            )
            _wait_for_processing_to_finish(page)

            history = _print_turn("Turn 1 — after upload", page)
            table = _latest_ai_markdown_table(page)

            # Verify extraction rendered — either as a markdown table or as prose.
            flattened = history.lower()
            if table.count():
                table.wait_for(state="visible", timeout=30_000)
                body_text = table.locator("tbody").inner_text()
                assert "DIG" in body_text, "FAIL Turn 1: DIG not in extraction table"
            else:
                # Agent rendered prose — check for merchant name and at least one
                # other receipt field (date or amount) to confirm extraction ran.
                assert "dig" in flattened, "FAIL Turn 1: DIG not in prose extraction"
                assert any(kw in flattened for kw in ["date", "amount", "total", "merchant"]), (
                    "FAIL Turn 1: no receipt fields found in prose extraction"
                )

            # Confirmation prompt — accept any reasonable phrasing
            confirmation_keywords = [
                "confirm", "correct", "look right", "accurate", "verify", "details"
            ]
            assert any(kw in flattened for kw in confirmation_keywords), (
                f"FAIL Turn 1: no confirmation prompt in history\n{history[-400:]}"
            )

            # field_confirmation Yes/No buttons must be visible
            assert _wait_for_interrupt_buttons(page), (
                "FAIL Turn 1: field_confirmation Yes/No buttons did not appear"
            )
            history_after_t1 = history
            btn_count_after_t1 = _interrupt_button_count(page)
            print(f"[Turn 1] Yes-button count: {btn_count_after_t1}")

            # ── Turn 2: policy side question while field_confirmation is pending ──
            _send_text_message(page, "what is my daily meal allowance")
            _wait_for_processing_to_finish(page)

            history = _print_turn("Turn 2 — after policy side question", page)
            page_html = page.content()

            # Assertion 1: searchPolicies tool was called.
            # When searchPolicies completes, sseHelpers emits a STEP_CONTENT div
            # via _summarizeToolOutput: "Found N relevant policy clause(s)".
            # That text is appended (beforeend) into #thinkingContent and survives
            # in the frozen thinking panel DOM after the stream ends.
            # "searchPolicies" itself never appears literally in the page HTML.
            assert "policy clause" in page_html, (
                "FAIL Turn 2: searchPolicies was not called — "
                "'policy clause' not found in page DOM (tool summary never emitted)\n"
                f"Last 800 chars of history:\n{history[-800:]}"
            )

            # Assertion 2: a response was provided.
            # History must have grown meaningfully since Turn 1.
            history_growth = len(history) - len(history_after_t1)
            assert history_growth > 50, (
                f"FAIL Turn 2: agent response too short or absent "
                f"(history grew by only {history_growth} chars)\n"
                f"Last 800 chars:\n{history[-800:]}"
            )

            # Assertion 3: field_confirmation re-presented.
            # Button count must increase — the pending interrupt survived the side question.
            btn_count_after_t2 = _interrupt_button_count(page)
            print(f"[Turn 2] Yes-button count: {btn_count_after_t2} (was {btn_count_after_t1})")
            assert btn_count_after_t2 > btn_count_after_t1, (
                f"FAIL Turn 2: field_confirmation was NOT re-presented after policy side question\n"
                f"Button count before={btn_count_after_t1}, after={btn_count_after_t2}"
            )

            # ── Turn 3: click Yes → policy check should detect a violation ────────
            # The DIG receipt is USD 16.20 → SGD 20.62. The lunch cap is SGD 20.00.
            # SGD 20.62 > SGD 20.00 is a violation — the agent must ask for justification,
            # NOT present a submit_confirmation (Yes/No) prompt.
            _click_latest_yes_button(page)
            _wait_for_processing_to_finish(page)

            history = _print_turn("Turn 3 — after Yes on field_confirmation", page)
            btn_count_after_t3 = _interrupt_button_count(page)
            print(f"[Turn 3] Yes-button count: {btn_count_after_t3} (was {btn_count_after_t2})")

            # Assertion 4: violation detected.
            # The agent must mention the violation — the converted amount SGD 20.62 exceeds
            # the lunch cap SGD 20.00, so the response must contain language about exceeding
            # the limit or requesting justification.
            violation_keywords = [
                "exceed", "violation", "violat", "justif", "over the", "above the",
                "limit", "cap", "20.00", "20.62",
            ]
            flattened_t3 = history.lower()
            assert any(kw in flattened_t3 for kw in violation_keywords), (
                f"FAIL Turn 3: no violation language found — agent missed that SGD 20.62 > SGD 20 lunch cap\n"
                f"Keywords checked: {violation_keywords}\n"
                f"Last 600 chars of history:\n{history[-600:]}"
            )

            # Assertion 5: no new submit_confirmation Yes/No buttons.
            # On the violation path the agent emits policy_justification (a text
            # prompt, no Yes/No buttons).  Clicking Yes on field_confirmation removes
            # the active interruptTarget button (−1); freezeTurn() may copy it into
            # static history (+1), giving a net-zero change.  Either way the count
            # must NOT INCREASE — if it does, submit_confirmation fired instead
            # (wrong path, violation was not detected).
            assert btn_count_after_t3 <= btn_count_after_t2, (
                f"FAIL Turn 3: button count INCREASED — violation was NOT detected\n"
                f"(expected policy_justification text prompt with no new Yes/No buttons)\n"
                f"Button count before={btn_count_after_t2}, after={btn_count_after_t3}\n"
                f"Last 600 chars of history:\n{history[-600:]}"
            )

            # ── Turn 4: provide justification → submit_confirmation appears ────────
            _send_text_message(
                page, "This was a team lunch for a project meeting — expenses exceeded cap."
            )
            _wait_for_processing_to_finish(page)

            history = _print_turn("Turn 4 — after justification", page)
            btn_count_after_t4 = _interrupt_button_count(page)
            print(f"[Turn 4] Yes-button count: {btn_count_after_t4}")

            # After justification, the agent should present submit_confirmation (Yes/No).
            # Button count must have increased from Turn 3.
            assert btn_count_after_t4 > btn_count_after_t3, (
                f"FAIL Turn 4: submit_confirmation buttons did not appear after justification\n"
                f"Button count before={btn_count_after_t3}, after={btn_count_after_t4}\n"
                f"Last 600 chars of history:\n{history[-600:]}"
            )

            # ── Turn 5: click Yes on submit_confirmation → CLAIM number returned ──
            _click_latest_yes_button(page)
            _wait_for_processing_to_finish(page)

            history = _print_turn("Turn 5 — after submit_confirmation Yes", page)

            # Acceptance criteria: a CLAIM-XXX number must appear in the chat history.
            # This confirms the claim was persisted to the database.
            assert any(kw in history.upper() for kw in ["CLAIM-", "CLM-"]), (
                f"FAIL Turn 5: no CLAIM number in chat history — claim was not submitted to DB\n"
                f"Last 800 chars of history:\n{history[-800:]}"
            )
        finally:
            browser.close()


@pytest.mark.e2e
def test_browser_side_question_full_conversation():
    """Full intake-gpt conversation: upload -> 2 side questions -> Yes -> submit.

    Validates the side question handling fix:
      1. Side question answers appear visibly in chat history
      2. The pending interrupt (field_confirmation) is re-presented after each answer
         (detected by Yes button count increasing by 1 per turn)
      3. Clicking Yes advances the workflow correctly (no premature step jump)
      4. A side question during submit_confirmation is answered then the prompt re-appears
      5. Final Yes submits the claim and a claim number is returned

    This test will FAIL on un-fixed code (that is its purpose: capture the bug
    in a reproducible, automated assertion before implementing the fix).

    Note on button location: `freezeTurn()` clones interrupt buttons into the static
    chat history and clears #interruptTarget. Buttons are found globally via
    `button[data-value="yes"]`, using .last for the most recent interrupt.
    """
    assert RESTAURANT_RECEIPT.exists(), f"Missing receipt fixture: {RESTAURANT_RECEIPT}"
    _require_services_up()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        try:
            _login(page)

            # ── Turn 1: upload DIG restaurant receipt ──────────────────────────
            _upload_receipt(
                page,
                RESTAURANT_RECEIPT,
                "Here is my lunch receipt from DIG restaurant.",
            )
            _wait_for_processing_to_finish(page)

            # field_confirmation buttons must be present (frozen into history)
            assert _wait_for_interrupt_buttons(page), (
                "FAIL Turn 1: field_confirmation Yes/No buttons did not appear after receipt upload"
            )
            btn_count_after_t1 = _interrupt_button_count(page)
            history = _chat_text(page)
            assert "DIG" in history, (
                f"FAIL Turn 1: DIG merchant not found in chat history\n{history[-500:]}"
            )

            # ── Turn 2: side question while field_confirmation is pending ──────
            _send_text_message(page, "is this a valid receipt?")
            _wait_for_processing_to_finish(page)

            history = _chat_text(page)
            # The answer must appear somewhere in the visible chat
            assert any(
                kw in history.lower()
                for kw in ["valid", "receipt", "yes", "acceptable", "legitimate", "original", "real"]
            ), (
                f"FAIL Turn 2: side question answer 'is this a valid receipt?' not visible\n"
                f"Last 800 chars of history:\n{history[-800:]}"
            )
            # field_confirmation must be re-presented (button count must increase)
            btn_count_after_t2 = _interrupt_button_count(page)
            assert btn_count_after_t2 > btn_count_after_t1, (
                f"FAIL Turn 2: field_confirmation was NOT re-presented after side question\n"
                f"Button count before={btn_count_after_t1}, after={btn_count_after_t2}"
            )

            # ── Turn 3: second side question (policy/approval) ─────────────────
            _send_text_message(page, "who will approve it?")
            _wait_for_processing_to_finish(page)

            history = _chat_text(page)
            assert any(
                kw in history.lower()
                for kw in ["approv", "manager", "head", "supervisor", "finance", "department", "hod"]
            ), (
                f"FAIL Turn 3: side question answer 'who will approve it?' not visible\n"
                f"Last 800 chars of history:\n{history[-800:]}"
            )
            btn_count_after_t3 = _interrupt_button_count(page)
            assert btn_count_after_t3 > btn_count_after_t2, (
                f"FAIL Turn 3: field_confirmation was NOT re-presented after approval side question\n"
                f"Button count before={btn_count_after_t2}, after={btn_count_after_t3}"
            )

            # ── Turn 4: click Yes → advances to policy check ───────────────────
            _click_latest_yes_button(page)
            _wait_for_processing_to_finish(page)

            history = _chat_text(page)
            btn_count_after_t4 = _interrupt_button_count(page)

            # Determine which path: submit_confirmation (buttons) or policy_justification (text)
            if btn_count_after_t4 > btn_count_after_t3:
                # New Yes buttons appeared → submit_confirmation (compliant receipt)
                assert any(
                    kw in history.lower()
                    for kw in ["policy", "compliant", "submit", "confirm", "proceed", "within"]
                ), (
                    f"FAIL Turn 4: submit_confirmation context not found\n"
                    f"Last 500:\n{history[-500:]}"
                )

                # ── Turn 5: side question during submit_confirmation ───────────
                _send_text_message(page, "who will approve this?")
                _wait_for_processing_to_finish(page)

                history = _chat_text(page)
                assert any(
                    kw in history.lower()
                    for kw in ["approv", "manager", "head", "supervisor", "finance", "department", "hod"]
                ), (
                    f"FAIL Turn 5: approval answer not visible during submit_confirmation\n"
                    f"Last 800 chars:\n{history[-800:]}"
                )
                btn_count_after_t5 = _interrupt_button_count(page)
                assert btn_count_after_t5 > btn_count_after_t4, (
                    f"FAIL Turn 5: submit_confirmation not re-presented after side question\n"
                    f"Button count before={btn_count_after_t4}, after={btn_count_after_t5}"
                )

                # ── Turn 6: click Yes → submit ─────────────────────────────────
                _click_latest_yes_button(page)
                _wait_for_processing_to_finish(page)

            else:
                # No new buttons → policy_justification (receipt exceeded policy limit)
                # ── Turn 5 (violation path): side question during justification ─
                _send_text_message(page, "who will approve this?")
                _wait_for_processing_to_finish(page)

                history = _chat_text(page)
                assert any(
                    kw in history.lower()
                    for kw in ["approv", "manager", "head", "supervisor", "finance", "department", "hod"]
                ), (
                    f"FAIL Turn 5 (violation): approval answer not visible during justification\n"
                    f"Last 800 chars:\n{history[-800:]}"
                )

                # ── Turn 6: provide justification ─────────────────────────────
                _send_text_message(
                    page, "This was a team lunch for a project planning session."
                )
                _wait_for_processing_to_finish(page)

                # If submit_confirmation follows, click Yes
                if _interrupt_button_count(page) > btn_count_after_t4:
                    _click_latest_yes_button(page)
                    _wait_for_processing_to_finish(page)

            # ── Final assertion: claim submission acknowledged ─────────────────
            history = _chat_text(page)
            assert any(
                kw in history.upper()
                for kw in ["CLAIM-", "CLM-", "SUBMITTED", "REFERENCE", "CONFIRMED", "ACKNOWLEDGMENT"]
            ), (
                f"FAIL Final: claim number / submission confirmation not found\n"
                f"Last 1000 chars of history:\n{history[-1000:]}"
            )

        finally:
            browser.close()


@pytest.mark.e2e
@pytest.mark.xfail(
    reason="intake-gpt manual-FX interrupt slice is not implemented in the browser path yet",
    strict=False,
)
def test_browser_vnd_receipt_reaches_manual_fx_prompt():
    """Next browser slice: upload VND receipt -> ask for manual FX rate."""
    assert VND_RECEIPT.exists(), f"Missing receipt fixture: {VND_RECEIPT}"
    _require_services_up()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 960})
        try:
            _login(page)
            _upload_receipt(
                page,
                VND_RECEIPT,
                "Please process this receipt from Vietnam.",
            )
            _wait_for_processing_to_finish(page)

            history = _chat_text(page)
            assert "exchange rate" in history.lower()
            assert "sgd" in history.lower()
            assert "```json" not in history
        finally:
            browser.close()
