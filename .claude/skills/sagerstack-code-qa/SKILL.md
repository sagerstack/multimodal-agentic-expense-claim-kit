---
name: sagerstack:code-qa
description: >
  Code QA validation skill for the builder team's QA agent. Provides AC-driven
  validation, test execution, coverage verification, code quality checks, flexible
  UAT, granular failure mapping, and QA report generation. Zero-trust validator
  that never modifies source code. Operates in read-only mode with Bash for
  running tests and inspecting outputs.
---

<essential_principles>

## How Code QA Validation Works

These principles ALWAYS apply when validating implementation quality.

### 1. AC-Driven Validation (Primary Gate)

Every validation starts from the user story's Acceptance Criteria table. Parse each AC independently and validate against the codebase.

**Parsing Process:**
1. Read user story at `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md`
2. Extract the AC table columns: ID, Given, When, Then, Type, Validates, Priority
3. For each AC, determine the validation method based on Type

| AC Type | Validation Method |
|---------|-------------------|
| Functional - Happy Path | Run corresponding test, verify expected outcome |
| Functional - Failure Scenario | Run corresponding test, verify error handling |
| Functional - Edge Case | Run corresponding test, verify edge behavior |
| Functional - Error Handling | Run corresponding test, verify error response |
| Functional - Integration | Run integration test with real or mocked services |
| Functional - End-to-End | Run E2E test via docker-compose + curl |
| Technical - Performance | Run performance test, verify threshold |
| Technical - Security | Run security scan, verify no vulnerabilities |
| Technical - Reliability | Run reliability test, verify SLA |

4. Locate the corresponding test(s) in the codebase using Grep/Glob
5. Run each test independently via `poetry run pytest {test_file}::{test_function} -v`
6. Record PASS or FAIL with evidence (test output, assertion details)

**AC Validation Report (per AC):**
```markdown
### AC-{N}: {Description from Then column}
- **Status**: PASS / FAIL
- **Validates**: {FR/TR IDs from Validates column}
- **Evidence**:
  - Test: {test_file}::{test_function}
  - Result: {pass/fail with output excerpt}
  - Notes: {observations, warnings, or context}
```

### 2. Test Execution (Zero Trust)

Re-run ALL tests independently. Never trust developer assertions or prior test results.

**Test execution order:**
1. Run full test suite: `poetry run pytest tests/ -v`
2. Run coverage: `poetry run pytest --cov=src --cov-report=term-missing --cov-fail-under=90`
3. If any AC maps to a specific test, run that test independently to capture isolated output

**Zero-trust rules:**
- Always re-run tests from scratch (no cached results)
- Verify test count matches expected (no silently skipped tests)
- Check for suspicious results: 0 events detected, empty responses, tests passing with no assertions
- Rebuild Docker containers before E2E tests: `docker-compose up -d --build`

### 3. Code Quality Checks (9-Check Pipeline)

Run ALL checks sequentially. If a check fails, note it and continue to remaining checks. Report ALL failures together.

| # | Check | Command | Threshold | Failure Action |
|---|-------|---------|-----------|----------------|
| 1 | Full Test Suite | `poetry run pytest tests/ -v` | All pass | Report failures |
| 2 | Coverage | `poetry run pytest --cov=src --cov-report=term-missing --cov-fail-under=90` | >= 90% | Report uncovered lines |
| 3 | Type Checking | `poetry run mypy src/ --strict` | Zero errors | Report type errors |
| 4 | Linting | `poetry run ruff check src/ tests/` | Zero violations | Report lint issues |
| 5 | Formatting | `poetry run ruff format --check src/ tests/` | All formatted | Report unformatted files |
| 6 | Security | `poetry run bandit -r src/` | No high/critical | Report vulnerabilities |
| 7 | Docker Build | `docker-compose build` | Builds successfully | Report build errors |
| 8 | CHANGELOG | Verify entry exists for this story | Entry present | Report missing entry |
| 9 | Git Status | `git status` | Clean working tree | Report uncommitted changes |

**Notes:**
- Check 7 (Docker Build): Skip if no `docker-compose.yml` exists. Note in report.
- Check 8 (CHANGELOG): Search for story ID (e.g., "US-025") in CHANGELOG.md. Story IDs use 3-digit format (US-{NNN}).
- Run all checks even if earlier ones fail. The full picture helps targeted remediation.

