# Phase 8: Compliance, Fraud + Advisor Agents - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Port the three post-submission agents (Compliance, Fraud, Advisor) from reference code (`reference-code/src/agentic_claims/agents/`) into the live codebase. Replace the current stubs with LLM-powered implementations. After the Intake Agent submits a claim, the graph pipeline runs compliance + fraud in parallel, then the advisor synthesizes both reports and routes the claim (auto-approve, return-to-claimant, or escalate-to-reviewer). The graph wiring (parallel fan-out + fan-in via evaluatorGate) already exists — the stubs need to be replaced with real agent logic.

The Claims (Chat) page is FROZEN — no changes to the chat UI. Post-submission processing is invisible to the claimant. Results appear on the Audit Log and Claim Review pages.

</domain>

<decisions>
## Implementation Decisions

### Reference Code Adaptation
- **SQL injection fix**: Rewrite fraud DB queries (queryClaimsHistory.py) to use parameterized SQL instead of f-string interpolation. Check if DB MCP executeQuery supports parameters; if not, sanitize inputs.
- **Shared tools**: Extract shared tools (searchPolicies, updateClaimStatus, sendNotification) to `agents/shared/tools/` instead of duplicating across agent packages.
- **SSL bypass**: Keep the httpx `verify=False` SSL bypass pattern in all 3 new agents, matching intake node behavior.
- **LLM fallback**: Port the 402 quota fallback pattern identically into each agent (primary model → fallback model on credits error). Do NOT extract to shared helper — keep it per-agent matching the reference pattern.
- **Agent patterns**: Port as-is from reference:
  - Compliance = direct LLM call (Evaluator pattern, SystemMessage + HumanMessage → structured JSON)
  - Fraud = direct LLM call + DB queries (Tool Call pattern, deterministic duplicate short-circuit)
  - Advisor = ReAct agent via create_react_agent with 3 tools (Reflection + Routing pattern)
- **DB MCP tools**: Use the existing `executeQuery` tool for all fraud queries. No new DB MCP tools.
- **Email MCP**: Keep stub mode (console logger in local dev). Advisor's sendNotification tool calls the existing Email MCP server's sendClaimNotification tool.
- **LLM client**: Use `ChatOpenRouter` directly in each agent (matching intake node), NOT the OpenRouterClient wrapper.

### SSE Streaming & Execution
- **No chat UI updates for post-submission agents**. The chat stream ends after intake's submission confirmation. Post-submission results are visible only on Audit Log and Claim Review pages.
- **Same graph execution**: Post-submission agents run in the same `astream_events` call as intake. The SSE stream stays open until the advisor finishes, but the chat UI ignores non-intake events. No background tasks.
- **Decision Pathway sidebar on Claims page stays as-is** (pre-submission only: Receipt Uploaded, AI Extraction, Policy Check, Final Decision). Post-submission steps appear only on the Audit Log page timeline.
- **Submission Summary table**: Static until refresh. No real-time SSE update for claim status changes.

### ClaimState + Audit Trail
- **New ClaimState fields**: Add `complianceFindings` (Optional[dict]), `fraudFindings` (Optional[dict]), `advisorDecision` (Optional[str]), `dbClaimId` (Optional[int]) to ClaimState.
- **Persist to both**: Add `compliance_findings` (JSONB), `fraud_findings` (JSONB), `advisor_decision` (VARCHAR), `approved_by` (VARCHAR, nullable) columns to claims table via Alembic migration. Reviewer pages query claims table directly for quick access. Audit_log has the detailed timeline.
- **approved_by field**: When advisor auto-approves → `approved_by = 'agent'`. When a reviewer approves/rejects → `approved_by = reviewer's employee ID` (e.g. '909090').
- **Direct audit writes**: Post-submission agents write audit_log entries directly via `insertAuditLog` MCP tool (no buffer/flush — DB claim ID is already known).
- **All 3 agents write audit entries**: Compliance writes `compliance_check`, Fraud writes `fraud_check`, Advisor writes `advisor_decision`. Full timeline visibility on Audit Log page.
- **Ensure violations populated**: Update intake agent to always write `violations` to ClaimState (empty list if none found). Compliance node depends on this.
- **dbClaimId in ClaimState**: submitClaim writes the integer DB primary key to `ClaimState.dbClaimId`. Advisor reads it directly from state instead of parsing ToolMessages.

### Advisor Decision → Status Mapping
- **Status values**: `auto_approve` → `"approved"`, `return_to_claimant` → `"rejected"`, `escalate_to_reviewer` → `"escalated"`. Note: reference uses "returned" but we use **"rejected"** instead.
- **No decision message in chat**: Chat ends after intake's submission confirmation. Decision visible only on Dashboard/Audit Log.
- **Advisor audit detail**: Advisor writes a rich `insertAuditLog` entry containing its decision reasoning, compliance summary, and fraud summary — in addition to the updateClaimStatus audit entry.
- **Message hygiene**: Only append the human-readable summary AIMessage to ClaimState.messages from the advisor. Filter out ReAct tool call/response messages.

