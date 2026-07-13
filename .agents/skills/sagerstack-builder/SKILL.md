---
name: sagerstack:builder
description: >
  SDLC implementation with agent team. Executes implementation plans produced by
  /sagerstack:planner. Spawns a 2-member builder team (Software Developer + Code QA)
  to implement code via TDD and validate against acceptance criteria. Use when building
  a phase from planned artifacts, implementing stories, or executing implementation plans.
---

<essential_principles>

## How SDLC Building Works

These principles ALWAYS apply when executing implementation plans with the builder team.

### 1. Implementation Plan-Driven Execution

The builder team executes ONLY what the implementation plan specifies. The plan is the single source of truth.

- Read impl plans from `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md`
- Read user stories from `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md` for AC reference
- Read tech research from `docs/phases/epic-{NNN}-{desc}/research/` when external APIs are involved
- Read critical analysis from `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-critical-analysis.md` for documented risks
- Task execution order follows the impl plan structure: MANUAL -> SETUP -> FR -> TR -> AC -> DOC
- Each parent task `[X.0][CATEGORY]` becomes one TaskList item
- Each subtask `[X.Y]` is executed within that TaskList item via TDD

### 2. TDD Non-Negotiable

Every subtask follows red-green-refactor. No exceptions.

1. **RED**: Write a failing test first
2. **GREEN**: Write the minimum code to make the test pass
3. **REFACTOR**: Clean up while keeping tests green
4. Repeat for next subtask

The Software Developer agent has `/sagerstack:software-engineering` preloaded, which enforces:
- Vertical Slice + DDD structure
- CamelCase naming everywhere
- Strict domain purity (no infrastructure imports in domain)
- Custom exceptions + Result pattern
- Structured logging
- No hardcoded values (all config from .env files)
- 90%+ code coverage

### 3. Skill-Enforced Quality

Quality standards are enforced through skill preloading, not manual instruction.

| Agent | Preloaded Skills | Standards Enforced |
|-------|-----------------|-------------------|
| Software Developer | `sagerstack:software-engineering`, `sagerstack:local-testing`, `project-memory` | Architecture, TDD, coverage, Docker, env files |
| Code QA | `sagerstack:code-qa`, `project-memory` | AC validation, quality pipeline, UAT |

The Developer does not need to be told HOW to write code. The skills define the how. The impl plan defines the WHAT.

### 4. QA Gate Per Story

After ALL implementation tasks for a story are complete, Code QA validates:

1. **AC-Driven Validation**: Parse each AC from the user story, run corresponding tests, report pass/fail
2. **Quality Pipeline (9 Checks)**: Test suite, coverage (>= 90%), type checking, linting, formatting, security, Docker build, CHANGELOG, git status
3. **Flexible UAT**: If docker-compose exists, spin up and test via HTTP. If local process exists, start and test. Otherwise skip UAT.
4. **Code Quality Inspection**: CamelCase naming, domain purity, no hardcoded values

QA operates as a zero-trust validator. It re-runs all tests independently and never trusts developer assertions.

### 5. Targeted Remediation

When QA finds failures, remediation is TARGETED, not broad.

1. QA maps each failure to a specific impl plan task (Failure-to-Task Mapping)
2. Team Lead creates remediation tasks ONLY for the failed areas
3. Developer fixes ONLY the identified issues
4. QA re-validates the FULL story (not just fixes)
5. Maximum 2 remediation cycles per story before escalation to user

### 6. Project Memory Integration

Both agents read and write project memory to maintain cross-session knowledge.

| Agent | Reads | Writes |
|-------|-------|--------|
| Software Developer | `docs/project_notes/decisions.md`, `docs/project_notes/key_facts.md`, `docs/project_notes/bugs.md` | `docs/project_notes/bugs.md`, `docs/project_notes/key_facts.md` |
| Code QA | `docs/project_notes/bugs.md`, `docs/project_notes/decisions.md` | `docs/project_notes/bugs.md`, `docs/project_notes/issues.md` |