### 4. Flexible UAT (User Acceptance Testing)

Detect the application's execution model and test accordingly.

**Detection Logic:**
1. Check for `docker-compose.yml` or `docker-compose.yaml` in project root
   - If found: UAT via Docker
2. Check for application entry point (`main.py`, FastAPI app, etc.)
   - If found: UAT via local process
3. If neither: Skip UAT, document in report as SKIPPED

**UAT via Docker:**
```bash
# 1. Build and start with latest code
docker-compose up -d --build

# 2. Wait for health check (30 second timeout)
for i in $(seq 1 30); do
  curl -sf http://localhost:{port}/health && break
  sleep 1
done

# 3. Run E2E scenarios from impl plan
# For each AC of type "Functional - End-to-End":
response=$(curl -s http://localhost:{port}/{endpoint})
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/{endpoint})

# 4. Assert expected outcomes
test "$status" = "200" || echo "FAIL: Expected 200, got $status"

# 5. Tear down
docker-compose down
```

**UAT via Local Process:**
```bash
# 1. Start application in background
poetry run python -m src.main &
APP_PID=$!

# 2. Wait for startup
sleep 3

# 3. Run test scenarios (same curl assertions as Docker UAT)

# 4. Stop application
kill $APP_PID
```

### 4b. Browser UAT (MANDATORY for web applications)

Browser UAT is **MANDATORY** for all web-facing plans. Use browser automation tools to navigate pages, interact with UI elements, verify visual output, and take screenshots.

**Tool priority (use first available):**
1. **Playwright MCP** (primary) — `mcp__playwright__*` tools: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_fill_form`, `browser_take_screenshot`, `browser_evaluate`, `browser_press_key`, `browser_wait_for`, `browser_console_messages`
2. **Claude in Chrome MCP** (fallback) — `mcp__claude-in-chrome__*` tools: `navigate`, `read_page`, `computer`, `find`, `form_input`, `javascript_tool`, `tabs_create_mcp`, `tabs_context_mcp`, `gif_creator`

**Tool discovery:** Use `ToolSearch` before starting UAT:
```
ToolSearch(query="mcp__playwright__browser_navigate")  # Check Playwright
ToolSearch(query="mcp__claude-in-chrome__navigate")     # Fallback check
```

**Screenshots:** Save all screenshots to `.qa/screenshots/` with naming:
```
{phase-no}-{page-name}-{iteration-no}-{desc}.png
```
Examples: `8.1-claims-1-draft-status.png`, `8.1-review-2-compliance-card.png`

**Browser UAT process:**
1. Launch/navigate to the application URL
2. For each UAT scenario:
   - Navigate to the relevant page
   - Perform user actions (click, type, upload, etc.)
   - Take screenshots for visual verification
   - Verify expected outcomes (element presence, text content, visual state)
   - Check console for errors
3. Record PASS/FAIL per scenario with screenshot evidence

### 5. Project Memory Integration

Read project memory BEFORE validation. Write findings AFTER validation.

**Before validation (READ):**
- `docs/project_notes/bugs.md` -- Check if known bugs are being reintroduced
- `docs/project_notes/decisions.md` -- Verify code follows established architectural decisions

**After validation (WRITE):**
- `docs/project_notes/bugs.md` -- Write bugs found (date, issue, root cause, solution, prevention)
- `docs/project_notes/issues.md` -- Log story completion (date, story ID, status, description)

**Integration during validation:**
- Cross-reference found issues against known bugs to detect regressions
- Verify architectural decisions are respected in the implementation
- Check if any previous bug fixes have been reverted

### 6. Granular Failure Mapping

When failures are found, map each failure back to specific implementation plan tasks. This enables targeted remediation instead of broad rework.

**Failure Mapping Process:**
1. For each test failure, identify the source file and function
2. Map the source file to the impl plan task that created/modified it
3. Map the test to the AC it validates (via Validates column)
4. Produce a remediation task list with specific fixes

**Mapping sources:**
- Test failure output -> source file:line -> impl plan `[X.0][CATEGORY]` task
- Coverage gap -> uncovered file:lines -> impl plan task that should have covered it
- UAT failure -> endpoint/route -> impl plan task that created the endpoint

**Failure Report Entry:**
```markdown
| Failure | Source | Impl Plan Task | Remediation |
|---------|--------|----------------|-------------|
| AC-2 test failure | src/orders/domain/order.py:23 | [5.0][FR-1] subtask [5.2] | Fix validation logic for empty cart |
| Coverage gap | src/orders/infrastructure/repo.py:45-62 | [7.0][FR-3] subtask [7.3] | Add tests for repository error paths |
| UAT: endpoint 500 | src/orders/api/routes.py:15 | [8.0][AC-2] subtask [8.1] | Fix endpoint handler exception |
```

### 7. QA Report Generation

Generate comprehensive QA reports. Two formats: PASS and FAIL.

**Report location:** `docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md`

**FAIL Report Format:**
```markdown
# QA Report: Story {N} - {Story Title}

