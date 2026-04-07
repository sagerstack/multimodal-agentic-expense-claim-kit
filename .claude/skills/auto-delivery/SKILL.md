---
name: auto-delivery
description: >
  Autonomous milestone delivery with agent team. Spawns a 2-member team
  (Developer + QA) to implement and verify each GSD plan in a milestone.
  Developer implements directly using sagerstack skills (no GSD delegation).
  QA validates with 9-check quality pipeline + Playwright browser UAT.
  Team Lead orchestrates plan-by-plan, provides progressive user updates,
  updates GSD state. Fully autonomous — only escalates on repeated failure.
---

<essential_principles>

## How Auto-Delivery Works

These principles ALWAYS apply when delivering with the auto-delivery team.

### 1. Fully Autonomous Execution

This is a hands-off workflow. Do NOT ask the user for confirmation, approval, or sign-off at any point during execution. The only times to involve the user are:
- **Planning input**: Before running `/gsd:discuss-phase` for unplanned phases — ask if user has context, requirements, or constraints to feed in
- **UAT planning**: Running `/sagerstack:plan-uat` for phases missing `<uat>` scenarios — interactive Q&A with the user to define acceptance test scenarios
- **Escalation**: QA fails after 3 fix cycles on the same plan
- **Final completion**: Report results when all phases are delivered

Between plans and phases, proceed immediately. No pause, no "Proceed?", no sign-off gate.

### 2. Skill-Guided Direct Implementation (No GSD Delegation)

Developer reads GSD PLAN.md files and implements directly. Developer does NOT invoke `/gsd:execute-phase` or any GSD commands. Instead, sagerstack skills enforce quality:

| Skill | What It Enforces |
|-------|-----------------|
| `sagerstack:software-engineering` | TDD, CamelCase, vertical slice, domain purity, 90% coverage, no hardcoded values |
| `sagerstack:local-testing` | Docker-first execution, env file sync, deployment scripts |

### 3. Plan-by-Plan Execution Within Phases

Each phase has multiple GSD plans (e.g., 06-01, 06-02, 06-03). Execute them sequentially in wave order. Each plan goes through the full develop → QA → fix loop before the next plan starts.

```
For each phase:
  For each GSD plan (in wave order):
    1. Developer implements plan tasks (TDD, Docker-first)
    2. Developer verifies hand-off gate (startup script + all tests pass)
    3. QA runs 9-check pipeline + Playwright browser UAT
    4. If issues → Developer fixes → QA re-verifies (max 3 cycles)
    5. Plan complete → Team Lead updates GSD state
  Phase complete → Team Lead updates ROADMAP.md, STATE.md
```

### 4. Progressive User Updates

Team Lead provides real-time progress narration to the user as agents work. Examples:
- "Developer implementing plan 06-01, task 3/7 — FastAPI lifespan setup..."
- "Developer hand-off gate passed: startup script works, 69/69 tests pass"
- "QA validating plan 06-01: running 9-check pipeline..."
- "QA found 2 issues (sidebar color, missing icon). Sending to developer for fix..."
- "Fix cycle 1 complete. QA re-verifying..."

Summarize agent messages for the user — do not forward raw agent output.

### 5. Team Lead Owns All User Interaction

Teammates NEVER communicate with the user directly. All user-facing communication flows through Team Lead.

### 6. QA Drives Quality Gate

A plan is NOT complete until QA reports all checks as PASS. The loop is:

```
QA validates → issues found? → Developer fixes → QA re-validates → repeat
```

Maximum 3 fix cycles per plan before escalating to user.

### 7. Startup Script Is the Docker Gate

Developer creates and maintains `scripts/local/startup.sh`. This script:
- Runs `docker compose up -d --build`
- Health checks all services
- Runs database migrations
- Verifies all components are healthy

QA uses this script to launch the app. If it fails, the plan is not ready for QA.

### 8. Stitch Designs Are the UI Spec

QA validates visual output against Stitch HTML designs in `docs/ux/`. Playwright browser testing is MANDATORY for all web-facing plans.

### 9. Context Management

Auto-delivery runs long sessions that risk hitting context compaction. Compaction summarizes earlier messages and can lose plan details, QA results, and execution state. Mitigate with:

**a) File paths over pasted content in SendMessage prompts.** Tell teammates to read files themselves instead of pasting full PLAN.md or ROADMAP.md content into the message. This keeps Team Lead's context lean.

