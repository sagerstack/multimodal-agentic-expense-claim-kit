"""Unit tests for _summarizeToolOutput label hygiene (Plan 13-16 gap closure).

Source: 13-DEBUG-tool-name-leak.md section 3 (STEP_CONTENT leak) + section 5 Recommendation.
"""

import re

from agentic_claims.web.sseHelpers import (
    TOOL_COMPLETION_LABELS,
    TOOL_LABELS,
    _summarizeToolOutput,
)


_INTERNAL_TOOL_NAMES = {
    "askHuman",
    "extractReceiptFields",
    "searchPolicies",
    "convertCurrency",
    "submitClaim",
    "getClaimSchema",
}


def testToolCompletionLabelsCoversAllKnownTools():
    """Every tool in TOOL_LABELS has a matching completion label."""
    for toolName in TOOL_LABELS:
        assert toolName in TOOL_COMPLETION_LABELS, (
            f"Missing completion label for {toolName}"
        )


def testSummarizeToolOutputNeverLeaksInternalToolNames():
    """Across happy path, error path, malformed payload, and unknown tool
    name, _summarizeToolOutput must never return a string containing a
    raw internal tool name. Source: 13-DEBUG-tool-name-leak.md section 3."""
    fixtures = [
        # (toolName, toolOutput) pairs covering the three default-branch
        # sites identified in the debug doc (lines 127, 163, 166).
        ("askHuman", ""),
        ("askHuman", None),
        ("askHuman", '{"not": "a dict but parses"}'),
        ("askHuman", "plain string not json"),
        ("extractReceiptFields", '{"fields": {}}'),  # dedicated branch
        ("searchPolicies", '{"results": []}'),  # dedicated branch
        ("convertCurrency", '{"rate": 1.0}'),  # dedicated branch
        ("submitClaim", '{"claim": {"id": "CL-1"}}'),  # dedicated branch
        ("getClaimSchema", '{"claims": [], "receipts": []}'),  # dedicated branch
        ("unknownFutureTool", '{"foo": "bar"}'),  # fallback path must not leak
        ("unknownFutureTool", None),  # fallback path
    ]
    pattern = re.compile(r"\b(" + "|".join(_INTERNAL_TOOL_NAMES) + r")\b")
    for toolName, toolOutput in fixtures:
        summary = _summarizeToolOutput(toolName, toolOutput)
        assert not pattern.search(summary), (
            f"_summarizeToolOutput({toolName!r}, ...) leaked internal tool "
            f"name in output: {summary!r}"
        )


def testSummarizeToolOutputUnknownToolUsesGenericFallback():
    """Unknown / future tools fall back to 'Step complete', never 'Completed <name>'."""
    summary = _summarizeToolOutput("brandNewTool", None)
    assert summary == "Step complete"
    summary2 = _summarizeToolOutput("brandNewTool", "not-json-at-all")
    assert summary2 == "Step complete"


def testSummarizeToolOutputAskHumanUsesCompletionLabel():
    """askHuman hits the default branch (no dedicated case). Must return
    the TOOL_COMPLETION_LABELS entry (e.g. 'Asked for clarification')."""
    summary = _summarizeToolOutput("askHuman", "")
    assert summary == TOOL_COMPLETION_LABELS["askHuman"]
    assert "askHuman" not in summary