## Summary
- **Overall Status**: FAIL
- **AC Results**: {X}/{Y} passed
- **Coverage**: {N}%
- **Quality Checks**: {X}/9 passed
- **UAT**: PASS / FAIL / SKIPPED

## AC Results
| AC ID | Description | Status | Evidence |
|-------|-------------|--------|----------|
| AC-1 | {desc} | PASS | test_file::test_func |
| AC-2 | {desc} | FAIL | test_file::test_func - AssertionError: ... |

## Quality Check Results
| Check | Status | Details |
|-------|--------|---------|
| Test Suite | PASS | 45/45 tests pass |
| Coverage | FAIL | 87% (target: 90%). Uncovered: src/orders/infrastructure/repo.py:45-62 |
| Type Check | PASS | 0 errors |
| Linting | PASS | 0 violations |
| Formatting | PASS | All formatted |
| Security | PASS | 0 issues |
| Docker Build | PASS | Build successful |
| CHANGELOG | PASS | Entry present |
| Git Status | PASS | Clean tree |

## UAT Results
| Scenario | Status | Details |
|----------|--------|---------|
| Health check | PASS | 200 OK |
| Create order | FAIL | Expected 201, got 500. Response: {"error": "..."} |

## Failure-to-Task Mapping
| Failure | Source | Impl Plan Task | Remediation |
|---------|--------|----------------|-------------|
| AC-2 test failure | src/orders/domain/order.py:23 | [5.0][FR-1] subtask [5.2] | Fix validation logic |
| Coverage gap | src/orders/infrastructure/repo.py:45-62 | [7.0][FR-3] subtask [7.3] | Add error path tests |

## Remediation Tasks (for Team Lead)
1. Fix validation logic in order domain - relates to [5.0][FR-1]
2. Add repository error path tests - relates to [7.0][FR-3]
```

**PASS Report Format:**
```markdown
# QA Report: Story {N} - {Story Title}

## Summary
- **Overall Status**: PASS
- **AC Results**: {Y}/{Y} passed (100%)
- **Coverage**: {N}% (>= 90%)
- **Quality Checks**: 9/9 passed
- **UAT**: PASS

## AC Results
| AC ID | Description | Status | Evidence |
|-------|-------------|--------|----------|
| AC-1 | {desc} | PASS | test_file::test_func |
| AC-2 | {desc} | PASS | test_file::test_func |

## Quality Check Results
All 9 checks passed.
| Check | Status |
|-------|--------|
| Test Suite | PASS ({N}/{N}) |
| Coverage | PASS ({N}%) |
| Type Check | PASS (0 errors) |
| Linting | PASS (0 violations) |
| Formatting | PASS |
| Security | PASS (0 issues) |
| Docker Build | PASS |
| CHANGELOG | PASS |
| Git Status | PASS |

## UAT Results
All scenarios passed.