### 7. Configurable Execution Mode

| Mode | Behavior | When to Use |
|------|----------|-------------|
| `single-epic` (default) | Execute one epic, report completion, stop | Normal usage |
| `--continue` | After epic completes, auto-chain to next epic if plans exist | Multi-epic sprint |

With `--continue`, if next epic plans do not exist, prompt user to run `/sagerstack:planner` first.

</essential_principles>

<intake>

## Phase Selection

Before executing, read the project context and available phase plans.

**Step 1: Read project context**
```
Read docs/project-context.md
```

**Step 2: Scan for planned phases**
```
Glob docs/phases/epic-*/plans/story-*-plan.md
```

**Step 3: Identify current state**
- Which phases have impl plans (ready to build)?
- Which phases are already built (all tasks marked `[x]`)?
- Which phase is next in dependency order?

**Step 4: Present to user**
```
BUILDER STATUS:

Epics ready to build:
  - epic-001-{desc}: {epic name} ({N} stories, {M} total tasks)
  - epic-002-{desc}: {epic name} ({N} stories, {M} total tasks)

Epics already built:
  - (none yet)

Which epic would you like to build?
Options:
  1. epic-001-{desc} (recommended - first in dependency order)
  2. epic-002-{desc}
  3. Specific story within an epic

Execution mode:
  - Default: single epic
  - Add --continue to auto-chain epics
```

**Wait for user to select epic/story and execution mode.**

</intake>

<routing>

| User Intent | Action |
|-------------|--------|
| "build epic 001", "execute epic", "implement epic" | Read `workflows/execute-phase.md`, execute full epic |
| "build story 002 in epic 001", "implement story", "just story NNN" | Read `workflows/execute-story.md`, execute single story |
| "check status", "where are we", "what's done" | Scan impl plans for `[x]` markers, report progress |
| "resume", "continue from where we left off" | Read TaskList + impl plan `[x]` markers, resume from first incomplete task |
| "fix QA failures", "remediation" | Read `workflows/remediation-loop.md`, execute targeted fixes |
| "setup environment first" | Read `workflows/setup-environment.md`, prepare local dev |

</routing>

<workflow_steps>

## Full Execution Workflow (6 Steps)

### Step 1: Intake and Epic Selection

1. Read `docs/project-context.md` to understand milestones and epics
2. Scan `docs/phases/` for available impl plans
3. Present epic status to user (see intake section above)
4. User selects epic and execution mode
5. Read all impl plans for the selected epic:
   - `docs/phases/epic-{NNN}-{desc}/plans/story-*-plan.md`
   - `docs/phases/epic-{NNN}-{desc}/stories/story-*.md`
   - `docs/phases/epic-{NNN}-{desc}/plans/story-*-critical-analysis.md`
   - `docs/phases/epic-{NNN}-{desc}/research/` (if exists)
6. Determine story execution order from dependencies

### Step 2: Team Setup

Create the builder team and spawn teammates.

```
TeamCreate(team_name="builder-epic-{NNN}", description="Building epic-{NNN}-{desc}: {epic name}")
```

**Spawn Software Developer:**
```
Task(
  subagent_type="builder-developer",
  team_name="builder-epic-{NNN}",
  name="software-developer",
  prompt="You are the Software Developer for epic-{NNN}-{desc}. Your skills (software-engineering, local-testing, project-memory) are preloaded. Follow TDD for every task. Read impl plans at: docs/phases/epic-{NNN}-{desc}/plans/. Read stories at: docs/phases/epic-{NNN}-{desc}/stories/. Work on branch: feature/epic-{NNN}-story-{NNN}. Await task assignments from Team Lead."
)
```

