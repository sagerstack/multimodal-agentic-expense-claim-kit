"""Deterministic Playwright benchmark capture.

Replaces the Claude-subagent capture loop. The benchmark flow is a fixed script
-- log in, set a file input, type a fixed message, submit, wait, scrape -- so
there is nothing for an LLM to decide. Driving it with an agent cost ~340s per
benchmark (~95% overhead against ~10s of actual app work) and, worse, made the
measuring instrument non-deterministic: the same benchmark could fail in
different ways on consecutive runs, so a failure could not be attributed to the
app rather than to the harness.

This module performs the identical flow with the `playwright` package directly.

DOM contract (verified against templates/chat.html):
  * #doneTarget      -- receives the HTML comment "<!-- done -->" and is
                        class="hidden". Both facts defeat CSS :empty and
                        Playwright visibility waits, so completion is detected
                        by reading innerHTML in JavaScript.
  * #interruptTarget -- clarifying questions; may contain buttons
                        (templates/partials/interrupt_buttons.html) which
                        disable the textarea, so button interrupts must be
                        answered by clicking, not typing.
  * #chatHistory     -- completed turns land here; #aiMessages is empty by the
                        time the done sentinel fires.

This module is fully decoupled from the app -- no imports from agentic_claims.
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import psycopg
from playwright.async_api import Browser, Page, async_playwright

from eval.src.config import EvalConfig
from eval.src.dataset import Benchmark

logger = logging.getLogger(__name__)

# How long to wait for one agent turn to finish before giving up.
TURN_TIMEOUT_SECONDS = 180.0
POLL_INTERVAL_SECONDS = 1.0
# Window to wait after 'done' for a trailing interrupt swap to arrive.
DONE_GRACE_SECONDS = 4.0
# Safety valve: a benchmark that keeps producing interrupts must still finish.
MAX_INTERRUPT_REPLIES = 6

_CLAIM_NUMBER_PATTERN = re.compile(r"\bCLAIM-[A-Za-z0-9]+\b")

_CLEAR_TARGETS_JS = """() => {
  for (const id of ['doneTarget', 'interruptTarget']) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '';
  }
}"""

_READ_TARGETS_JS = """() => {
  const read = id => {
    const el = document.getElementById(id);
    return el ? el.innerHTML.trim().length : 0;
  };
  const buttons = Array.from(
    document.querySelectorAll('#interruptTarget button[aria-label]')
  ).map(b => b.getAttribute('aria-label'));
  return {done: read('doneTarget'), interrupt: read('interruptTarget'), buttons};
}"""


def _buildEmptyCapture() -> dict:
    """Return the capture sub-document with every key present and unset."""
    return {
        "claimId": None,
        "conversationTranscript": [],
        "extractedFields": None,
        "agentDecision": None,
        "complianceFindings": None,
        "fraudFindings": None,
        "advisorReasoning": None,
        "retrievedPolicyChunks": [],
    }


def buildResultSkeleton(benchmark: Benchmark) -> dict:
    """Return a result dict matching the captured-result schema."""
    return {
        "benchmarkId": benchmark["benchmarkId"],
        "benchmark": benchmark["benchmark"],
        "category": benchmark["category"],
        "file": benchmark["file"],
        "scoringType": benchmark["scoringType"],
        "capture": _buildEmptyCapture(),
        "expected": {
            "expectedDecision": benchmark["expectedDecision"],
            "passCriteria": benchmark["passCriteria"],
            "companionMetadata": benchmark.get("companionMetadata"),
        },
    }


def buildErrorResult(benchmark: Benchmark, errorMessage: str) -> dict:
    """Return a result marked with captureError, keeping the schema intact."""
    result = buildResultSkeleton(benchmark)
    result["captureError"] = errorMessage
    return result


def parseTranscript(chatText: str) -> list[dict]:
    """Split #chatHistory innerText into ordered user/assistant turns.

    The DOM renders a Material icon name on its own line before each turn
    ("person" for the user, "smart_toy" for the agent), which gives a reliable
    deterministic delimiter without depending on styling or bubble classes.
    """
    # Chrome renders the thinking panel and per-bubble timestamps inside
    # #chatHistory too; neither is conversation content.
    timestampPattern = re.compile(r"^(\d{1,2}:\d{2}\s*(AM|PM)?|Just now|Today|Yesterday)$", re.I)
    thinkingPattern = re.compile(r"^(Thought for .*|\.?\s*\d+ tools?|Governance control .*)$", re.I)

    turns: list[dict] = []
    role: Optional[str] = None
    buffer: list[str] = []

    def flush() -> None:
        if role and buffer:
            content = "\n".join(line for line in buffer if line.strip()).strip()
            if content:
                turns.append({"role": role, "content": content})

    for rawLine in (chatText or "").splitlines():
        line = rawLine.strip()
        if line in ("person", "smart_toy"):
            flush()
            role = "user" if line == "person" else "assistant"
            buffer = []
            continue
        # Icon names for the collapsible thinking panel -- not conversation.
        if line in ("neurology", "expand_more", "expand_less", "shield"):
            continue
        if timestampPattern.match(line) or thinkingPattern.match(line):
            continue
        buffer.append(rawLine)

    flush()
    return turns


async def _fetchExtractedFields(claimNumber: str, dbUrl: str) -> Optional[dict]:
    """Read what the app actually persisted for this claim.

    Sourced from the database rather than scraped from agent prose: the receipts
    row is what the system committed, so it cannot drift with wording changes.
    """
    try:
        async with await psycopg.AsyncConnection.connect(dbUrl) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT r.merchant, r.date, r.total_amount, r.currency,
                           r.line_items, r.original_amount, r.original_currency,
                           r.converted_amount_sgd, c.category
                    FROM claims c
                    LEFT JOIN receipts r ON r.claim_id = c.id
                    WHERE c.claim_number = %s
                    LIMIT 1
                    """,
                    (claimNumber,),
                )
                row = await cur.fetchone()
    except Exception as exc:
        logger.warning("extractedFields lookup failed for %s: %s", claimNumber, exc)
        return None

    if row is None or row[0] is None:
        return None

    (merchant, date, totalAmount, currency, lineItems,
     originalAmount, originalCurrency, convertedSgd, category) = row

    fields: dict[str, Any] = {
        "merchant": merchant,
        "date": date.isoformat() if date else None,
        "total": float(originalAmount) if originalAmount is not None else (
            float(totalAmount) if totalAmount is not None else None
        ),
        "currency": originalCurrency or currency,
        "category": category,
        "lineItems": len(lineItems) if isinstance(lineItems, list) else None,
    }
    if convertedSgd is not None:
        fields["convertedAmount"] = float(convertedSgd)
        fields["convertedCurrency"] = "SGD"
        if originalAmount:
            fields["exchangeRate"] = round(float(convertedSgd) / float(originalAmount), 4)
    return fields