### Dashboard, Claim Review & Audit Log Page Changes
- **Audit Log timeline**: New steps (compliance_check, fraud_check, advisor_decision) with **distinct colors per agent** — intake = blue, compliance = green/red (pass/fail), fraud = orange (risk), advisor = purple (decision). Compliance and fraud steps should be visually indicated as **parallel** (same superstep) in the timeline.
- **Claim Review page**: Add separate 'Compliance' card (verdict, violations, cited clauses) and 'Fraud' card (verdict, flags, duplicates) alongside existing receipt/fields cards. These read from the new JSONB columns on the claims table.
- **Dashboard KPIs**: Update existing cards to show breakdown (Pending/Escalated/Rejected) instead of adding new cards.
- **Approve/reject buttons**: Only show on escalated claims. Auto-approved and rejected claims are final — no reviewer override.
- **Escalation styling**: Status badge is sufficient — no special highlighting for escalated claims beyond the badge.

### Claude's Discretion
- Exact structure of the shared tools module (`agents/shared/tools/`)
- Parameterized query implementation details for fraud DB queries
- SSE event filtering logic for ignoring non-intake events in the chat stream
- Compliance/fraud card layout on Claim Review page
- Color palette for agent-specific timeline steps

</decisions>

<specifics>
## Specific Ideas

- Reference code is at `reference-code/src/agentic_claims/agents/{compliance,fraud,advisor}/` — port structure, prompts, and logic but adapt to our codebase conventions
- The `_extractJsonBlock()` helper is duplicated across all 3 reference agents — extract to shared utils
- Fraud agent's `_isExactDuplicate()` short-circuits the LLM call for deterministic duplicate detection — this is a critical behavior to preserve
- Advisor's VALID_DECISIONS set and decision→status mapping should use "rejected" not "returned"
- Email addresses: claimant → `{employeeId}@sutd.edu.sg`, reviewer → `expenses-reviewer@sutd.edu.sg`

</specifics>

<deferred>
## Deferred Ideas

- **In-app notifications for reviewers** — badge count on sidebar 'Review' item showing pending escalated claims
- **Resubmission flow** — claimant sees why their claim was rejected and can resubmit through the chat
- **MailHog integration** — wire up MailHog container for visible email testing in local dev

</deferred>

<uat>
## Acceptance Test Scenarios

**Created:** 2026-04-06
**Phase:** 8

### Scenario 1: Full pipeline — auto-approve [Happy path]

**Precondition:** App running, logged in as user (sagar/sagar123), no prior claims in this session
**Test receipt:** A valid restaurant receipt under SGD 100 (within meal policy cap)

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a valid restaurant receipt and provide employee ID | AI extracts fields, thinking panel shows extraction steps, Decision Pathway updates |
| 2 | Confirm extracted fields when prompted | Policy check passes, submission proceeds |
| 3 | Wait for "Your claim CLAIM-XXX has been submitted" confirmation | Chat shows submission confirmation with claim number |
| 4 | Log out, log in as reviewer (james/james123), navigate to Dashboard | Dashboard shows the new claim in the claims table with status 'approved' |
| 5 | Click the claim row to open Claim Review page | Claim Review shows: receipt image, extracted fields, Compliance card (verdict: PASS, no violations), Fraud card (verdict: LEGIT, no flags), no approve/reject buttons (already approved) |
| 6 | Navigate to Audit Log, select the claim | Decision timeline shows 6 steps: receipt_uploaded → ai_extraction → policy_check → compliance_check (PASS) → fraud_check (LEGIT) → advisor_decision (APPROVED). Compliance and fraud steps shown as parallel |

**Verify:**
- `SELECT status, compliance_findings, fraud_findings, advisor_decision, approved_by FROM claims WHERE claim_number = 'CLAIM-XXX'` returns status='approved', all findings populated, approved_by='agent'
- `SELECT COUNT(*) FROM audit_log WHERE claim_id = X` returns 6 entries (3 intake + 3 post-submission)

### Scenario 2a: Escalation — high amount [Happy path]

**Precondition:** App running, logged in as user, no prior claims in session
**Test receipt:** A receipt with amount > SGD 2000 (triggers director approval threshold)

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a high-value receipt (> SGD 2000) and provide employee ID | AI extracts fields, amount shows > SGD 2000 |
| 2 | Confirm extracted fields, claim is submitted | Chat shows "CLAIM-XXX has been submitted" |
| 3 | Log in as reviewer (james/james123), navigate to Dashboard | Dashboard shows claim with status 'escalated' |
| 4 | Click the claim to open Claim Review | Compliance card shows requiresDirectorApproval=true, Fraud card shows verdict, AI Insight shows advisor reasoning, approve/reject buttons are visible |
| 5 | Click 'Approve' button | Claim status changes to 'approved', approved_by = reviewer's employee ID (909090) |

