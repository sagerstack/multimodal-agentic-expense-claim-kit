---
phase: "11"
plan: "02"
name: "Remove Dead UI and Fix Pathway Reset"
subsystem: "advisor-agent, ui-templates, sse-pathway"
status: "complete"
completed: "2026-04-11"
duration: "8 min"
tags: ["advisor", "sendNotification", "message-bubble", "decision-pathway", "sse", "cleanup"]

dependency-graph:
  requires: ["11-01"]
  provides: ["advisor-2-tool-config", "clean-message-bubbles", "pathway-reset-on-new-receipt"]
  affects: ["11-03", "11-04"]

tech-stack:
  added: []
  patterns: ["pathway-seeding-reset-condition"]

key-files:
  created: []
  modified:
    - "src/agentic_claims/agents/advisor/node.py"
    - "src/agentic_claims/agents/advisor/prompts/advisorSystemPrompt.py"
    - "templates/partials/message_bubble.html"
    - "src/agentic_claims/web/sseHelpers.py"

decisions:
  - "Keep sendNotification.py file (not deleted) — may be used later for direct MCP calls outside ReAct loop"
  - "Reset pathway by clearing both pathwayCompletedTools and pathwayToolTimestamps on new receipt after submission"

metrics:
  tasks-completed: 2
  tasks-total: 2
  commits: 2
---

# Phase 11 Plan 02: Remove Dead UI and Fix Pathway Reset Summary

**One-liner:** Removed sendNotification from advisor ReAct tools (2 tools remain), stripped confirm/edit buttons from message bubbles, and added pathway reset condition for new receipt after prior submission.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove sendNotification from advisor and confirm/edit buttons from message bubbles | c52421a | advisor/node.py, advisorSystemPrompt.py, message_bubble.html |
| 2 | Fix Decision Pathway reset on new receipt after submission | 49a00a7 | sseHelpers.py |

## What Was Done

### Task 1 — Advisor cleanup and dead UI removal

**advisor/node.py:**
- Removed `from agentic_claims.agents.advisor.tools.sendNotification import sendNotification` import
- Changed `tools=[searchPolicies, updateClaimStatus, sendNotification]` to `tools=[searchPolicies, updateClaimStatus]`
- Updated `_getAdvisorAgent` docstring: "two tools" (was "three tools")
- Updated context message: removed "sendNotification (claimant) → sendNotification (reviewer, if escalating)" from the workflow instruction
- Updated module docstring to remove mcp-email reference

**advisorSystemPrompt.py:**
- Removed `sendNotification` row from the TOOLS table
- Removed Steps 3 and 4 (notify claimant/reviewer) from the MANDATORY WORKFLOW section
- Removed NOTIFICATION MESSAGE TEMPLATES section
- Removed `notificationsSent` field from the output JSON schema
- Removed "Always call updateClaimStatus BEFORE sendNotification" constraint

**message_bubble.html:**
- Removed the `<div class="flex gap-2 mt-3">` block with its two `<button>` elements ("Yes, looks correct" and "Edit details")
- Retained the confidence scores display (`<div class="flex flex-wrap gap-1 mt-2">` with score badges)
- The multi-turn interrupt flow via `askHuman` handles confirmation — these buttons were dead code

### Task 2 — Decision Pathway reset

**sseHelpers.py (lines 739-764):**
- Added reset condition: `if graphInput.get("hasImage") and sv.get("claimSubmitted"):`
  - Clears `pathwayCompletedTools` and `pathwayToolTimestamps`
  - Seeds only `receiptUploaded` timestamp for the fresh upload
- Moved existing seeding logic (extractedReceipt, searchPolicies, claimSubmitted checks) into the `else` branch
- Without this fix, uploading a second receipt in the same session after a prior submission would display all pathway steps as already completed

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Keep sendNotification.py file | Not deleted — may be used later as a direct MCP call outside the ReAct loop |
| Reset both sets and timestamps | Timestamps must also be cleared so new receipt gets fresh timestamps, not inherited ones from prior claim |

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

- Plan 11-03 can proceed: advisor cleanup is complete, conversation UX improvements can build on clean state
- The sendNotification.py file is preserved for potential future use