async def _login(page: Page, config: EvalConfig) -> None:
    """Authenticate and land on the chat page."""
    await page.goto(f"{config.appUrl}/login", wait_until="domcontentloaded")
    await page.fill('input[name="username"]', config.evalUsername)
    await page.fill('input[name="password"]', config.evalPassword)
    await page.click('button[type="submit"]')
    # networkidle never fires -- the SSE stream holds a connection open.
    await page.wait_for_selector("#chatForm", timeout=30_000)


async def _submitTurn(page: Page, message: str, receiptPath: Optional[Path]) -> None:
    """Clear the done sentinel, optionally attach a receipt, and send a message."""
    await page.evaluate(_CLEAR_TARGETS_JS)
    if receiptPath is not None:
        await page.set_input_files('input[type="file"][name="receipt"]', str(receiptPath))
    await page.fill('textarea[name="message"]', message)
    await page.click('#chatForm button[type="submit"]')


async def _waitForTurn(page: Page) -> str:
    """Block until the done sentinel fills or an interrupt appears.

    Returns "done", "interrupt", or "timeout".
    """
    deadline = time.monotonic() + TURN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = await page.evaluate(_READ_TARGETS_JS)
        # Interrupt takes precedence over done: the agent fills BOTH targets
        # when it ends a turn with a question (the interrupt swap also
        # dispatches stream-done). Checking done first would end the capture
        # while the agent is still waiting for an answer, so nothing is ever
        # submitted.
        if state["interrupt"] > 0:
            return "interrupt"
        if state["done"] > 0:
            # The done sentinel can land a beat BEFORE the interrupt swap, so a
            # bare "done" is not proof the agent has finished with us. Give the
            # interrupt a grace window to appear; without this the capture ends
            # while the agent is still asking "May I submit it?" and no claim is
            # ever created.
            graceDeadline = time.monotonic() + DONE_GRACE_SECONDS
            while time.monotonic() < graceDeadline:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                if (await page.evaluate(_READ_TARGETS_JS))["interrupt"] > 0:
                    return "interrupt"
            return "done"
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    return "timeout"


async def _answerInterrupt(page: Page) -> None:
    """Reply to a clarifying question, by button when buttons are present."""
    state = await page.evaluate(_READ_TARGETS_JS)
    buttons: list[str] = state.get("buttons") or []

    if buttons:
        # Prefer an affirmative option so the benchmark proceeds to a decision.
        affirmative = ("yes", "confirm", "proceed")
        label = next(
            (b for b in buttons if b.strip().lower() in affirmative), buttons[0]
        )
        # Read the label off the live DOM before clearing, then clear so the
        # answered question cannot be re-detected as a new interrupt.
        await page.click(f'#interruptTarget button[aria-label="{label}"]')
        await page.evaluate(_CLEAR_TARGETS_JS)
        logger.info("  answered button interrupt: %s", label)
        return

    await _submitTurn(page, "Yes, please proceed", receiptPath=None)
    logger.info("  answered text interrupt")


