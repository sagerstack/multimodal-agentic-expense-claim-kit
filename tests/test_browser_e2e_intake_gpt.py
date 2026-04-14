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
    page.get_by_role("button", name="Sign In").click()
    page.wait_for_url(f"{APP_URL}/")
    page.locator("#chatHistory").wait_for(state="visible", timeout=30_000)


def _upload_receipt(page, receipt_path: Path, prompt: str) -> None:
    page.locator('textarea[name="message"]').fill(prompt)
    page.locator('input[name="receipt"]').set_input_files(str(receipt_path.resolve()))
    page.locator('#chatForm button[type="submit"]').click()


def _wait_for_processing_to_finish(page) -> None:
    page.locator("#thinkingPanel").wait_for(state="visible", timeout=30_000)
    page.locator("#thinkingPanel").wait_for(state="hidden", timeout=120_000)


def _chat_text(page) -> str:
    return page.locator("#chatHistory").inner_text()


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