**b) Compact after every plan.** After writing SUMMARY.md and updating ROADMAP.md (step 2d), run `/compact` with a focus hint so the compactor preserves what matters:
```
/compact Focus on: current phase {N}, remaining plans queue, latest QA status. GSD state is in ROADMAP.md and STATE.md.
```

**c) GSD files are the source of truth, not context.** If compaction occurs mid-delivery, Team Lead re-reads ROADMAP.md and STATE.md to reconstruct the execution queue. SUMMARY.md files tell which plans are done. Never rely on conversation memory for plan completion status.

</essential_principles>

<intake>

## Scope Resolution

**Step 1: Read project state**
```
Read .planning/STATE.md
Read .planning/ROADMAP.md
```

**Step 2: Determine scope from user input**

| Input | Scope |
|-------|-------|
| `--milestone 2.0` | All phases in v2.0 that are not complete |
| `--phase 6` | Phase 6 only |
| `--skip-research` | Skip research step during `/gsd:plan-phase` (pass `--skip-research` flag) |
| _(empty)_ | All remaining phases in active milestone from STATE.md |

**Step 3: Resolve plan execution queue**
- Read ROADMAP.md to get ordered phase list
- For each phase, discover GSD PLAN.md files in `.planning/phases/{phase-dir}/`
- Check which have SUMMARY.md (already complete) — skip those
- Classify each phase:
  - **Ready**: Has PLAN.md files → add to execution queue (group by wave)
  - **Needs planning**: No PLAN.md files → flag for planning step
- Build ordered queue: phase → wave → plan

**Step 4: Planning gate (if any phases need planning)**

If ALL phases have PLAN.md files, skip to Step 5.

For each phase that needs planning, check three prerequisites in order:

**4a. Discuss phase (if no CONTEXT.md)**
```bash
PADDED_PHASE=$(printf "%02d" ${PHASE})
ls .planning/phases/${PADDED_PHASE}-*/${PADDED_PHASE}-CONTEXT.md .planning/phases/${PADDED_PHASE}-*/CONTEXT.md 2>/dev/null
```

If CONTEXT.md is MISSING:
1. Notify user: "Phase {N} needs context. Running `/gsd:discuss-phase {N}` now..."
2. Run `/gsd:discuss-phase {N}` — this is an interactive Q&A with the user. Team Lead runs it directly (not a subagent). The user answers the questions. This produces CONTEXT.md.
3. After CONTEXT.md is created, proceed to 4b.

If CONTEXT.md EXISTS — skip to 4b.

**4b. Plan UAT (if no `<uat>` in CONTEXT.md)**

Check if CONTEXT.md already has a `<uat>` section:
```bash
grep -l '<uat>' .planning/phases/${PADDED_PHASE}-*/*-CONTEXT.md .planning/phases/${PADDED_PHASE}-*/CONTEXT.md 2>/dev/null
```

If `<uat>` is MISSING:
1. Notify user: "Phase {N} needs acceptance test scenarios. Running `/sagerstack:plan-uat {N}` now..."
2. Run `/sagerstack:plan-uat {N}` — this is an interactive Q&A with the user. Team Lead runs it directly (not a subagent). The user selects scenarios and answers deep-dive questions. This appends `<uat>` to CONTEXT.md.
3. After `<uat>` is appended, proceed to 4c.

If `<uat>` EXISTS — skip to 4c.

**4c. Plan phase (if no PLAN.md)**
For each phase with CONTEXT.md (including `<uat>`) but no PLAN.md files:
1. Run `/gsd:plan-phase {N}` (or `/gsd:plan-phase {N} --skip-research` if `--skip-research` flag was passed to auto-deliver) — this reads CONTEXT.md (including `<uat>` scenarios) and produces PLAN.md files.
2. Re-discover PLAN.md files for the phase and add to execution queue.

**Step 5: Log scope and begin**
```
AUTO-DELIVERY STARTING

Mode: {--milestone X / --phase N / active milestone}
Phases: {list}
Total plans: {count}
Phases planned this session: {list or "none"}
Starting: Phase {N}, Plan {NN}-{NN} — {plan name}
```

Proceed directly to team setup.

</intake>

<workflow_steps>

## Full Delivery Workflow

### Step 1: Team Setup

Create the team and spawn teammates.

Derive team name from the repository name and phase number:
```python
repo_name = os.path.basename(os.getcwd())  # e.g., "agentic-expense-claims"
team_name = f"maverick-{repo_name}_{phase_number}"  # e.g., "maverick-agentic-expense-claims_8.1"
```

```
TeamCreate(team_name="maverick-{repo_name}_{phase_number}", description="Auto-delivery for phase {phase_number}")
```

