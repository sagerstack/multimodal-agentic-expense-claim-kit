# Developer Log Format

Structured markdown log for tracking implementation progress. Adapted for the builder team's single Software Developer agent model.

---

## Overview

The developer log provides comprehensive traceability, metrics, and reporting for each user story implementation. The Software Developer agent writes all 6 sections (previously split between py-developer and dev-supervised in the old architecture).

**File Location:** `docs/phases/epic-{NNN}-{desc}/logs/story-{NNN}-{desc}-dev-log.md`

---

## Log Structure

The log consists of 6 sections in markdown format:

| Section | Content | When Written |
|---------|---------|--------------|
| 1. Header | Metadata (story ID, timestamps, status) | Start of implementation, updated at completion |
| 2. Implementation Tasks | Task-by-task log with files, approach, decisions | After each parent task |
| 3. Quality Checks Summary | Quality pipeline results | After quality checks run |
| 4. Implementation Summary | Holistic summary (tasks, files, coverage, requirements, DDD patterns) | At story completion |
| 5. Issues & Violations | Problems encountered, workflow violations | At story completion |
| 6. Recommendations | Next steps, improvements | At story completion |

---

## Section 1: Header

Metadata block at top of log file.

### Fields

| Field | Description | Example |
|-------|-------------|---------|
| **User Story** | Story ID and title | US-025 LunarCrush Authentication Setup |
| **Epic** | Epic reference | epic-001-{desc} |
| **Started** | Start timestamp (YYYY-MM-DD HH:MM:SS) | 2026-02-13 14:32:02 |
| **Completed** | End timestamp | 2026-02-13 15:39:02 |
| **Duration** | Elapsed time | 67 minutes |
| **Status** | Overall status | Complete / Partial / Failed |
| **Branch** | Feature branch name | feature/epic-001-story-001 |

### Template

```markdown
# Implementation Log: {Story ID} {Story Title}

**User Story**: {Story ID} {Story Title}
**Epic**: epic-{NNN}-{desc}
**Started**: {YYYY-MM-DD HH:MM:SS}
**Completed**: {YYYY-MM-DD HH:MM:SS}
**Duration**: {N} minutes
**Status**: {Complete / Partial / Failed}
**Branch**: feature/epic-{NNN}-story-{NNN}
```

---

## Section 2: Implementation Tasks

Task-by-task log tracking TDD implementation progress with file paths, approach, and key decisions.

### Columns

| Column | Description | Example |
|--------|-------------|---------|
| **Timestamp** | YYYY-MM-DD HH:MM:SS format | 2026-02-13 14:32:02 |
| **Phase** | Implementation phase/layer | Domain Layer, Application Layer, Infrastructure, Tests |
| **Task** | Task description (concise) | Implement RankedRoute value object |
| **Files** | Files created/modified | `src/domain/valueObjects/rankedRoute.py` |
| **Approach** | Technical approach (1 sentence) | Immutable dataclass with Decimal scores for precision |
| **Key Decisions** | Important choices made (1-2 items) | Used Decimal over float; validation in __post_init__ |
| **Tests** | Test file and coverage | `tests/unit/domain/testRankedRoute.py` (98%) |

### Template

```markdown
## Implementation Tasks

| Timestamp | Phase | Task | Files | Approach | Key Decisions | Tests |
|-----------|-------|------|-------|----------|---------------|-------|
| {timestamp} | {layer} | {task desc} | `{file paths}` | {approach} | {decisions} | `{test file}` ({coverage}%) |
```

---

## Section 3: Quality Checks Summary

Results of the quality check pipeline after implementation.

### Columns

| Column | Description | Values |
|--------|-------------|--------|
| **Check** | Check number and name | "1. Test Suite", "2. Coverage Report", etc. |
| **Status** | Check result | PASSED / SKIPPED / FAILED |
| **Details** | Summary of results | "41 tests, 0 failures, 95.92% coverage" |
| **Timestamp** | When check was executed | 2026-02-13 15:37:53 |

### Template