async def _runBenchmarkOnPage(page: Page, benchmark: Benchmark, config: EvalConfig) -> dict:
    """Drive one benchmark to completion on an authenticated page."""
    result = buildResultSkeleton(benchmark)
    capture = result["capture"]

    receiptPath = config.invoicesDir / benchmark["file"]
    if not receiptPath.exists():
        return buildErrorResult(benchmark, f"Receipt file not found: {benchmark['file']}")

    await _submitTurn(
        page,
        f"Please process this receipt: {benchmark['scenario']}",
        receiptPath,
    )

    outcome = await _waitForTurn(page)
    replies = 0
    while outcome == "interrupt" and replies < MAX_INTERRUPT_REPLIES:
        await _answerInterrupt(page)
        replies += 1
        outcome = await _waitForTurn(page)

    if outcome == "timeout":
        return buildErrorResult(
            benchmark, "Pipeline timeout -- done sentinel never received content"
        )
    if outcome == "interrupt":
        return buildErrorResult(
            benchmark, f"Interrupt loop exceeded {MAX_INTERRUPT_REPLIES} replies"
        )

    chatText = await page.evaluate(
        "() => document.getElementById('chatHistory')?.innerText || ''"
    )
    capture["conversationTranscript"] = parseTranscript(chatText)

    claimMatch = _CLAIM_NUMBER_PATTERN.search(chatText)
    if claimMatch:
        claimNumber = claimMatch.group(0)
        capture["claimId"] = claimNumber
        capture["agentDecision"] = "submitted"
        capture["extractedFields"] = await _fetchExtractedFields(claimNumber, config.dbUrl)
    else:
        # No claim number means the agent declined to submit -- a valid outcome
        # for rejection benchmarks (ER-002, ER-003). Record the closing message.
        assistantTurns = [t for t in capture["conversationTranscript"] if t["role"] == "assistant"]
        capture["agentDecision"] = assistantTurns[-1]["content"] if assistantTurns else None

    return result


async def _resetSession(page: Page, config: EvalConfig) -> None:
    """Start a fresh conversation so benchmarks do not share thread state."""
    await page.goto(f"{config.appUrl}/logout", wait_until="domcontentloaded")
    await _login(page, config)


async def _captureDuplicateBenchmark(
    browser: Browser, benchmark: Benchmark, config: EvalConfig
) -> dict:
    """ER-013: submit the same receipt twice in two independent sessions.

    The second submission is the one under test -- the agent should recognise it
    as a duplicate of the first.
    """
    firstContext = await browser.new_context()
    try:
        page = await firstContext.new_page()
        await _login(page, config)
        await _runBenchmarkOnPage(page, benchmark, config)
    finally:
        await firstContext.close()

    secondContext = await browser.new_context()
    try:
        page = await secondContext.new_page()
        await _login(page, config)
        return await _runBenchmarkOnPage(page, benchmark, config)
    finally:
        await secondContext.close()


async def runCapture(benchmarks: list[Benchmark], config: EvalConfig) -> list[dict]:
    """Capture every benchmark sequentially in a single browser instance.

    Benchmarks run one at a time and each gets a fresh browser context, so no
    session or conversation state leaks between them.
    """
    results: list[dict] = []
    total = len(benchmarks)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for index, benchmark in enumerate(benchmarks, start=1):
                benchmarkId = benchmark["benchmarkId"]
                started = time.monotonic()
                logger.info(
                    "CAPTURE [%d/%d] %s -- %s",
                    index, total, benchmarkId, benchmark["benchmark"],
                )

                try:
                    if benchmarkId == "ER-013":
                        result = await _captureDuplicateBenchmark(browser, benchmark, config)
                    else:
                        context = await browser.new_context()
                        try:
                            page = await context.new_page()
                            await _login(page, config)
                            result = await _runBenchmarkOnPage(page, benchmark, config)
                        finally:
                            await context.close()
                except Exception as exc:
                    logger.error("Capture failed for %s: %s", benchmarkId, exc)
                    result = buildErrorResult(benchmark, f"{type(exc).__name__}: {exc}")

                elapsed = time.monotonic() - started
                if "captureError" in result:
                    logger.warning(
                        "  [%s] ERROR: %s (%.1fs)",
                        benchmarkId, result["captureError"], elapsed,
                    )
                else:
                    logger.info(
                        "  [%s] claim=%s turns=%d (%.1fs)",
                        benchmarkId,
                        result["capture"]["claimId"],
                        len(result["capture"]["conversationTranscript"]),
                        elapsed,
                    )
                results.append(result)
        finally:
            await browser.close()

    return results