**Spawn Developer:**
```
Agent(
  subagent_type="auto-developer",
  team_name="maverick",
  name="developer",
  prompt="You are the Developer for auto-delivery of milestone v{milestone}.

  Read these files to understand the project:
  - .planning/STATE.md
  - .planning/ROADMAP.md
  - .claude/CLAUDE.md

  Your sagerstack skills (software-engineering, local-testing) are preloaded.
  You implement GSD plans DIRECTLY — no /gsd:execute-phase delegation.

  Await task assignments from Team Lead."
)
```

**Spawn QA:**
```
Agent(
  subagent_type="auto-qa",
  team_name="maverick",
  name="qa",
  prompt="You are the QA for auto-delivery of milestone v{milestone}.

  Read these files:
  - .planning/STATE.md
  - .planning/ROADMAP.md
  - .claude/CLAUDE.md
  - docs/ux/ (Stitch HTML designs — the UI spec)

  Your sagerstack code-qa skill is preloaded.
  You validate with 9-check pipeline + browser UAT.

  BROWSER UAT IS MANDATORY for all web-facing plans.
  Use Playwright MCP tools (mcp__playwright__*) as the primary browser automation.
  If Playwright MCP is unavailable, fall back to Claude in Chrome MCP tools (mcp__claude-in-chrome__*).
  Use ToolSearch to discover available browser tools before starting UAT.

  Await QA assignments from Team Lead."
)
```

### Step 2: Phase Loop

For each phase in the execution queue:

**Update user:**
```
--- PHASE {N}: {phase name} ---
Goal: {from ROADMAP.md}
Plans: {count} ({list plan numbers})
```

#### For each GSD plan in the phase (wave order):

##### 2a. Developer Implementation

Read the GSD PLAN.md content. Create a task and send to Developer:

```
TaskCreate(subject="Plan {NN}-{NN}: Implement", description="Implement {plan name}")
```

```
SendMessage(
  to="developer",
  content="TASK: Implement Plan {NN}-{NN} — {plan name}

  READ THESE FILES:
  - Plan: .planning/phases/{phase-dir}/{NN}-{NN}-PLAN.md
  - Phase success criteria: .planning/ROADMAP.md (Phase {N} section)
  - Project context: .claude/CLAUDE.md

  Instructions:
  1. Read the plan tasks and implement each one via TDD
  2. Follow your preloaded sagerstack skills (software-engineering, local-testing)
  3. Create/update scripts/local/startup.sh for full stack launch
  4. Commit atomically per task: {type}({phase}-{plan}): {description}

  HAND-OFF GATE (all must pass before reporting):
  - All plan tasks implemented and committed
  - scripts/local/startup.sh runs successfully
  - ALL tests pass: poetry run pytest tests/ -v (zero failures)
  - No uncommitted changes

  Report back with: tasks completed, commits, test results, startup script status."
)
```

**Update user:** "Developer implementing plan {NN}-{NN} — {plan name}..."

Wait for Developer to report completion.

**Update user with Developer summary:** "Plan {NN}-{NN} implemented: {X} tasks, {Y} commits, all tests pass, startup script working."

##### 2b. QA Verification

Create a task and send to QA:

```
TaskCreate(subject="Plan {NN}-{NN}: QA (cycle {C})", description="9-check pipeline + Playwright UAT")
```

```
SendMessage(
  to="qa",
  content="TASK: Verify Plan {NN}-{NN} — {plan name}

  READ THESE FILES:
  - Plan (for success criteria): .planning/phases/{phase-dir}/{NN}-{NN}-PLAN.md
  - Phase success criteria: .planning/ROADMAP.md (Phase {N} section)
  - UAT scenarios: .planning/phases/{phase-dir}/{phase}-CONTEXT.md (read <uat> section)
    (If no <uat> section exists, skip functional UAT and test against success criteria only)
  - Stitch designs: docs/ux/ (compare visual output)

  Instructions:
  1. Launch app: bash scripts/local/startup.sh
  2. Run 9-check quality pipeline (from sagerstack:code-qa)
  3. Run functional UAT from CONTEXT.md <uat> scenarios (Layer 3):
     - Execute each scenario step-by-step
     - Verify expected outcomes at each step
     - Run post-scenario verification checks
  4. Run Playwright MCP browser visual UAT (Layer 4):
     - Navigate to each affected page
     - Validate against Stitch designs
     - Take screenshots (save to .qa/screenshots/ with naming: {phase-no}-{page-name}-{iteration-no}-{desc}.png)
  5. Report structured QA results (PASS/FAIL per criterion and per scenario)

  Report back with full QA report."
)
```

