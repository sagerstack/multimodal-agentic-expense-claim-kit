"""Playwright-driven benchmark capture runner.

Drives the real web UI with Playwright to capture benchmark results from the
live app. Replaces the claude-code-sdk subagent approach with a direct sync
Playwright script that follows the same patterns as tests/test_browser_e2e_intake_gpt.py.

This module is fully decoupled from the app -- no imports from agentic_claims.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional

from eval.src.config import EvalConfig
from eval.src.dataset import Benchmark

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON extraction helpers (retained from original implementation)
# ---------------------------------------------------------------------------


def _tryParseJson(text: str) -> Optional[dict]:
    """Attempt JSON parsing. Returns dict or None."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _extractFirstJsonObject(text: str) -> Optional[dict]:
    """Find and parse the first balanced JSON object in arbitrary text."""
    startIdx = text.find("{")
    if startIdx == -1:
        return None

    depth = 0
    inString = False
    escapeNext = False

    for idx in range(startIdx, len(text)):
        ch = text[idx]
        if escapeNext:
            escapeNext = False
            continue
        if ch == "\\" and inString:
            escapeNext = True
            continue
        if ch == '"':
            inString = not inString
            continue
        if inString:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[startIdx : idx + 1]
                return _tryParseJson(candidate)
    return None


def _buildErrorResult(benchmark: Benchmark, errorMessage: str) -> dict:
    """Build a partial error result for a benchmark that failed capture."""
    return {
        "benchmarkId": benchmark["benchmarkId"],
        "benchmark": benchmark["benchmark"],
        "category": benchmark["category"],
        "file": benchmark["file"],
        "scoringType": benchmark["scoringType"],
        "captureError": errorMessage,
        "capture": {
            "claimId": None,
            "conversationTranscript": [],
            "extractedFields": None,
            "agentDecision": None,
            "complianceFindings": None,
            "fraudFindings": None,
            "advisorReasoning": None,
            "retrievedPolicyChunks": [],
        },
        "expected": {
            "expectedDecision": benchmark["expectedDecision"],
            "passCriteria": benchmark["passCriteria"],
            "companionMetadata": benchmark.get("companionMetadata"),
        },
    }


# ---------------------------------------------------------------------------
# Playwright helper functions (follow E2E test patterns)
# ---------------------------------------------------------------------------


def _loginPlaywright(page, config: EvalConfig) -> None:
    """Log in to the app and wait for the chat page to be ready.

    Raises RuntimeError with a clear message if login fails (wrong credentials
    or login page error) rather than letting Playwright time out.
    """
    page.goto(f"{config.appUrl}/login", wait_until="networkidle")
    page.locator('input[name="username"]').fill(config.evalUsername)
    page.locator('input[name="password"]').fill(config.evalPassword)
    # no_wait_after=True avoids blocking on the long-lived SSE stream that
    # the chat page opens immediately after redirect.
    page.get_by_role("button", name="Sign In").click(no_wait_after=True)

    # Wait up to 15s for the URL to leave /login.  If it doesn't move, the
    # credentials are invalid — surface a clear error instead of a 60s timeout.
    try:
        page.wait_for_url(f"{config.appUrl}/", timeout=15_000)
    except Exception:
        currentUrl = page.url
        if "login" in currentUrl:
            raise RuntimeError(
                f"Login failed for user '{config.evalUsername}'. "
                "Check EVAL_USERNAME / EVAL_PASSWORD env vars."
            )
        raise

    page.locator("#chatHistory").wait_for(state="visible", timeout=30_000)


def _buildUserMessage(benchmark: Benchmark) -> str:
    """Compose the initial user message for a benchmark.

    Includes the scenario description and, when present, the `companionMetadata`
    formatted as an "Additional context" JSON block so the agent has access to
    reference data (expense entries, approval thresholds, report headers,
    policy windows, etc.) that would otherwise never reach its context.
    """
    parts = [f"Please process this receipt: {benchmark['scenario']}"]

    companion = benchmark.get("companionMetadata")
    if companion:
        companionJson = json.dumps(companion, indent=2, default=str)
        parts.append(
            "\n\nAdditional context for this claim (use this to inform your "
            "analysis — do not ignore these values):\n"
            f"```json\n{companionJson}\n```"
        )

    question = benchmark.get("question")
    if question:
        parts.append(f"\n\nQuestion you must answer: {question}")

    return "".join(parts)