**Spawn Code QA:**
```
Task(
  subagent_type="builder-qa",
  team_name="builder-epic-{NNN}",
  name="code-qa",
  prompt="You are the Code QA for epic-{NNN}-{desc}. Your skills (code-qa, project-memory) are preloaded. You validate acceptance criteria, run the 9-check quality pipeline, and perform UAT. You NEVER modify source code. Read stories at: docs/phases/epic-{NNN}-{desc}/stories/. Read plans at: docs/phases/epic-{NNN}-{desc}/plans/. Await QA assignments from Team Lead."
)
```

**Create task list from impl plans:**

For each story (in dependency order), for each parent task `[X.0][CATEGORY]` in the impl plan:
```
TaskCreate(
  subject="[US-{NNN}] [X.0][CATEGORY] {description}",
  description="Implement all subtasks [X.1] through [X.N]. Impl plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md. Story: docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md."
)
```

Create QA validation task per story:
```
TaskCreate(
  subject="[US-{NNN}] QA Validation",
  description="Validate all AC for US-{NNN}. Run 9-check quality pipeline. Perform UAT."
)
TaskUpdate(qaTaskId, addBlockedBy=[all story N impl task IDs])
```

### Step 3: Pre-Implementation Setup

Before assigning implementation tasks, verify environment readiness.

1. **Check for existing feature branch or create one:**
   ```
   git checkout -b feature/epic-{NNN}-story-{NNN}
   ```
   If branch already exists (resuming), check it out.

2. **Merge latest from main:**
   ```
   git merge main
   ```

3. **Check local environment:**
   - Docker running? (`docker info`)
   - Dependencies installed? (`poetry install`)
   - Environment files present? (`.env.local`, `tests/.env.test`)

4. **Handle MANUAL tasks:**
   If impl plan contains `[MANUAL]` tasks:
   - Notify user: "Manual action required: {description}. Please complete and confirm."
   - Block downstream tasks until user confirms

### Step 4: Story Execution Loop

For each story in the epic (in dependency order):

**4a. Assign implementation tasks to Developer**

For each parent task (SETUP first, then FR/TR/AC in impl plan order):
```
TaskUpdate(taskId, owner="software-developer")
SendMessage(
  type="message",
  recipient="software-developer",
  content="TASK ASSIGNMENT:
  - Task ID: {taskId}
  - Subject: [X.0][CATEGORY] {description}
  - Impl Plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md
  - Story: docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md
  - Instructions: Implement all subtasks [X.1] through [X.N] via TDD (red-green-refactor).
  - After completing all subtasks: Run quality checks (pytest, coverage, mypy, ruff, bandit).
  - If quality checks pass: Commit with descriptive message.
  - Mark subtasks [x] in impl plan as you complete them.",
  summary="Implement [X.0][CATEGORY] for US-{NNN}"
)
```

Wait for Developer to complete each task before assigning the next.

**4b. Developer implements via TDD**

Developer follows this cycle for each subtask:
1. Read subtask from impl plan
2. Write failing test (RED)
3. Write minimal code to pass (GREEN)
4. Refactor (REFACTOR)
5. After all subtasks in parent task done, run quality checks:
   - `poetry run pytest tests/ -v`
   - `poetry run pytest --cov=src --cov-fail-under=90`
   - `poetry run mypy src/ --strict`
   - `poetry run ruff check src/ tests/`
   - `poetry run bandit -r src/`
6. If all pass, commit:
   ```
   git add {relevant files}
   git commit -m "{descriptive message}"
   ```
7. Mark subtasks `[x]` in impl plan file
8. Mark TaskList task as completed
9. Report to Team Lead

**4c. After all impl tasks for a story complete, assign QA**

