---
status: diagnosed
trigger: "Gap 6 UAT: internal tool names (askHuman, extractReceiptFields, etc.) exposed to end users in thinking/reasoning panel"
created: 2026-04-13
updated: 2026-04-13
---

## Root Cause

Two leakage sites in src/agentic_claims/web/sseHelpers.py:
1. _summarizeToolOutput (lines 127/163/166) returns `f"Completed {toolName}"` for askHuman (no dedicated branch) → renders into STEP_CONTENT at line 1178.
2. STEP_NAME fallback (line 1114) `f"Running {toolName}..."` for any tool missing from TOOL_LABELS.

Interrupt channel IS correctly firing (line 1507) — not a 13-09 regression. See .planning/phases/13-intake-agent-hybrid-routing-and-bug-fixes/13-DEBUG-tool-name-leak.md for full analysis.

## Current Focus

hypothesis: sseHelpers.py emits tool.start/tool.end with raw toolName; template renders it verbatim. askHuman may not be reaching `sse-swap="interrupt"` channel.
test: trace SSE emission for all tools + askHuman interrupt flow
expecting: map events → template partials → visible rendering
next_action: read sseHelpers.py in full

## Symptoms

expected: Thinking panel shows friendly labels ("Asking for clarification") not internal names; askHuman renders via interrupt channel not tool-trace.
actual: Users see "Completed askHuman" in thinking panel (UAT German session d6ab0ed2 @ 00:04:27).
errors: none
reproduction: submit a claim that triggers askHuman tool call → observe UI thinking panel
started: Phase 13 (specifically post-13-09 refactor per 13-11 executor's note)
