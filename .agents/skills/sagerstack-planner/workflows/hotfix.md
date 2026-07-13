# Hotfix Workflow

## Purpose

Abbreviated planning workflow for bug fixes. Creates a lightweight single-story epic with minimal ceremony. `--skip-research` is always active.

## Entry Point

User runs `/sagerstack:hotfix` or selects "hotfix" from planner intake.

## Bug Classification

Before starting, classify the bug:

| Class | Criteria | Action |
|-------|----------|--------|
| Simple | Single file fix, clear root cause, no architectural impact | Team Lead handles alone (no team spawn) |
| Moderate | Multi-file fix, needs investigation, limited scope | Spawn BA only for story creation |
| Complex | Architectural impact, unclear root cause, multiple systems | Upgrade to full planner workflow (`/sagerstack:planner`) |

Ask user: "Describe the bug. Include: what happens, what should happen, and where you think the issue is."

Based on the description, classify and confirm: "This looks like a {simple/moderate/complex} bug. {Action}. Proceed?"

If complex: redirect to `/sagerstack:planner` with `--skip-research` flag.

## Workflow (5 Steps)

### Step 1: Create Bug Epic

**Actor**: Team Lead

1. Create epic folder: `docs/phases/epic-{NNN}-hotfix-{desc}/`
2. Determine epic number:
   - Read `docs/project-context.md`
   - Use next available epic number
   - Add entry to project-context.md as a hotfix epic
3. Create minimal epic.md:

```markdown
# Epic: Hotfix - {bug description}

## Metadata
| Field | Value |
|-------|-------|
| ID | EP-{NNN} |
| Title | Hotfix: {brief description} |
| Type | Hotfix |
| Research Mode | Skipped |
| Created | {YYYY-MM-DD HH:mm:ss} |
| Status | Final |

## Bug Description
**Reported behavior**: {what happens}
**Expected behavior**: {what should happen}
**Suspected location**: {where user thinks the issue is}

## User Stories List
| ID | Title | Status | Priority | AI Complexity Score |
|----|-------|--------|----------|---------------------|
| US-001 | Fix: {bug description} | Final | Must-have | {1-10} |
```

### Step 2: Create Bug Story

**Actor**: Team Lead (simple) or BA (moderate)

Create a minimal bug-fix story at `docs/phases/epic-{NNN}-hotfix-{desc}/stories/story-001-fix-{desc}.md`:

**Functional Requirements** (minimal):

| Status | ID | Category | Requirement | Description | Priority |
|--------|-----|----------|-------------|-------------|----------|
| [ ] | FR-1 | Bug Fix | Reproduce bug | Write failing test that reproduces the reported behavior | P1 |
| [ ] | FR-2 | Bug Fix | Fix bug | Implement fix so the failing test passes | P1 |
| [ ] | FR-3 | Bug Fix | Regression test | Verify no existing tests broken by the fix | P1 |

**Technical Requirements** (minimal):

| Status | ID | Category | Requirement | Description | Target |
|--------|-----|----------|-------------|-------------|--------|
| [ ] | TR-1 | Reliability | No regression | All existing tests continue to pass | 100% pass rate |

**Acceptance Criteria** (minimal):

| Status | ID | Given | When | Then | Type | Validates | Priority |
|--------|-----|-------|------|------|------|-----------|----------|
| [ ] | AC-1 | {bug condition} | {trigger action} | {correct behavior} | Functional - Bug Fix | FR-1, FR-2 | P1 |
| [ ] | AC-2 | The fix is applied | Running full test suite | All tests pass including new regression test | Functional - Regression | FR-3, TR-1 | P1 |

### Step 3: User Confirms (Single Q&A Checkpoint)

**Actor**: Team Lead presents to user

Present the bug story summary:
- Bug description
- FR/TR/AC
- Proposed fix approach (if known)

Ask: "Does this capture the bug correctly? Any adjustments?"

**One round only** — adjust if needed, then proceed.

### Step 4: Generate Simplified Implementation Plan

**Actor**: Team Lead (generates directly — no Architect, no Critic)

Create implementation plan at `docs/phases/epic-{NNN}-hotfix-{desc}/plans/story-001-fix-{desc}-plan.md`:

**Task structure** (fixed for all hotfixes):

```markdown
## Task-Based Implementation Plan

### 1. Reproduce Bug
- [ ] **[1.0][FR-1] Reproduce bug with failing test**
  - [ ] [1.1] Write test that triggers the reported bug behavior
  - [ ] [1.2] Verify test fails (RED)

### 2. Fix Bug
- [ ] **[2.0][FR-2] Implement fix**
  - [ ] [2.1] Identify root cause
  - [ ] [2.2] Implement minimal fix
  - [ ] [2.3] Verify failing test now passes (GREEN)
  - [ ] [2.4] Refactor if needed (REFACTOR)

### 3. Regression Test
- [ ] **[3.0][FR-3, TR-1] Verify no regression**
  - [ ] [3.1] Run full test suite
  - [ ] [3.2] Run coverage check (>= 90%)
  - [ ] [3.3] Run type check (mypy --strict)
  - [ ] [3.4] Run linter (ruff check)

### 4. Documentation
- [ ] **[4.0][DOC] Update documentation**
  - [ ] [4.1] Update CHANGELOG with bug fix entry
  - [ ] [4.2] Log bug in docs/project_notes/bugs.md
  - [ ] [4.3] Commit with descriptive message
```

### Step 5: Ready for Builder

**Actor**: Team Lead

1. Verify all artifacts exist:
   ```
   docs/phases/epic-{NNN}-hotfix-{desc}/
     epic.md
     stories/story-001-fix-{desc}.md
     plans/story-001-fix-{desc}-plan.md
   ```
2. Report to user:
   ```
   HOTFIX PLANNED: EP-{NNN} - {bug description}

   Artifacts:
   - Epic: docs/phases/epic-{NNN}-hotfix-{desc}/epic.md
   - Story: docs/phases/epic-{NNN}-hotfix-{desc}/stories/story-001-fix-{desc}.md
   - Plan: docs/phases/epic-{NNN}-hotfix-{desc}/plans/story-001-fix-{desc}-plan.md

   Next: Run /sagerstack:builder {NNN} to implement the fix.
   ```

## Key Differences from Full Planner

| Aspect | Full Planner | Hotfix |
|--------|-------------|--------|
| Research | Full (or --skip-research) | Always skipped |
| Team spawn | 4 agents | 0 (simple) or 1 BA (moderate) |
| Q&A checkpoints | 3 | 1 |
| Impl plan author | Solution Architect | Team Lead |
| Critical review | Yes (with 2 refinement cycles) | No |
| Story count | Multiple | Always 1 |
| Steps | 9 | 5 |