**Update user:** "QA validating plan {NN}-{NN}..."

Wait for QA results.

##### 2c. Fix Loop (if needed)

**If QA reports all PASS:**
- **Update user:** "Plan {NN}-{NN} PASSED QA. {X}/9 quality checks, {Y}/{Z} criteria verified."
- Proceed to 2d.

**If QA reports failures:**
- Increment fix cycle counter
- **Update user:** "QA found {X} issues in plan {NN}-{NN}. Sending to developer for fix (cycle {C}/3)..."
- If counter > 3: Escalate to user (see escalation section)

Send issues to Developer:
```
SendMessage(
  to="developer",
  content="TASK: Fix QA issues for Plan {NN}-{NN} (cycle {C})

  Issues to fix:
  {paste QA issue list}

  Fix ONLY the listed issues. Do not refactor or add unrequested changes.
  Re-run the full hand-off gate before reporting back.
  Report what changed and which issues were addressed."
)
```

**Update user:** "Developer fixing {X} issues..."

Wait for Developer, then re-assign QA (full re-verification). Loop until clean.

##### 2d. Plan Complete — Update GSD State

After QA passes:

1. Create SUMMARY.md for the plan (or note completion):
   ```
   Write .planning/phases/{phase-dir}/{NN}-{NN}-SUMMARY.md with:
   - Plan name, tasks completed, commits, deviations
   - QA cycles count
   - Date completed
   ```

2. Update ROADMAP.md — mark plan as `[x]` complete

3. **Update user:**
   ```
   Plan {NN}-{NN} COMPLETE ({plan name})
     Tasks: {X}/{X}
     QA cycles: {C}
     Phase progress: {completed}/{total} plans
   ```

4. **Compact context** (see principle #9):
   ```
   /compact Focus on: phase {N} delivery, remaining plans: {list remaining}. Completed plans are in ROADMAP.md and SUMMARY.md files. Preserve current teammate state.
   ```

5. Move to next plan in the phase.

#### Phase Complete

After all plans in the phase pass QA:

1. Update STATE.md with phase completion
2. Update ROADMAP.md phase status
3. Mark phase requirements as Complete in REQUIREMENTS.md

**Update user:**
```
--- PHASE {N} COMPLETE: {phase name} ---
  Plans: {X}/{X} complete
  Total QA cycles: {sum}
  Proceeding to Phase {N+1}...
```

Move to next phase immediately.

### Step 3: Delivery Complete

After all phases in scope are done:

```
AUTO-DELIVERY COMPLETE

Milestone: v{milestone}
Phases delivered: {N}/{N}
Plans executed: {total}
Total QA cycles: {sum}

Summary:
  - Phase {N}: {one-line summary}
  - Phase {N+1}: {one-line summary}
  ...

Next steps:
  - Create PR for feature branch
  - Tag release
```

### Step 4: Team Shutdown

```
SendMessage(to="developer", content={"type": "shutdown_request", "reason": "Delivery complete"})
SendMessage(to="qa", content={"type": "shutdown_request", "reason": "Delivery complete"})
TeamDelete
```

</workflow_steps>

<escalation>

## Escalation Format

This is the ONLY point where the user is asked for input during execution.

When QA fails after 3 fix cycles on the same plan:

```
ESCALATION: Plan {NN}-{NN} — {plan name} (Phase {N})

REMAINING FAILURES:
{list each failing criterion with evidence}

FIX ATTEMPTS:
  - Cycle 1: {what was tried, what changed}
  - Cycle 2: {what was tried, what changed}
  - Cycle 3: {what was tried, what changed}

RECOMMENDATION:
{Team Lead's assessment of what's blocking resolution}

OPTIONS:
  1. Manual intervention (you fix, then we re-verify)
  2. Skip this plan and proceed to next
  3. Abort delivery
```

After user responds, resume execution accordingly.

</escalation>

<reference_index>

## Key Files

| File | Purpose |
|------|---------|
| `.planning/STATE.md` | Current phase, progress, context |
| `.planning/ROADMAP.md` | Phase goals, success criteria, plan slots |
| `.planning/REQUIREMENTS.md` | Full requirements list |
| `.planning/phases/` | GSD PLAN.md files (developer reads these directly) |
| `docs/ux/` | Stitch HTML designs (UI spec for QA) |
| `docker-compose.yml` | Full application stack |
| `scripts/local/startup.sh` | Docker stack launch script (developer creates, QA uses) |

</reference_index>