```markdown
## Quality Checks Summary

| Check | Status | Details | Timestamp |
|-------|--------|---------|-----------|
| 1. Test Suite | {status} | {N} tests, {N} failures | {timestamp} |
| 2. Coverage Report | {status} | {N}% {exceeds/below} 90% requirement | {timestamp} |
| 3. Type Checking | {status} | MyPy {N} errors, {N} source files | {timestamp} |
| 4. Linting | {status} | Ruff {N} violations | {timestamp} |
| 5. Security Scan | {status} | Bandit {N} high/medium issues | {timestamp} |
| 6. Docker Build | {status} | {result} | {timestamp} |
| 7. CHANGELOG | {status} | {result} | {timestamp} |
| 8. Git Commit | {status} | {result} | {timestamp} |
| 9. Task Completion | {status} | {result} | {timestamp} |

**Quality Gate Result**: {PASSED / INCOMPLETE / FAILED} - {summary}
```

---

## Section 4: Implementation Summary

Holistic summary with 5 required subsections.

### 4.1 Tasks Completed

```markdown
### 4.1 Tasks Completed: {X}/{Y} ({Z}%)

**Implemented Tasks**:
- [{X}.1] {task description}
- [{X}.2] {task description}
- ...

**Skipped Tasks**: {N} tasks ({N}% incomplete)
```

### 4.2 Files Modified

```markdown
### 4.2 Files Modified: {N} files

**Created** ({N} files):
- `{file path}` - {purpose}
- ...

**Modified** ({N} files):
- `{file path}` - {changes made}
- ...
```

### 4.3 Test Coverage

```markdown
### 4.3 Test Coverage: {N}%

**Coverage by Layer**:
- Domain: {N}% ({N} statements, {N} missing)
- Application: {N}% ({N} statements, {N} missing)
- Infrastructure: {N}% ({N} statements, {N} missing)
- Presentation: {N}% ({N} statements, {N} missing)

**Test Statistics**:
- Total: {N} tests
- Unit tests: {N} tests (mocked dependencies)
- Integration tests: {N} tests (component integration)
- E2E tests: {N} tests (docker-compose + curl)
- Live verification: {N} tests (real external APIs)
```

### 4.4 Requirements Coverage

```markdown
### 4.4 Requirements Coverage: {X}/{Y} ({Z}%)

- **Functional Requirements**: {X}/{Y} ({Z}%) implemented
- **Technical Requirements**: {X}/{Y} ({Z}%) implemented
- **Acceptance Criteria**: {X}/{Y} ({Z}%) validated
```

### 4.5 DDD Patterns Applied

```markdown
### 4.5 DDD Patterns Applied: {N} patterns

- **Value Objects**: {names} ({file paths})
- **Entities**: {names} ({file paths})
- **Aggregates**: {names} ({file paths})
- **Domain Events**: {names} ({file paths})
- **Repository Pattern**: {names} ({file paths})
- **Domain Services**: {names} ({file paths})
- **Specification Pattern**: {names} ({file paths})
- **Factory Pattern**: {names} ({file paths})
```

List only patterns that were actually applied. If none, state "No DDD patterns applied."

---

## Section 5: Issues & Violations

Problems encountered during implementation and validation.

### 5.1 Critical Issues

- Incomplete implementation (task gaps)
- Missing quality checks
- AC validation gaps
- Test coverage below threshold

### 5.2 Workflow Violations

- Missing TDD steps (code written without failing test first)
- Log format errors (timestamp issues)
- Uncommitted changes

### Template

```markdown
## Issues & Violations

### Critical Issues

{If none: "None - Implementation completed successfully."}

1. **{Issue Title}**: {description}
   - **Impact**: {what is affected}
   - **Resolution Required**: {what needs to happen}

### Workflow Violations

{If none: "None."}

- **{Violation}**: {description}
```

---

## Section 6: Recommendations

Next steps to complete or improve the implementation.

### Template

```markdown
## Recommendations

{If story fully complete: "User story fully implemented and ready for QA validation."}

1. **{Action}**: {description}
2. **{Action}**: {description}
```

---

## Timestamp Format

**CRITICAL**: Always use formatted date/time strings in `YYYY-MM-DD HH:MM:SS` format.

- Correct: `2026-02-13 14:32:02`
- Incorrect: `$(date +%Y-%m-%d %H:%M:%S)` (bash syntax -- Write tool does not execute bash)

Generate timestamps programmatically using Python's datetime formatting, never bash command substitution.

---

## Complete Example