## Recommendation
Story is ready for merge. All acceptance criteria validated, quality standards met.
```

</essential_principles>

<intake>

## What QA Needs to Begin

The QA agent requires the following context from the Team Lead:

1. **Story file path**: `docs/phases/epic-{NNN}-{desc}/stories/story-{NNN}-{desc}.md` (for AC parsing)
2. **Impl plan file path**: `docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md` (for failure mapping)
3. **Epic reference**: Which epic is being validated
4. **Validation scope**: Full validation or re-validation after remediation

**Before starting validation, QA MUST:**
- Read the user story to extract all ACs
- Read the impl plan to understand task structure (for failure mapping)
- Read project memory files (bugs.md, decisions.md)
- Identify the test structure in the codebase

</intake>

<routing>

| Validation Scope | Workflow |
|------------------|----------|
| Full story validation (first pass) | `workflows/validate-story.md` |
| UAT-only validation | `workflows/run-uat.md` |
| Re-validation after remediation | `workflows/remediation-check.md` |

</routing>

<workflow_steps>

## Full Validation Process

### Phase 1: Preparation

1. **Read user story** -- Extract AC table (ID, Given, When, Then, Type, Validates, Priority)
2. **Read impl plan** -- Map parent tasks to understand code structure
3. **Read project memory** -- Check bugs.md and decisions.md for context
4. **Scan codebase** -- Identify test files, source structure, docker-compose presence

### Phase 2: AC Validation

For each AC in priority order (P1 first):
1. Parse Given/When/Then columns
2. Search for corresponding test using Grep (search for AC ID, FR/TR IDs, or keyword matching)
3. Run the test independently: `poetry run pytest {test_path}::{test_func} -v`
4. Record result with evidence

### Phase 3: Quality Pipeline

Run all 9 checks sequentially. Record every result regardless of pass/fail.

### Phase 4: Code Quality Inspection

Verify architectural standards by reading source code:
- **CamelCase naming**: Grep for snake_case violations in src/ (function names, variables)
- **Domain purity**: Check domain/ directories for infrastructure imports (SQLAlchemy, Pydantic, httpx)
- **No hardcoded values**: Grep for common hardcoding patterns (string literals as config, magic numbers)
- **Vertical slice structure**: Verify feature directories contain domain/application/infrastructure/api

### Phase 5: UAT

If applicable (docker-compose exists or app entry point found):
1. Build/start application
2. Wait for health check
3. Run E2E scenarios from AC table (Type = "Functional - End-to-End")
4. Assert expected outcomes
5. Tear down

### Phase 6: Report Generation

1. Compile all results into QA report format (PASS or FAIL)
2. If failures exist, generate Failure-to-Task Mapping
3. Write report to `docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md`
4. Update project memory (bugs.md with new bugs, issues.md with story status)
5. Send results to Team Lead via SendMessage

</workflow_steps>

<reference_index>

## Domain Knowledge

All in `references/`:

**AC Parsing:**
- ac-parsing.md -- How to parse user story AC tables, column definitions, AC types, validation methods

**Quality Standards:**
- quality-checklist.md -- Full 9-check quality pipeline with commands, thresholds, and failure handling
- Code quality standards including SOLID, data policies, configuration management

**Cross-Agent Validation:**
- cross-agent-validation.md -- Validation rules adapted for QA agent: what to verify in developer output

**UAT Patterns:**
- uat-patterns.md -- Common UAT patterns: Docker-based, local process, health checks, HTTP assertions

</reference_index>

<workflows_index>

## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| validate-story.md | Full story validation: AC + quality + UAT + report |
| run-uat.md | UAT-only validation: Docker or local process testing |
| remediation-check.md | Re-validation after developer fixes: targeted scope |

</workflows_index>

<verification>

## Post-Validation Checklist

After every QA validation, verify:

- [ ] Every AC in the user story has been individually validated (PASS or FAIL with evidence)
- [ ] All 9 quality checks have been executed and results recorded
- [ ] Coverage is >= 90% (or failure documented with uncovered lines)
- [ ] CamelCase naming verified in source code (no snake_case in functions/variables)
- [ ] Domain layer has no infrastructure imports (no SQLAlchemy, Pydantic, httpx in domain/)
- [ ] No hardcoded values found (no magic numbers, string literals as config)
- [ ] UAT executed if docker-compose or app entry point exists (or SKIPPED documented)
- [ ] Failure-to-Task Mapping complete for every failure (mapped to impl plan task IDs)
- [ ] QA report written to `docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md`
- [ ] Project memory updated (bugs.md for new bugs, issues.md for story status)
- [ ] Results sent to Team Lead via SendMessage with clear PASS/FAIL status

</verification>