```
TaskUpdate(qaTaskId, owner="code-qa")
SendMessage(
  type="message",
  recipient="code-qa",
  content="QA ASSIGNMENT:
  - Story: docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md
  - Impl Plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md
  - Instructions: Validate ALL acceptance criteria. Run full 9-check quality pipeline. Perform UAT if docker-compose or app entry point exists. Generate QA report at docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md.
  - If ALL pass: Report PASS with summary.
  - If ANY fail: Report FAIL with Failure-to-Task Mapping for targeted remediation.",
  summary="QA validate US-{NNN}"
)
```

**4d. Handle QA results**

**If QA PASSES:**
- Story is complete
- Move to next story
- Create feature branch for next story if needed

**If QA FAILS:**
- Read QA report and extract Failure-to-Task Mapping
- Create targeted remediation tasks:
  ```
  TaskCreate(
    subject="[US-{NNN}] Remediation: {failure description}",
    description="Fix: {specific issue}. Source: {file:line}. Related task: [X.0][CATEGORY]. Test that must pass: {test reference}."
  )
  TaskUpdate(remediationTaskId, owner="software-developer")
  ```
- Assign remediation to Developer
- After Developer fixes, re-assign QA (full re-validation)
- Track retry count: max 2 per story

**If QA fails after 2 retries, escalate to user:**
```
ESCALATION: US-{NNN} in epic-{NNN}-{desc}

WHAT FAILED:
- {Concise description of remaining failures}

WHAT WAS ATTEMPTED:
- Retry 1: {what was tried and result}
- Retry 2: {what was tried and result}

REMAINING ISSUES:
- {Issue 1 with file/line reference}
- {Issue 2 with file/line reference}

RECOMMENDATION:
- {Suggested manual intervention}

ARTIFACTS:
- QA Report: docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md
- Impl Plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md
```

### Step 5: Epic Completion

After all stories in the epic pass QA:

1. **Final verification:**
   - Run full test suite across entire codebase
   - Verify all impl plan tasks marked `[x]`
   - Verify all QA reports show PASS

2. **Update project status:**
   - Log epic completion in `docs/project_notes/issues.md`

3. **Report to user:**
   ```
   EPIC COMPLETE: epic-{NNN}-{desc} - {epic name}

   Stories completed: {N}/{N}
   Total tasks executed: {X}
   Test coverage: {N}%
   QA retries: {N}
   Feature branches: feature/epic-{NNN}-story-{NNN}

   Next steps:
   - Create PR(s) for feature branches
   - Run /sagerstack:builder for next epic (if planned)
   - Run /sagerstack:planner for next epic (if not yet planned)
   ```

### Step 6: Team Shutdown

1. **Graceful shutdown:**
   ```
   SendMessage(type="shutdown_request", recipient="software-developer", content="Epic complete. Shutting down.")
   SendMessage(type="shutdown_request", recipient="code-qa", content="Epic complete. Shutting down.")
   ```

2. **Wait for shutdown confirmations**

3. **Delete team:**
   ```
   TeamDelete
   ```

4. **Continuation mode check:**
   - If `--continue` flag was set:
     - Check if `docs/phases/epic-{next}/plans/` exists
     - If yes: Restart from Step 1 with next epic (create new team)
     - If no: "Next epic not yet planned. Please run /sagerstack:planner for the next epic."
   - If default mode: Done. Return to user.

</workflow_steps>

<team_configuration>

## Builder Team Definition

### Team Structure

| Role | Agent Name | Subagent Type | Permission Mode | Model | Skills Preloaded |
|------|-----------|---------------|-----------------|-------|-----------------|
| Team Lead | (main session) | N/A (delegate mode) | `delegate` | `opus` | N/A |
| Software Developer | `software-developer` | `builder-developer` | `bypassPermissions` | `sonnet` | `sagerstack:software-engineering`, `sagerstack:local-testing`, `project-memory` |
| Code QA | `code-qa` | `builder-qa` | `plan` | `opus` | `sagerstack:code-qa`, `project-memory` |

### Subagent Definition: builder-developer

**File:** `.Codex/agents/builder-developer.md`