def _uploadAndSubmit(page, config: EvalConfig, benchmark: Benchmark) -> None:
    """Upload the benchmark receipt and submit the initial message."""
    receiptPath = str(config.invoicesDir / benchmark["file"])
    userMessage = _buildUserMessage(benchmark)

    # The file input is hidden — set files directly (matches E2E test pattern)
    page.locator('input[name="receipt"]').set_input_files(receiptPath)
    page.locator('textarea[name="message"]').fill(userMessage)
    page.locator('#chatForm button[type="submit"]').click()


def _initDoneCounter(page) -> None:
    """Install a global stream-done event counter on the page.

    The app dispatches a 'stream-done' CustomEvent both when the SSE "done"
    event fires (#doneTarget swap) AND when the SSE "interrupt" event fires
    (#interruptTarget swap).  By counting these events we can wait for exactly
    the NEXT event regardless of whether it's an interrupt or a final done.

    Must be called after login (page is ready) and before form submission.
    """
    page.evaluate("""
        if (typeof window.__evalDoneCount === 'undefined') {
            window.__evalDoneCount = 0;
        }
        if (!window.__evalDoneCounterInstalled) {
            window.addEventListener('stream-done', function() {
                window.__evalDoneCount = (window.__evalDoneCount || 0) + 1;
            });
            window.__evalDoneCounterInstalled = true;
        }
    """)


def _waitForNextStreamDone(page, afterCount: int, timeoutMs: int = 120_000) -> int:
    """Block until a new stream-done event fires OR a claim number appears in chat.

    Exits early when CLAIM-XXXX appears in #chatHistory so we don't wait for
    post-submission agents (compliance/fraud/advisor) to complete. Their output
    is enriched from the DB separately.

    Returns the new counter value so callers can chain subsequent waits.
    """
    page.wait_for_function(
        f"""
        (window.__evalDoneCount || 0) > {afterCount} ||
        /CLAIM-\\d+/i.test(
            (document.getElementById('chatHistory') || {{}}).innerText || ''
        )
        """,
        timeout=timeoutMs,
    )
    return page.evaluate("window.__evalDoneCount || 0")


_JUSTIFICATION_TEXT = "Client dinner."
_CONFIRM_TEXT = "Yes."

# Known fallback exchange rates for currencies the Frankfurter API does not support.
# Values are approximate reference rates for evaluation purposes only.
_FALLBACK_RATES_TO_SGD = {
    "VND": "1 VND = 0.000054 SGD",
    "IDR": "1 IDR = 0.00008 SGD",
    "LAK": "1 LAK = 0.00006 SGD",
    "KHR": "1 KHR = 0.00032 SGD",
    "MMK": "1 MMK = 0.00064 SGD",
}

# Phrases that indicate the agent is asking for a business justification
_JUSTIFICATION_PHRASES = (
    "justification is required",
    "justification before",
    "please explain why",
    "explain why this expense",
    "provide a justification",
    "provide a brief justification",
    "why this expense was necessary",
    # Actual policy_justification interrupt text from requestHumanInput.py:
    "business reason",
    "exceeding the policy cap",
    "describe the business reason",
)

# Phrases that indicate the agent is asking for a yes/no confirmation
_CONFIRM_PHRASES = (
    "would you like",
    "shall i proceed",
    "do you want to submit",
    "please confirm",
    "should i proceed",
    "do you wish to",
    "ready to submit",
    "type 'yes'",
    'type "yes"',
)

# Phrases that indicate the agent is asking the user for a manual exchange rate
# (happens for currencies that the Frankfurter API does not cover, e.g. VND).
_RATE_REQUEST_PHRASES = (
    "exchange rate",
    "conversion rate",
    "share the rate",
    "provide the rate",
    "what is the rate",
    "1 vnd =",
    "1 idr =",
    "1 lak =",
    "1 khr =",
    "1 mmk =",
)


