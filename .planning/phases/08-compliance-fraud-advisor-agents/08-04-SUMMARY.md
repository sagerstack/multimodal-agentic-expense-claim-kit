---
plan: 08-04
status: complete
completed: 2026-04-06
---

# Plan 08-04 Summary: Advisor Agent — Reflection + Routing

## Tasks Completed

### Task 1: Advisor node, prompt, 3 tools, DB MCP extension

**System prompt** (`prompts/advisorSystemPrompt.py`):
- Decision rules table (compliance verdict x fraud verdict → routing decision)
- Mandatory workflow: decide → updateClaimStatus → sendNotification (claimant) → sendNotification (reviewer if escalating)
- Notification message templates
- Final JSON summary output format

**3 Tools:**
- `tools/searchPolicies.py`: RAG MCP searchPolicies (optional, for citing policy clauses)
- `tools/updateClaimStatus.py`: DB MCP updateClaimStatus; DECISION_TO_STATUS uses "rejected" for return_to_claimant
- `tools/sendNotification.py`: Email MCP sendClaimNotification; claimant → `{employeeId}@sutd.edu.sg`, reviewer → `expenses-reviewer@sutd.edu.sg`

**Node (`node.py`):**
- `_getAdvisorAgent`: uses `buildAgentLlm(temperature=0.2)` from shared package
- `state.get("dbClaimId")` — reads directly from state, not ToolMessage scanning
- `_extractAdvisorDecision`: scans reversed messages for JSON with "decision" key, falls back to keyword matching, defaults to escalate_to_reviewer
- `_extractClaimNumber`: reads from state.claimNumber first, falls back to ToolMessage scan
- 402 fallback via `_getAdvisorAgent(useFallback=True)`
- `insertAuditLog` audit entry with action="advisor_decision" (non-fatal)
- Message hygiene: returns only `[AIMessage(summaryMsg)]` — no ReAct tool noise
- Status mapping: auto_approve→approved, return_to_claimant→rejected, escalate_to_reviewer→escalated

**DB MCP extension** (`mcp_servers/db/server.py`):
- `updateClaimStatus` extended with optional `complianceFindings`, `fraudFindings`, `advisorDecision`, `approvedBy` parameters
- Dynamic SET clause builder using `Json()` wrapper for JSONB values

### Task 2: Unit tests
- `tests/test_advisor_agent.py`: 6 tests
  - `testAdvisorAutoApproveCleanClaim`: pass+legit → approved, message contains "AUTO-APPROVED"
  - `testAdvisorReturnToClaimantViolation`: fail+legit → rejected
  - `testAdvisorEscalateForFraud`: pass+suspicious → escalated
  - `testAdvisorDecisionFallbackEscalate`: unparseable output → escalate_to_reviewer default
  - `testAdvisorReadsDbClaimIdFromState`: dbClaimId=99 from state used in audit log MCP call
  - `testAdvisorMessageHygiene`: 4 internal ReAct messages → only 1 summary AIMessage in result

- `tests/test_graph.py`: updated advisor routing assertions ("Advisor Agent" → "Advisor Decision")

## Commits
- `b320b7a` feat(08-04): advisor agent — Reflection+Routing with 3 tools, DB extension, message hygiene

## Test Results
- 190 passed, 0 failures (pre-existing E2E error unchanged)

## Success Criteria Verification
1. Advisor synthesizes compliance + fraud into routing decision — PASS
2. Decision mapping: auto_approve→approved, return_to_claimant→rejected, escalate_to_reviewer→escalated — PASS
3. updateClaimStatus tool + DB MCP extension with JSONB findings — PASS
4. Email notifications via sendNotification tool — PASS
5. dbClaimId read from state directly — PASS (verified by testAdvisorReadsDbClaimIdFromState)
6. Message hygiene: only summary AIMessage returned — PASS (verified by testAdvisorMessageHygiene)
7. 6 unit tests all pass — PASS