```yaml
---
name: builder-developer
description: >
  Software Developer for the SDLC builder team. Implements code via TDD
  following software-engineering and local-testing skill standards.
  CamelCase naming, Vertical Slice + DDD, 90%+ coverage.
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - SendMessage
  - TaskUpdate
  - TaskList
model: sonnet
permissionMode: bypassPermissions
maxTurns: 200
skills:
  - sagerstack:software-engineering
  - sagerstack:local-testing
  - project-memory
---
```

### Subagent Definition: builder-qa

**File:** `.Codex/agents/builder-qa.md`

```yaml
---
name: builder-qa
description: >
  Code QA for the SDLC builder team. Validates acceptance criteria pass/fail,
  runs quality check pipeline, performs flexible UAT. Zero-trust validator
  that never modifies source code.
tools:
  - Read
  - Glob
  - Grep
  - Bash
  - SendMessage
  - TaskUpdate
  - TaskList
  - Write
model: opus
permissionMode: plan
maxTurns: 80
skills:
  - sagerstack:code-qa
  - project-memory
---
```

### File Ownership Rules

To prevent race conditions, each teammate owns specific files:

| Agent | Owns (write access) | Reads |
|-------|---------------------|-------|
| Software Developer | `src/`, `tests/`, impl plan `[x]` markers, developer log, CHANGELOG | All phase artifacts, codebase |
| Code QA | QA report files (`docs/phases/epic-{NNN}-{desc}/qa/`) only | `src/`, `tests/`, all epic artifacts (read-only) |

</team_configuration>

<reference_index>

## Reference Files

All in `references/`:

**Task Execution:**
- task-execution.md -- Task execution patterns adapted from process-implementation-plan (checkbox protocol, relevant files tracking, subtask ordering)

**Logging:**
- developer-log.md -- Developer logging format adapted for single-agent model (6 sections, timestamp format, complete log structure)

**Git Workflow:**
- git-workflow.md -- Branch naming, commit conventions, PR creation, merge protocol

**Escalation:**
- escalation-protocol.md -- When and how to escalate to user (QA failures, infrastructure issues, blocked tasks, agent crashes)

</reference_index>

<workflows_index>

## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| execute-phase.md | Full phase execution with team orchestration |
| execute-story.md | Single story execution within a phase |
| remediation-loop.md | QA failure remediation with targeted fixes |
| setup-environment.md | Pre-implementation local environment setup |

</workflows_index>

<verification>

## Post-Execution Checklist

After completing an epic, verify:

### Code Quality
- [ ] All tests pass (`poetry run pytest tests/ -v`)
- [ ] Coverage >= 90% (`poetry run pytest --cov=src --cov-fail-under=90`)
- [ ] Zero type errors (`poetry run mypy src/ --strict`)
- [ ] Zero lint violations (`poetry run ruff check src/ tests/`)
- [ ] Zero security issues (`poetry run bandit -r src/`)

### Architecture Standards
- [ ] CamelCase naming throughout (classes, functions, variables, tests)
- [ ] Domain layer has no infrastructure imports
- [ ] Vertical Slice structure (organize by feature, not technical layer)
- [ ] No hardcoded values (all config from .env files)
- [ ] Custom exceptions for domain errors

### Implementation Completeness
- [ ] All impl plan tasks marked `[x]`
- [ ] All QA reports show PASS
- [ ] Developer log complete (all 6 sections)
- [ ] CHANGELOG updated for each story

### Git
- [ ] Feature branch per story (`feature/epic-{NNN}-story-{NNN}`)
- [ ] All changes committed with descriptive messages
- [ ] Latest main merged before pushing
- [ ] No uncommitted changes (`git status` clean)

### Project Memory
- [ ] New bugs documented in `docs/project_notes/bugs.md`
- [ ] New config facts in `docs/project_notes/key_facts.md`
- [ ] Story completion logged in `docs/project_notes/issues.md`

</verification>