def _detectFallbackRateReply(text: str) -> Optional[str]:
    """Pick a fallback '1 XXX = Y SGD' reply for a currency we recognise.

    Returns the reply string if the agent's message references a currency we
    have a fallback rate for, otherwise None. Scans in order so the most
    specific match wins.
    """
    upper = text.upper()
    for code, reply in _FALLBACK_RATES_TO_SGD.items():
        if code in upper:
            return reply
    return None


def _handleActiveInterrupt(page) -> bool:
    """Respond to an active interrupt in #interruptTarget if present.

    Returns True if an interrupt was detected and responded to.
    Detects two kinds of interrupt:
      - Justification request: responds with a realistic business justification
      - Confirmation (yes/no buttons or plain confirm): responds Yes
    """
    interruptLocator = page.locator("#interruptTarget")
    try:
        interruptText = interruptLocator.inner_text(timeout=500)
    except Exception:
        return False

    if not interruptText.strip():
        return False

    interruptLower = interruptText.strip().lower()

    # Prefer clicking the Yes button if present (submit confirmation interrupt)
    yesButtons = page.locator('button[data-value="yes"]')
    if yesButtons.count():
        yesButtons.last.click()
        return True

    # Justification request — provide a business reason + confirmation in one message
    if any(phrase in interruptLower for phrase in _JUSTIFICATION_PHRASES):
        page.locator('textarea[name="message"]').fill(_JUSTIFICATION_TEXT)
    elif any(phrase in interruptLower for phrase in _RATE_REQUEST_PHRASES):
        fallbackReply = _detectFallbackRateReply(interruptText)
        if fallbackReply:
            page.locator('textarea[name="message"]').fill(fallbackReply)
        else:
            page.locator('textarea[name="message"]').fill(_CONFIRM_TEXT)
    else:
        page.locator('textarea[name="message"]').fill(_CONFIRM_TEXT)

    page.locator('#chatForm button[type="submit"]').click()
    return True


def _handleConversationalConfirm(page) -> bool:
    """Detect and respond to agent confirmation questions sent as regular chat messages.

    Some agents ask "Would you like to proceed?" as a regular AI message rather
    than a LangGraph interrupt. This check reads the last AI message and responds
    if it contains a confirmation prompt — preventing the runner from exiting
    prematurely before the claim is submitted.

    Returns True if a confirmation question was detected and answered.
    """
    # Check if a CLAIM number already appeared — no confirm needed
    try:
        chatText = page.locator("#chatHistory").inner_text(timeout=500)
        if re.search(r"CLAIM-\d+", chatText, re.IGNORECASE):
            return False
    except Exception:
        return False

    try:
        aiElements = page.locator(".ai-markdown").all()
        if not aiElements:
            return False
        lastText = aiElements[-1].inner_text(timeout=500).lower()
    except Exception:
        return False

    # Determine which response to use
    if any(phrase in lastText for phrase in _JUSTIFICATION_PHRASES):
        responseText = _JUSTIFICATION_TEXT
    elif any(phrase in lastText for phrase in _RATE_REQUEST_PHRASES):
        fallbackReply = _detectFallbackRateReply(lastText)
        if not fallbackReply:
            return False
        responseText = fallbackReply
    elif any(phrase in lastText for phrase in _CONFIRM_PHRASES):
        responseText = _CONFIRM_TEXT
    else:
        return False

    try:
        page.locator('textarea[name="message"]').fill(responseText)
        page.locator('#chatForm button[type="submit"]').click()
        return True
    except Exception:
        return False


