---
name: sagerstack:verify
description: >
  Interactive UAT verification skill. Walks the user through acceptance criteria
  one at a time, records pass/fail/skip results, generates UAT report, and routes
  remediation gaps to /sagerstack:builder. Solo skill (no agent team).
---

<essential_principles>

## How Interactive UAT Works

These principles ALWAYS apply when verifying acceptance criteria with the user.

### 1. AC-Driven Verification

All verification is derived from the Acceptance Criteria tables in user story files. Each AC row (Given/When/Then) becomes one verification item. No ad-hoc testing — only structured AC validation.

### 2. One at a Time

Present ONE acceptance criterion to the user at a time. Wait for their response before proceeding to the next. Never batch or summarize — each AC gets individual attention and a clear pass/fail/skip verdict.

### 3. Severity Inferred, Never Asked

When the user reports a failure, infer severity from the AC context:
- **Critical**: AC validates a core functional requirement (FR P1) or blocking integration
- **Major**: AC validates important functionality (FR P2) or significant user workflow
- **Minor**: AC validates edge cases, cosmetic issues, or low-priority requirements

Never ask the user "How severe is this?" — determine it from the AC's priority, type, and the FR/TR it validates.

### 4. Persistent and Resumable

Write results incrementally to the UAT report file. If the session is interrupted, the user can resume from where they left off. The report file is the source of truth for progress.

### 5. Remediation Routing

After verification completes, gaps (FAIL results) are summarized with remediation tasks. The user can choose to:
- Route failures to `/sagerstack:builder` for automated fixing
- Document failures for later resolution
- Re-verify specific ACs after manual fixes

</essential_principles>

<intake>

## UAT Verification Intake

1. Read `docs/project-context.md` to identify available epics
2. Scan `docs/phases/` for epics with completed QA reports (indicating builder has run)
3. Check for existing `uat-report.md` files (indicating previous UAT sessions)

**What would you like to verify?**

Options:
- Specify an epic (e.g., "epic 001", "verify epic 001")
- Specify a story (e.g., "story 002 in epic 001")
- "resume" to continue from last UAT session
- "status" to see UAT progress across all epics

**Wait for response before proceeding.**

</intake>

<routing>

| Response | Action |
|----------|--------|
| Epic number (e.g., "001", "epic 001", "verify 001") | Execute UAT for all stories in the epic |
| Story reference (e.g., "story 002 in epic 001") | Execute UAT for single story |
| "resume", "continue" | Find most recent incomplete uat-report.md, resume from first unverified AC |
| "status", "progress" | Scan all uat-report.md files, present summary table |

</routing>

<workflow_steps>

## UAT Verification Workflow (4 Steps)

### Step 1: Load Story and Parse ACs

**Actor**: Codex (solo)

1. Read the target user story file: `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md`
2. Parse the Acceptance Criteria table:
   - Extract each row: ID, Given, When, Then, Type, Validates, Priority
   - Sort by Priority (P1 first, then P2, etc.)
3. Check for existing UAT report at `docs/phases/epic-{NNN}-{desc}/qa/uat-report.md`
   - If exists: load previous results, identify unverified ACs
   - If not: create new report file with header
4. Present verification plan to user:
   ```
   UAT VERIFICATION: US-{NNN} - {story title}

   Total ACs: {N}
   Previously verified: {N} (if resuming)
   Remaining: {N}

   Verification order (by priority):
   1. AC-{N}: {brief description} [P1]
   2. AC-{N}: {brief description} [P1]
   3. AC-{N}: {brief description} [P2]
   ...

   Ready to begin? (yes / skip to AC-{N} / cancel)
   ```

### Step 2: Interactive Verification Loop

**Actor**: Codex presents, user responds

For each AC (in priority order):

**2a. Present the AC:**
```
--- AC-{N} ({current}/{total}) ---
Type: {Functional - Happy Path / Technical - Performance / etc.}
Validates: {FR-1, TR-2, etc.}
Priority: {P1/P2/P3}

GIVEN: {context from AC table}
WHEN:  {action from AC table}
THEN:  {expected outcome from AC table}

Verification steps:
1. {Specific instruction derived from the Given/When/Then}
2. {What to check or observe}
3. {Expected result to confirm}

Result? (pass / fail / skip / stop / back)
```

**2b. Handle user response:**

