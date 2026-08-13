"""Automated Claude subagent capture runner.

Invokes Claude Code SDK to run Playwright-driven benchmark captures sequentially.
Each benchmark generates a structured JSON result via the subagent prompt.

This module is fully decoupled from the app -- no imports from agentic_claims.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from claude_code_sdk import query
from claude_code_sdk._errors import MessageParseError
from claude_code_sdk.types import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

from eval.src.capture.subagent import buildCapturePrompt, buildDuplicateCapturePrompt
from eval.src.config import EvalConfig
from eval.src.dataset import Benchmark

logger = logging.getLogger(__name__)

# Project root -- used as the subagent cwd so the Playwright MCP server's
# workspace-root file access covers eval/invoices/ for receipt uploads.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Playwright MCP server, passed explicitly to the SDK subprocess. The SDK does
# not inherit the interactive CLI's MCP registry, so without this the subagent
# has no browser and every capture fails with an SDK error.
PLAYWRIGHT_MCP_SERVER: dict = {
    "playwright": {
        "type": "stdio",
        "command": "npx",
        "args": [
            "-y",
            "@playwright/mcp@latest",
            "--headless",
            "--isolated",
            "--viewport-size=1280x900",
        ],
    }
}

# Both forms are supplied: the bare server name allows every tool the server
# exposes, the wildcard covers permission-rule style matching.
PLAYWRIGHT_ALLOWED_TOOLS = ["mcp__playwright", "mcp__playwright__*"]


def _subprocessEnv() -> dict[str, str]:
    """Environment for the spawned `claude` CLI, with Anthropic auth cleared.

    The CLI authenticates via the local subscription login. If ANTHROPIC_API_KEY
    is set it switches to API-key auth instead and dies with "Invalid API key"
    unless the value is a real key -- surfacing here as the opaque
    "Command failed with exit code 1". Clearing it keeps subscription auth.
    """
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env


def _installTolerantMessageParser() -> None:
    """Make claude-code-sdk 0.0.25 skip message types it does not recognise.

    The SDK is end-of-life at 0.0.25 while the `claude` CLI keeps adding message
    types. `rate_limit_event` is emitted on ordinary queries and raises
    MessageParseError, which aborts the capture stream mid-run. Unknown types
    carry no data this runner consumes, so dropping them is safe and keeps the
    capture path working without a dependency migration.
    """
    from claude_code_sdk._internal import client as sdkClient
    from claude_code_sdk._internal.message_parser import parse_message as originalParse

    if getattr(sdkClient.parse_message, "_toleratesUnknownTypes", False):
        return

    def tolerantParse(data):
        try:
            return originalParse(data)
        except MessageParseError:
            logger.debug(
                "Skipping unrecognised SDK message type: %s",
                data.get("type") if isinstance(data, dict) else "?",
            )
            return None

    tolerantParse._toleratesUnknownTypes = True
    sdkClient.parse_message = tolerantParse


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------


def parseSubagentResponse(responseText: str, benchmark: Benchmark) -> dict:
    """Extract a JSON result dict from the Claude subagent's response text.

    The subagent is instructed to return plain JSON, but it may wrap the
    output in markdown code fences. This function handles:
      1. Plain JSON string
      2. ```json ... ``` fenced block
      3. ``` ... ``` fenced block (no language tag)
      4. JSON embedded in prose (greedy extraction of first { ... } block)

    If parsing fails entirely, returns a partial result with captureError set.

    Args:
        responseText: The full text from the subagent's ResultMessage.
        benchmark: The benchmark definition (used to build fallback result).

    Returns:
        Parsed dict matching the captured output schema, or partial result
        with captureError on failure.
    """
    if not responseText or not responseText.strip():
        return _buildErrorResult(benchmark, "Empty response from subagent")

    text = responseText.strip()

    # Try 1: direct JSON parse
    parsed = _tryParseJson(text)
    if parsed is not None:
        return _normaliseResult(parsed, benchmark)

    # Try 2: strip markdown code fences
    fenceMatch = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenceMatch:
        parsed = _tryParseJson(fenceMatch.group(1))
        if parsed is not None:
            return _normaliseResult(parsed, benchmark)

    # Try 3: find the largest top-level JSON object in the text
    # Walk character by character to find balanced braces
    parsed = _extractFirstJsonObject(text)
    if parsed is not None:
        return _normaliseResult(parsed, benchmark)

    logger.warning(
        "parseSubagentResponse: could not extract JSON for %s. "
        "Response snippet: %.200s",
        benchmark["benchmarkId"],
        text,
    )
    return _buildErrorResult(
        benchmark,
        f"JSON parse failed. Response snippet: {text[:200]}",
    )


def _normaliseResult(parsed: dict, benchmark: Benchmark) -> dict:
    """Coerce an abort-shaped subagent response into the standard error schema.

    The capture prompt tells the subagent to bail out with
    {"error": ..., "capture": null} on login failure, a missing receipt file, or
    a pipeline timeout. That shape is not the captured-result schema: downstream
    code (and this module's own progress printing) assumes result["capture"] is
    a dict, so passing it through raised AttributeError and aborted the whole
    run instead of failing just this benchmark.
    """
    if parsed.get("error") or parsed.get("capture") is None:
        message = parsed.get("error") or "Subagent returned no capture payload"
        return _buildErrorResult(benchmark, str(message))
    return parsed


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
# Subagent response text extraction
# ---------------------------------------------------------------------------


def _extractTextFromMessages(messages: list) -> str:
    """Extract all text content from a list of SDK messages.

    Iterates AssistantMessage content blocks and ResultMessage.result,
    concatenating all text found.

    Args:
        messages: List of Message objects from the claude_code_sdk query.

    Returns:
        Combined text string from all messages.
    """
    parts: list[str] = []
    for message in messages:
        if isinstance(message, ResultMessage):
            if message.result:
                parts.append(message.result)
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# Single benchmark capture
# ---------------------------------------------------------------------------


async def runSingleCapture(benchmark: Benchmark, config: EvalConfig) -> dict:
    """Invoke Claude via claude-code-sdk to capture one benchmark result.

    Selects the appropriate prompt (standard vs duplicate for ER-013),
    streams events from the subagent, and parses the final JSON response.

    Args:
        benchmark: The benchmark definition from dataset.BENCHMARKS.
        config: EvalConfig with ANTHROPIC_API_KEY and app credentials.

    Returns:
        Parsed benchmark result dict, or partial error result on failure.
    """
    benchmarkId = benchmark["benchmarkId"]

    if benchmarkId == "ER-013":
        prompt = buildDuplicateCapturePrompt(benchmark, config)
    else:
        prompt = buildCapturePrompt(benchmark, config)

    _installTolerantMessageParser()

    options = ClaudeCodeOptions(
        mcp_servers=PLAYWRIGHT_MCP_SERVER,
        allowed_tools=PLAYWRIGHT_ALLOWED_TOOLS,
        max_turns=50,
        cwd=_PROJECT_ROOT,
        env=_subprocessEnv(),
    )

    collectedMessages: list = []

    try:
        async for event in query(prompt=prompt, options=options):
            # Unrecognised message types are dropped by the tolerant parser
            if event is None:
                continue

            collectedMessages.append(event)

            # Log tool use activity for visibility
            if isinstance(event, AssistantMessage):
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        logger.info("  [%s] Tool: %s", benchmarkId, block.name)

    except Exception as exc:
        logger.error(
            "runSingleCapture: SDK error for %s: %s",
            benchmarkId,
            exc,
        )
        return _buildErrorResult(benchmark, f"SDK error: {exc}")

    responseText = _extractTextFromMessages(collectedMessages)

    if not responseText:
        return _buildErrorResult(benchmark, "No text content in subagent response")

    return parseSubagentResponse(responseText, benchmark)


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

    For each benchmark:
      1. Build the subagent prompt
      2. Invoke Claude via claude-code-sdk
      3. Parse the JSON response
      4. Log progress

    Errors for individual benchmarks are caught and stored as partial
    results -- the loop continues to the next benchmark.

    Args:
        benchmarks: List of benchmark definitions to capture.
        config: EvalConfig with credentials, URLs, and API keys.

    Returns:
        List of result dicts in the same order as the input benchmarks.
    """
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
            logger.error(
                "runCapture: unexpected error for %s: %s",
                benchmarkId,
                exc,
            )
            result = _buildErrorResult(benchmark, f"Unexpected error: {exc}")

        if "captureError" in result:
            print(f"  ERROR: {result['captureError']}")
        else:
            agentDecision = (result.get("capture") or {}).get("agentDecision", "")
            print(f"  Decision: {agentDecision or 'N/A'}")

        results.append(result)

        # Brief pause between benchmarks to avoid session overlap
        if idx < total:
            await asyncio.sleep(1)

    print(f"\nCapture complete: {total} benchmarks processed.")
    return results
