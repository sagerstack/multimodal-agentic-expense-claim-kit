---
name: plan-uat
description: >
  Create UAT acceptance test scenarios for a phase via Q&A with the user.
  Reads CONTEXT.md decisions + bugs.md regressions to draft candidate user
  journeys, refines via multi-choice Q&A, appends <uat> section to CONTEXT.md.
  Run BEFORE /gsd:plan-phase so the planner builds plans that cover all scenarios.
  QA agent reads the same <uat> section as its functional test contract.
---

<essential_principles>

## How Plan-UAT Works

This skill creates acceptance test scenarios that serve two downstream consumers:

1. **gsd-planner** — reads `<uat>` in CONTEXT.md during planning, ensures every scenario step has a covering task
2. **auto-qa agent** — reads `<uat>` during QA validation, executes each scenario as a functional test

The scenarios define WHAT the user should experience, not HOW to build it.

### When to Run

```
/gsd:discuss-phase {N}        → creates CONTEXT.md (decisions)
/sagerstack:plan-uat {N}      → appends <uat> to CONTEXT.md (test scenarios)
/gsd:plan-phase {N}           → planner reads CONTEXT.md including <uat>
/sagerstack:auto-deliver {N}  → QA agent reads <uat> as functional test contract
```

**Auto-triggered by auto-delivery:** If CONTEXT.md exists but has no `<uat>` section, auto-delivery's planning gate (step 4b) automatically invokes this skill before running `/gsd:plan-phase`. The Team Lead runs it directly — same interactive Q&A with the user.

### Core Principle

Scenarios are user journeys, not implementation checks. Each step describes a user action and an observable outcome — what they see, not what the code does.

</essential_principles>

<intake>

**Input:** Phase number (required)

```
/sagerstack:plan-uat 6.1
```

</intake>

<process>

## Step 1: Validate and Load Context

```bash
# Normalize phase number
PHASE="06.1"  # zero-padded from input
PHASE_DIR=$(ls -d .planning/phases/${PHASE}-* 2>/dev/null | head -1)
```

**If no PHASE_DIR:** Error — "Phase directory not found. Run `/gsd:discuss-phase {N}` first."

**Read context files:**
- `{PHASE_DIR}/*-CONTEXT.md` — REQUIRED (must exist from `/gsd:discuss-phase`)
- `docs/project_notes/bugs.md` — for regression scenarios (open bugs fixed in this phase)
- `.planning/ROADMAP.md` — phase goal and success criteria

**If CONTEXT.md missing:** Error — "No CONTEXT.md found. Run `/gsd:discuss-phase {N}` first."

**If CONTEXT.md already has `<uat>` section:** Offer: 1) View existing, 2) Replace, 3) Append more scenarios.

## Step 2: Analyze and Generate Candidate Scenarios

Read the `<decisions>` section from CONTEXT.md. Identify user-facing changes:

- **Something users SEE** → visual state changes, panel updates, new elements
- **Something users DO** → upload, click, type, confirm
- **Something users EXPERIENCE** → response time, error messages, workflow progression
- **Bugs being fixed** → regression scenarios from bugs.md

Generate 3-6 candidate user journey scenarios. Each scenario is a named end-to-end path through the changes.

**Scenario types to consider:**
- **Happy path** — the primary workflow succeeds end-to-end
- **Edge case** — ambiguous input, missing data, boundary conditions
- **Regression** — specific bug symptoms that must not reappear
- **Error recovery** — what happens when something fails

## Step 3: Present Scenarios for Selection

Present candidates as a numbered multi-choice list:

```
Based on the Phase {N} decisions, here are candidate test scenarios:

1. [Happy path] Full claim submission flow
   Upload receipt → extract → confirm → policy check → submit → verify in DB

2. [Regression] BUG-012 — Summary panel updates after submission
   Submit claim → panel shows 100%, CLAIM-XXX header, correct SGD amount

3. [Regression] BUG-013 — No hallucinated submissions
   Verify claim actually persists to database after "submitted" response

4. [Edge case] Foreign currency receipt
   Upload USD receipt → conversion shown → SGD amount in summary panel

Which scenarios should we include? (e.g., "1,2,3" or "all")
```

Wait for user selection.

## Step 4: Deep-Dive Each Selected Scenario

For each selected scenario, present 3-4 questions about expected outcomes. Use multi-choice format:

```
Scenario 1: Full claim submission flow

Q1: After receipt upload and extraction, what should the summary panel show?
  a) Merchant name, amount, category, 33% progress
  b) Just the amount and 50% progress
  c) Nothing until user confirms

Q2: After successful submission, what should the panel header say?
  a) "CLAIM-XXX" (the actual claim number from DB)
  b) "Submitted"
  c) Keep showing "Current Session"

Q3: How should we verify the claim was actually persisted?
  a) Check database directly (SELECT from claims table)
  b) Trust the UI response
  c) Both — UI shows success AND DB has the record
```

After each scenario's questions, offer: "More questions about this scenario, or move to next?"

## Step 5: Write UAT Section

After all scenarios are refined, append the `<uat>` section to the existing CONTEXT.md.

**Format:**

```markdown
<uat>
## Acceptance Test Scenarios

**Created:** {date}
**Phase:** {phase number}

### Scenario 1: {Name} [{type}]

**Precondition:** {Starting state — e.g., "App running, fresh session, no prior claims"}
**Test receipt:** {Which receipt image to use, if applicable}

| Step | User Action | Expected Outcome |
|------|-------------|-----------------|
| 1 | {action} | {observable result} |
| 2 | {action} | {observable result} |
| 3 | {action} | {observable result} |

**Verify:** {Post-scenario check — e.g., "SELECT * FROM claims WHERE claim_number = 'CLAIM-XXX' returns 1 row"}

### Scenario 2: {Name} [{type}]
...

</uat>
```

**Rules for writing scenarios:**
- Steps describe USER actions and OBSERVABLE outcomes only
- No implementation details (no file paths, function names, CSS selectors)
- Expected outcomes are what the user SEES or what the DATABASE contains
- Each scenario is self-contained (own precondition, own verification)
- Regression scenarios reference the bug number they prevent

## Step 6: Confirm and Save

Show the complete `<uat>` section to the user before saving:

```
Here's the UAT section I'll append to CONTEXT.md:

{rendered uat section}

Append to CONTEXT.md? (yes / edit)
```

On "yes" — append to CONTEXT.md (after the existing `</deferred>` closing tag but before the final `---` footer).

On "edit" — ask what to change, revise, re-confirm.

## Step 7: Done

```
UAT scenarios appended to {PHASE_DIR}/{phase}-CONTEXT.md

{N} scenarios ready:
  1. {scenario name} [{type}] — {step count} steps
  2. {scenario name} [{type}] — {step count} steps
  ...

Next: /gsd:plan-phase {N}
The planner will read these scenarios and ensure plans cover all expected outcomes.
```

</process>

<verification>
After writing:
- [ ] `<uat>` section exists in CONTEXT.md
- [ ] Each scenario has: name, type, precondition, steps table, verify
- [ ] Steps describe user actions and observable outcomes (no implementation details)
- [ ] Regression scenarios reference bug numbers
- [ ] Existing CONTEXT.md sections (domain, decisions, specifics, deferred) are unchanged
</verification>