| Response | Action |
|----------|--------|
| "pass", "yes", "y", "p" | Record PASS, write to report, proceed to next AC |
| "fail", "no", "n", "f" | Ask "What did you observe?", record user's observation, infer severity from AC context, record FAIL with details, proceed to next AC |
| "skip", "s" | Ask "Why skip? (not testable / not applicable / defer)", record SKIPPED with reason, proceed to next AC |
| "stop", "quit", "q" | Save progress to report, present summary of completed ACs, exit |
| "back", "b", "previous" | Go back to previous AC, allow re-verification |

**2c. Write results incrementally:**
After each AC response, update the UAT report file immediately. This ensures progress is saved even if the session is interrupted.

### Step 3: Generate UAT Report

**Actor**: Codex (solo)

After all ACs are verified (or user stops), finalize the report.

Save to: `docs/phases/epic-{NNN}-{desc}/qa/uat-report.md`

```markdown
# UAT Report: US-{NNN} - {story title}

## Metadata
| Field | Value |
|-------|-------|
| Story ID | US-{NNN} |
| Epic | EP-{NNN} - {epic name} |
| Date Started | {YYYY-MM-DD} |
| Date Completed | {YYYY-MM-DD or "In Progress"} |
| Status | PASS / FAIL / IN PROGRESS |
| Total ACs | {N} |
| Passed | {N} |
| Failed | {N} |
| Skipped | {N} |
| Not Verified | {N} |

## Results

| AC ID | Description | Priority | Type | Result | Severity | Notes |
|-------|-------------|----------|------|--------|----------|-------|
| AC-1 | {brief} | P1 | Happy Path | PASS | - | - |
| AC-2 | {brief} | P1 | Failure Scenario | FAIL | Major | {user observation} |
| AC-3 | {brief} | P2 | Edge Case | SKIPPED | - | {skip reason} |

## Gaps (Failures)

### GAP-1: AC-{N} - {description}
- **Severity**: {Critical/Major/Minor}
- **AC**: Given {context} When {action} Then {expected}
- **Observed**: {what user reported}
- **Validates**: {FR/TR IDs}
- **Remediation**: {suggested fix approach}
- **Impl Plan Task**: [{X}.0][CATEGORY] (if traceable to impl plan)

## Remediation Summary

| Priority | Gap Count | Suggested Action |
|----------|-----------|-----------------|
| Critical | {N} | Must fix before release |
| Major | {N} | Should fix before release |
| Minor | {N} | Can defer to next iteration |

## Verification Log
| Timestamp | AC ID | Action | Details |
|-----------|-------|--------|---------|
| {HH:mm} | AC-1 | VERIFIED | PASS |
| {HH:mm} | AC-2 | VERIFIED | FAIL - {brief} |
```

### Step 4: Remediation Routing

**Actor**: Codex presents options, user decides

After report is generated, if there are any FAIL results:

```
UAT COMPLETE: US-{NNN} - {story title}

Results: {N} PASS / {N} FAIL / {N} SKIPPED

Gaps requiring remediation:
1. [Critical] AC-{N}: {description}
2. [Major] AC-{N}: {description}

Options:
1. Fix now — Route gaps to /sagerstack:builder for automated remediation
2. Fix later — Document gaps, continue to next story
3. Re-verify — Re-run specific ACs (e.g., after manual fix)
```

| Response | Action |
|----------|--------|
| "fix", "fix now", "1" | Summarize gaps as remediation tasks, instruct user to run `/sagerstack:builder` with story reference |
| "later", "defer", "2" | Mark report as "FAIL - Deferred", log gaps in `docs/project_notes/issues.md` |
| "re-verify", "recheck", "3" | Ask which ACs to re-verify, loop back to Step 2 for those ACs only |

If all ACs PASS:
```
UAT COMPLETE: US-{NNN} - {story title}

All {N} acceptance criteria PASSED.

UAT report saved to: docs/phases/epic-{NNN}-{desc}/qa/uat-report.md

Next steps:
- Verify next story in this epic
- Run /sagerstack:verify for another epic
```

</workflow_steps>

<verification>

## Post-UAT Checklist

After completing UAT for a story:

### Report Quality
- [ ] UAT report exists at `docs/phases/epic-{NNN}-{desc}/qa/uat-report.md`
- [ ] All ACs have a result (PASS, FAIL, or SKIPPED — no blanks)
- [ ] Every FAIL has user observation recorded
- [ ] Every FAIL has severity inferred (not asked)
- [ ] Every SKIP has a reason recorded

### Gap Management
- [ ] All Critical gaps have remediation tasks defined
- [ ] All Major gaps have remediation tasks defined
- [ ] Gaps are logged in `docs/project_notes/issues.md` if deferred

### User Confirmation
- [ ] User was presented with remediation options
- [ ] User's chosen action was executed (fix/defer/re-verify)

</verification>