def _waitForPipelineComplete(page, timeoutMs: int = 480_000) -> None:
    """Wait for the full pipeline to complete, handling interrupts per turn.

    The SSE stream fires a 'stream-done' CustomEvent after EVERY turn, including
    interrupt turns (field_confirmation, submit_confirmation).  Using #doneTarget
    innerHTML alone exits too early because it's populated after the first turn.

    Instead we use a JS event counter installed by _initDoneCounter:
      - Note the current counter value
      - Wait for it to increase (next stream-done event)
      - If #interruptTarget is non-empty: respond to interrupt, loop
      - If no interrupt: pipeline is done for this session

    Raises:
        RuntimeError: If the pipeline emits an error event.
        TimeoutError: If any single turn exceeds timeoutMs.
    """
    MAX_TURNS = 15

    for turn in range(MAX_TURNS):
        # Exit immediately if CLAIM appeared during the previous interrupt handler.
        # Without this check the next _waitForNextStreamDone call could deadlock
        # because the pipeline is already done but the counter has already advanced.
        try:
            chatText = page.locator("#chatHistory").inner_text(timeout=300)
            if re.search(r"CLAIM-\d+", chatText, re.IGNORECASE):
                return
        except Exception:
            pass

        currentCount = page.evaluate("window.__evalDoneCount || 0")

        # Check for pipeline error before waiting
        try:
            errorHtml = page.locator("#errorTarget").inner_html(timeout=300)
            if errorHtml.strip():
                raise RuntimeError(f"Pipeline error: {errorHtml.strip()[:200]}")
        except RuntimeError:
            raise
        except Exception:
            pass

        # Wait for the next stream-done event (interrupt or real done).
        # _handleActiveInterrupt no longer sleeps after responding, so we
        # always reach here with the stream-done counter at a known stable value.
        try:
            _waitForNextStreamDone(page, currentCount, timeoutMs=timeoutMs)
        except Exception:
            raise TimeoutError(
                f"Pipeline did not emit stream-done in turn {turn + 1} "
                f"within {timeoutMs}ms"
            )

        # If a claim number appeared, submission is done — exit before post-submission
        try:
            chatText = page.locator("#chatHistory").inner_text(timeout=300)
            if re.search(r"CLAIM-\d+", chatText, re.IGNORECASE):
                return
        except Exception:
            pass

        # Check for LangGraph interrupt in #interruptTarget
        if _handleActiveInterrupt(page):
            continue

        # Check for conversational confirmation question in the last AI message
        if _handleConversationalConfirm(page):
            continue

        # No interrupt or confirmation — pipeline completed this session
        return

    raise TimeoutError(f"Pipeline did not complete after {MAX_TURNS} turns")


def _extractClaimId(pageText: str) -> Optional[str]:
    """Extract the first CLAIM-XXXX reference from the page text."""
    match = re.search(r"CLAIM-(\d+)", pageText, re.IGNORECASE)
    if match:
        return f"CLAIM-{match.group(1)}"
    return None


def _extractAgentDecision(lastAiMessageText: str) -> str:
    """Return the last AI message text as the agent decision.

    Metrics receive this as agentDecision and search within it for their
    own keywords (e.g. 'receipt', 'duplicate', 'approved').  Returning the
    full message text gives metrics the maximum signal to work with.

    Truncated to 800 chars to stay within deepeval metadata limits.
    """
    return lastAiMessageText.strip()[:800] if lastAiMessageText else ""


def _scrapeResult(page, benchmark: Benchmark) -> dict:
    """Read the final page state and build a structured result dict.

    Extracts:
    - Conversation transcript from .ai-markdown elements (assistant messages)
    - Claim ID via CLAIM-XXXX regex
    - Agent decision = text of the last AI message (metrics search within it)
    """
    chatText = page.locator("#chatHistory").inner_text()

    # Build assistant transcript from rendered AI message elements.
    # After freezeTurn(), messages move from #aiMessages into frozen divs;
    # all carry .ai-markdown class.
    transcript = []
    aiElements = page.locator(".ai-markdown").all()
    for el in aiElements:
        try:
            text = el.inner_text().strip()
            if text:
                transcript.append({"role": "assistant", "content": text})
        except Exception:
            pass

    claimId = _extractClaimId(chatText)

    # agentDecision = last AI message text so metrics can keyword-search within it
    lastMessageText = transcript[-1]["content"] if transcript else chatText[-800:]
    agentDecision = _extractAgentDecision(lastMessageText)

    return {
        "benchmarkId": benchmark["benchmarkId"],
        "benchmark": benchmark["category"],
        "category": benchmark["category"],
        "file": benchmark["file"],
        "scoringType": benchmark["scoringType"],
        "capture": {
            "claimId": claimId,
            "conversationTranscript": transcript,
            "extractedFields": None,
            "agentDecision": agentDecision,
            "complianceFindings": None,
            "fraudFindings": None,
            "advisorReasoning": None,
            "retrievedPolicyChunks": [],
        },
        "expected": {
            "expectedDecision": benchmark["expectedDecision"],
            "passCriteria": benchmark["passCriteria"],
            "companionMetadata": benchmark.get("companionMetadata"),
        },
    }