**Verify:**
- `SELECT status, approved_by FROM claims WHERE claim_number = 'CLAIM-XXX'` returns status='approved', approved_by='909090'
- Audit log has an entry with action='reviewer_decision' and actor containing reviewer info

### Scenario 2b: Escalation — suspicious fraud [Happy path]

**Precondition:** App running, logged in as user. Multiple prior claims at the same merchant already exist (>3 in last 30 days from seeded data or prior submissions)

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a receipt from the same merchant as prior claims | AI extracts fields |
| 2 | Confirm and submit | Chat shows submission confirmation |
| 3 | Log in as reviewer, navigate to Audit Log, select the claim | Fraud step shows 'suspicious' verdict with frequency_anomaly flag. Compliance and fraud steps shown as parallel |
| 4 | Open Claim Review | Fraud card shows flags (frequency_anomaly), related claim numbers listed |

**Verify:**
- `SELECT fraud_findings FROM claims WHERE claim_number = 'CLAIM-XXX'` — fraud_findings contains verdict='suspicious' and flags array is non-empty

### Scenario 3: Duplicate claim detection [Edge case]

**Precondition:** App running, logged in as user, fresh session

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a valid receipt, provide employee ID, confirm, submit | First claim submitted successfully — CLAIM-XXX, status 'approved' |
| 2 | Reset chat session (new claim) | Fresh session starts |
| 3 | Upload the SAME receipt, same employee ID, confirm, submit | Second claim submitted — CLAIM-YYY |
| 4 | Log in as reviewer, navigate to Claim Review for CLAIM-YYY | Fraud card shows verdict: DUPLICATE, flag type: 'duplicate', references CLAIM-XXX. Claim status is 'escalated' |

**Verify:**
- `SELECT status, fraud_findings FROM claims WHERE claim_number = 'CLAIM-YYY'` — status='escalated', fraud_findings contains verdict='duplicate' and duplicateClaims includes CLAIM-XXX

### Scenario 4: Existing intake flow unbroken [Regression]

**Precondition:** App running, logged in as user, fresh session

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Navigate to Claims page (/) | Chat page loads with input area, thinking panel collapsed, Decision Pathway shows 4 steps all 'Pending' |
| 2 | Upload a receipt image | Thinking panel opens, shows "Extracting fields..." step. Decision Pathway: 'Receipt Uploaded' step updates to 'Completed' |
| 3 | AI responds with extracted fields, asks for confirmation | Chat shows AI message with merchant, amount, date. 'AI Extraction' step completes on pathway |
| 4 | Provide employee ID | Employee ID captured, AI acknowledges |
| 5 | Confirm the extracted fields | Policy check runs, 'Policy Check' step completes. Submission proceeds |
| 6 | Claim submitted successfully | Chat shows "CLAIM-XXX has been submitted". Submission summary table at bottom shows the claim row. 'Final Decision' pathway step completes |

**Verify:**
- Claims page UI unchanged — thinking panel, Decision Pathway sidebar, submission summary table all function identically to Phase 6.2 behavior
- `SELECT * FROM claims WHERE claim_number = 'CLAIM-XXX'` returns 1 row with status in ('approved', 'escalated', 'rejected')

### Scenario 5a: Rejection — amount exceeds daily cap [Happy path]

**Precondition:** App running, logged in as user

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a meals receipt with amount exceeding daily meal cap (e.g. SGD 200 when policy cap is SGD 100) | AI extracts fields showing high meal amount |
| 2 | Confirm and submit | Claim submitted as CLAIM-XXX |
| 3 | Log in as reviewer, check Dashboard | Claim shows status 'rejected' |
| 4 | Open Claim Review page | Compliance card shows verdict: FAIL, violations list includes "exceeds daily meal cap", cited clause references meals policy section |

**Verify:**
- `SELECT status, compliance_findings, advisor_decision FROM claims WHERE claim_number = 'CLAIM-XXX'` — status='rejected', compliance verdict='fail', advisor_decision='return_to_claimant'

### Scenario 5b: Rejection — prohibited category [Happy path]

**Precondition:** App running, logged in as user

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | Upload a receipt for a prohibited expense category (e.g. personal entertainment, alcohol) | AI extracts fields |
| 2 | Confirm and submit | Claim submitted as CLAIM-XXX |
| 3 | Log in as reviewer, check Audit Log | Compliance step shows verdict: FAIL with prohibited category violation |

**Verify:**
- `SELECT status, compliance_findings FROM claims WHERE claim_number = 'CLAIM-XXX'` — status='rejected', compliance verdict='fail'

</uat>

---

*Phase: 08-compliance-fraud-advisor-agents*
*Context gathered: 2026-04-06*