```markdown
# Implementation Log: US-001 - Order Management Domain

**User Story**: US-001 - Order Management Domain
**Epic**: epic-001-order-management
**Started**: 2026-02-13 14:32:02
**Completed**: 2026-02-13 15:39:02
**Duration**: 67 minutes
**Status**: Complete
**Branch**: feature/epic-001-story-001

---

## Implementation Tasks

| Timestamp | Phase | Task | Files | Approach | Key Decisions | Tests |
|-----------|-------|------|-------|----------|---------------|-------|
| 2026-02-13 14:32:02 | Domain Layer | Implement OrderId value object | `src/orders/domain/orderId.py` | Frozen dataclass wrapping UUID | UUID for identity; validation in __post_init__ | `tests/unit/orders/testOrderId.py` (100%) |
| 2026-02-13 14:45:18 | Domain Layer | Implement Order entity | `src/orders/domain/order.py` | Rich entity with business logic | 10-item limit invariant; domain events for state changes | `tests/unit/orders/testOrder.py` (98%) |
| 2026-02-13 15:12:34 | Application Layer | Create PlaceOrder handler | `src/orders/application/placeOrder.py` | Command handler with DI | Repository injected via constructor; Result pattern for errors | `tests/integration/orders/testPlaceOrder.py` (96%) |

---

## Quality Checks Summary

| Check | Status | Details | Timestamp |
|-------|--------|---------|-----------|
| 1. Test Suite | PASSED | 45 tests, 0 failures | 2026-02-13 15:35:00 |
| 2. Coverage Report | PASSED | 96% exceeds 90% requirement | 2026-02-13 15:35:15 |
| 3. Type Checking | PASSED | MyPy 0 errors, 12 files | 2026-02-13 15:35:20 |
| 4. Linting | PASSED | Ruff 0 violations | 2026-02-13 15:35:25 |
| 5. Security Scan | PASSED | Bandit 0 issues | 2026-02-13 15:35:30 |
| 6. Docker Build | PASSED | Image built | 2026-02-13 15:36:00 |
| 7. CHANGELOG | PASSED | Entry added | 2026-02-13 15:36:05 |
| 8. Git Commit | PASSED | Committed to feature branch | 2026-02-13 15:36:10 |
| 9. Task Completion | PASSED | All tasks marked [x] | 2026-02-13 15:36:15 |

**Quality Gate Result**: PASSED - All checks completed successfully

---

## Implementation Summary

### 4.1 Tasks Completed: 15/15 (100%)

**Implemented Tasks**: All 15 tasks completed (see implementation plan)

**Skipped Tasks**: 0 tasks (0% incomplete)

### 4.2 Files Modified: 8 files

**Created** (6 files):
- `src/orders/domain/orderId.py` - OrderId value object
- `src/orders/domain/order.py` - Order aggregate root
- `src/orders/application/placeOrder.py` - Place order handler
- `tests/unit/orders/testOrderId.py` - OrderId tests
- `tests/unit/orders/testOrder.py` - Order tests
- `tests/integration/orders/testPlaceOrder.py` - Integration tests

**Modified** (2 files):
- `pyproject.toml` - Added dependencies
- `CHANGELOG.md` - Added entry for US-001

### 4.3 Test Coverage: 96%

**Coverage by Layer**:
- Domain: 100% (85 statements, 0 missing)
- Application: 96% (50 statements, 2 missing)

**Test Statistics**:
- Total: 45 tests (30 unit, 10 integration, 5 E2E)

### 4.4 Requirements Coverage: 12/12 (100%)

- Functional Requirements: 4/4 (100%) implemented
- Technical Requirements: 3/3 (100%) implemented
- Acceptance Criteria: 5/5 (100%) validated

### 4.5 DDD Patterns Applied: 4 patterns

- **Value Objects**: OrderId (`src/orders/domain/orderId.py`)
- **Entities**: Order (`src/orders/domain/order.py`)
- **Repository Pattern**: OrderRepository (`src/orders/domain/orderRepository.py`)
- **Domain Events**: OrderPlaced (`src/orders/domain/events.py`)

---

## Issues & Violations

None - Implementation completed successfully.

---

## Recommendations

User story fully implemented and ready for QA validation.

---

**Log Generated By**: Software Developer agent
**Log Format Version**: 3.0 (Builder Team)
```