# ---------------------------------------------------------------------------
# Single benchmark capture (sync Playwright)
# ---------------------------------------------------------------------------


def _runPlaywrightCapture(benchmark: Benchmark, config: EvalConfig) -> dict:
    """Run a single benchmark capture using a real Playwright browser.

    Standard flow:
      1. Login
      2. Upload receipt + submit
      3. Poll until done (handling interrupts)
      4. Scrape output

    Returns structured result dict or error result on failure.
    """
    try:
        from playwright.sync_api import sync_playwright  # deferred import
    except ImportError:
        return _buildErrorResult(benchmark, "playwright not installed (pip install playwright)")

    benchmarkId = benchmark["benchmarkId"]
    receiptPath = config.invoicesDir / benchmark["file"]

    if not receiptPath.exists():
        return _buildErrorResult(
            benchmark, f"Receipt file not found: {benchmark['file']}"
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1536, "height": 960})
            captureError: Optional[str] = None
            try:
                _loginPlaywright(page, config)
                _initDoneCounter(page)  # must be before form submission
                _uploadAndSubmit(page, config, benchmark)
                try:
                    _waitForPipelineComplete(page, timeoutMs=480_000)
                except TimeoutError as turnExc:
                    # Don't abort — scrape whatever is visible on the page.
                    # This preserves the intake conversation even when
                    # post-submission agents (compliance/fraud/advisor) are slow.
                    captureError = f"Timeout: {turnExc}"
                    logger.warning(
                        "_runPlaywrightCapture: timeout for %s — scraping partial result",
                        benchmarkId,
                    )
                result = _scrapeResult(page, benchmark)
                if captureError:
                    result["captureError"] = captureError
                logger.info(
                    "runPlaywrightCapture: %s — turns=%d claimId=%s error=%s",
                    benchmarkId,
                    len(result.get("capture", {}).get("conversationTranscript", [])),
                    result["capture"].get("claimId"),
                    captureError or "none",
                )
                return result
            finally:
                browser.close()

    except RuntimeError as exc:
        return _buildErrorResult(benchmark, f"Pipeline error: {exc}")
    except Exception as exc:
        logger.error("_runPlaywrightCapture: unexpected error for %s: %s", benchmarkId, exc)
        return _buildErrorResult(benchmark, f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# ER-013: Duplicate detection (two-session pattern)
# ---------------------------------------------------------------------------


def _runPlaywrightDuplicateCapture(benchmark: Benchmark, config: EvalConfig) -> dict:
    """Run ER-013 duplicate detection using two browser sessions.

    Session 1: login, upload receipt, complete flow, note claim number.
    Session 2: login again (after /logout), upload same receipt, capture output.
    The second session's output is what we score (duplicate flag should appear).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _buildErrorResult(benchmark, "playwright not installed")

    receiptPath = config.invoicesDir / benchmark["file"]
    if not receiptPath.exists():
        return _buildErrorResult(benchmark, f"Receipt file not found: {benchmark['file']}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1536, "height": 960})
            try:
                # ── Session 1: initial submission ─────────────────────────────
                logger.info("ER-013 Session 1: initial submission")
                _loginPlaywright(page, config)
                _initDoneCounter(page)
                _uploadAndSubmit(page, config, benchmark)
                _waitForPipelineComplete(page, timeoutMs=480_000)

                session1Text = page.locator("#chatHistory").inner_text()
                session1ClaimId = _extractClaimId(session1Text)
                logger.info("ER-013 Session 1 complete. claimId=%s", session1ClaimId)

                # ── Logout to clear session ───────────────────────────────────
                page.goto(f"{config.appUrl}/logout", wait_until="networkidle")

                # ── Session 2: duplicate submission ───────────────────────────
                logger.info("ER-013 Session 2: duplicate submission")
                _loginPlaywright(page, config)
                _initDoneCounter(page)  # reset counter in fresh session
                _uploadAndSubmit(page, config, benchmark)
                _waitForPipelineComplete(page, timeoutMs=480_000)

                result = _scrapeResult(page, benchmark)
                # Attach session 1 claim for reference
                result["capture"]["session1ClaimId"] = session1ClaimId
                logger.info(
                    "ER-013 Session 2 complete. decision=%s claimId=%s",
                    result["capture"].get("agentDecision"),
                    result["capture"].get("claimId"),
                )
                return result

            finally:
                browser.close()

    except TimeoutError as exc:
        return _buildErrorResult(benchmark, f"Timeout: {exc}")
    except RuntimeError as exc:
        return _buildErrorResult(benchmark, f"Pipeline error: {exc}")
    except Exception as exc:
        logger.error("_runPlaywrightDuplicateCapture: unexpected error: %s", exc)
        return _buildErrorResult(benchmark, f"Unexpected error: {exc}")


# ---------------------------------------------------------------------------
# Async wrappers (keep same interface as original runner)
# ---------------------------------------------------------------------------


async def runSingleCapture(benchmark: Benchmark, config: EvalConfig) -> dict:
    """Capture one benchmark result via Playwright (async interface).

    Runs the sync Playwright capture in a thread executor so it can be awaited
    by the async batch runner without blocking the event loop.

    Args:
        benchmark: The benchmark definition from dataset.BENCHMARKS.
        config: EvalConfig with app URL, credentials, and invoice directory.

    Returns:
        Parsed benchmark result dict, or partial error result on failure.
    """
    benchmarkId = benchmark["benchmarkId"]
    logger.info("runSingleCapture: starting %s", benchmarkId)

    if benchmarkId == "ER-013":
        captureFunc = _runPlaywrightDuplicateCapture
    else:
        captureFunc = _runPlaywrightCapture

    try:
        result = await asyncio.to_thread(captureFunc, benchmark, config)
    except Exception as exc:
        logger.error("runSingleCapture: thread error for %s: %s", benchmarkId, exc)
        result = _buildErrorResult(benchmark, f"Thread error: {exc}")

    return result


# ---------------------------------------------------------------------------
# Batch capture runner
# ---------------------------------------------------------------------------


async def runCapture(
    benchmarks: list[Benchmark],
    config: EvalConfig,
) -> list[dict]:
    """Run the full capture loop for a list of benchmarks sequentially.

    Benchmarks are run one at a time (not in parallel) to avoid browser
    session conflicts and keep load on the app manageable.

    Args:
        benchmarks: List of benchmark definitions to capture.
        config: EvalConfig with credentials, URLs, and invoice directory.

    Returns:
        List of result dicts in the same order as the input benchmarks.
    """
    import asyncio as _asyncio

    results: list[dict] = []
    total = len(benchmarks)

    for idx, benchmark in enumerate(benchmarks, start=1):
        benchmarkId = benchmark["benchmarkId"]
        logger.info(
            "CAPTURE [%d/%d] %s — %s",
            idx,
            total,
            benchmarkId,
            benchmark["benchmark"],
        )
        print(f"\n[{idx}/{total}] Capturing {benchmarkId}: {benchmark['benchmark']}")

        try:
            result = await runSingleCapture(benchmark, config)
        except Exception as exc:
            logger.error("runCapture: unexpected error for %s: %s", benchmarkId, exc)
            result = _buildErrorResult(benchmark, f"Unexpected error: {exc}")

        if "captureError" in result:
            print(f"  ERROR: {result['captureError']}")
        else:
            agentDecision = result.get("capture", {}).get("agentDecision", "")
            claimId = result.get("capture", {}).get("claimId", "")
            print(f"  Decision: {agentDecision or 'N/A'}  ClaimId: {claimId or 'N/A'}")

        results.append(result)

        # Brief pause between benchmarks to let the app settle
        if idx < total:
            await _asyncio.sleep(2)

    print(f"\nCapture complete: {total} benchmarks processed.")
    return results
