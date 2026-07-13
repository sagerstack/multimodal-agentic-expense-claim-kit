# Implementation Plan Patterns

Reference for the Solution Architect when generating implementation plans from user stories. Extracted and adapted from the implementation-plan artifact template.

---

## Purpose

Task-based execution guide that provides requirement-driven task organization with complete test coverage and direct traceability from requirements to implementation to validation.

**Key Principle**: Implementation plan describes WHAT/HOW capabilities to build. Tech research describes WHAT/WHY external data is structured.

---

## Core Sections

1. **Metadata** - ID (`US-{NM}-{N}-IMPL-PLAN`), title, user story ID, tech research ID, timestamps, complexity, dependencies
2. **Quick Reference** - Tech stack, architectural pattern, link to tech research
3. **Requirements Coverage Validation** (MANDATORY) - 100% FR/TR/AC mapping with test coverage tracking
4. **Task-Based Implementation Plan** - Requirement-driven organization with hierarchical parent/sub-task structure
5. **Changelog** - Timestamp, author, changes, affected sections, reason

---

## Abstraction Guidelines

- Describe **capabilities** (WHAT), not file paths (WHERE)
- Specify **requirements/behavior**, not structure
- Use placeholders: [entity names], [feature capabilities], [business logic requirements]
- Trust developer to apply Clean Architecture standards
- Never prescribe specific file names or directory structures

**Good**: "Implement order validation logic that enforces minimum quantity and valid product references"
**Bad**: "Create file src/orders/domain/validators.py with class OrderValidator"

---

## Task Type Markers

### Parent Task Categories

| Marker | Category | Purpose |
|--------|----------|---------|
| `[{X}.0][MANUAL]` | Manual Prerequisites | Human-required actions (subscriptions, external UI) |
| `[{X}.0][SETUP]` | Environment & Setup | Docker, dependencies, base classes, config |
| `[{X}.0][FR-N]` | Functional Requirement | One parent task per FR from user story |
| `[{X}.0][TR-N]` | Technical Requirement | One parent task per TR from user story |
| `[{X}.0][AC-N]` | Acceptance Criterion | One parent task per AC, MUST include 4 test levels |
| `[{X}.0][DOC]` | Documentation | Final deliverables, version control |

### Subtask Numbering

- Format: `[{X}.1]`, `[{X}.2]`, ... `[{X}.N]`
- Default: automated (no marker needed)
- Manual: `[{X}.Y][MANUAL]` when human action required

### Rules
- Parent tasks NEVER have `[MANUAL]` or automation markers (only category prefix)
- Subtasks marked `[MANUAL]` only when human action required
- Developer STOPS at `[MANUAL]` tasks, executes all unmarked tasks automatically
- No `[AUTO]` marker (automation is default)

---

## Task Execution Order

1. **Manual Prerequisites** (`[MANUAL]`) - External account setup, subscriptions, payments
2. **Environment & Setup** (`[SETUP]`) - Docker, dependencies, base exception hierarchy, config
3. **Functional Requirements** (`[FR-N]`) - One parent per FR, in FR numbering order
4. **Technical Requirements** (`[TR-N]`) - One parent per TR
5. **Acceptance Criteria** (`[AC-N]`) - One parent per AC with 4 test levels
6. **Documentation** (`[DOC]`) - Developer docs, CI/CD, quality checks

---

## Parent Task Number Allocation

```
Manual Prerequisites: [1.0], [2.0], ...
Environment & Setup:  [3.0], [4.0], ...
FR tasks:            [5.0][FR-1], [6.0][FR-2], ...
TR tasks:            [{X}.0][TR-1], [{X}.0][TR-2], ...
AC tasks:            [{X}.0][AC-1], [{X}.0][AC-2], ...
Documentation:       [{X}.0][DOC]
```

Numbers are sequential across all categories. No gaps.

---

## FR/TR Task Structure

```markdown
- [ ] **[{X}.0][FR-N] {Requirement Description}**
  - [ ] [{X}.1] Implement {capability 1}
  - [ ] [{X}.2] Implement {capability 2}
  - [ ] [{X}.3] Implement {capability 3}
  - [ ] [{X}.N-1] Write unit tests: {test scenarios}
  - [ ] [{X}.N] Live environment test: {deployment -> verification steps}
```

Each FR/TR parent task should:
- Reference the exact requirement from the user story
- Break into 3-8 subtasks
- Include unit test subtask
- Include live environment verification

---

## AC Task Structure (4 Mandatory Test Levels)

Every AC parent task MUST include these 4 test levels:

```markdown
- [ ] **[{X}.0][AC-N] {Acceptance Criterion Description}**
  - [ ] [{X}.1] Implementation subtask 1
  - [ ] [{X}.2] Implementation subtask 2
  - [ ] [{X}.3] Implementation subtask 3
  - [ ] [{X}.4] Write unit tests (mocked dependencies)
  - [ ] [{X}.5] Write integration tests (component integration with test doubles)
  - [ ] [{X}.6] **E2E Test**:
    ```bash
    docker-compose build
    docker-compose up -d
    response=$(curl -s http://localhost:{port}/{endpoint})
    status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}/{endpoint})
    test "$status" = "200" || exit 1
    echo "AC-N E2E test passed"
    docker-compose down
    ```
  - [ ] [{X}.7] **Live Environment Verification**:
    - Deploy to test environment
    - Verify with real external APIs (not mocks)
    - Validate production-like behavior
    - Document evidence of successful validation
```

### Test Level Definitions

| Level | Subtask | Purpose | Characteristics |
|-------|---------|---------|-----------------|
| Unit | `[{X}.4]` | Isolated logic testing | Mocked dependencies, fast, test single functions |
| Integration | `[{X}.5]` | Component integration | Test doubles/stubs, request/response flows through layers |
| E2E | `[{X}.6]` | Full deployed workflow | Docker environment, bash scripts, curl assertions |
| Live | `[{X}.7]` | Real environment verification | Real APIs (no mocks), production-like behavior, evidence |

---

## Requirements Coverage Validation (MANDATORY)

This section MUST appear after Quick Reference, before the Task-Based Plan.

### Format

```markdown
## Requirements Coverage Validation

### Functional Requirements
| Requirement ID | Description | Parent Task | Status |
|----------------|-------------|-------------|--------|
| FR-1 | {Description} | [{X}.0][FR-1] ({N} subtasks) | [ ] |
| FR-2 | {Description} | [{X}.0][FR-2] ({N} subtasks) | [ ] |

### Technical Requirements
| Requirement ID | Description | Parent Task | Status |
|----------------|-------------|-------------|--------|
| TR-1 | {Description} | [{X}.0][TR-1] ({N} subtasks) | [ ] |

### Acceptance Criteria
| Criteria ID | Description | Parent Task | Unit Tests | Integration Tests | E2E Test | Live Verification |
|-------------|-------------|-------------|------------|-------------------|----------|-------------------|
| AC-1 | {Description} | [{X}.0][AC-1] | [{X}.4] | [{X}.5] | [{X}.6] | [{X}.7] |

**Coverage Summary**:
- Functional Requirements: X/X mapped (100%)
- Technical Requirements: Y/Y mapped (100%)
- Acceptance Criteria: Z/Z mapped with complete test coverage (100%)
```

### Validation Rules (BLOCKING)
1. Every FR must have a dedicated parent task
2. Every TR must have a dedicated parent task
3. Every AC must have a dedicated parent task with 4 test levels
4. Coverage must be 100%. Any gap makes the plan INVALID.

---

## API Field Extraction Task Requirements (CRITICAL)

### When to Apply
If tech research document includes "API Research" section with field extraction mappings.

### Mandatory Task Pattern

For each API endpoint referenced in tech research:

```markdown
- [ ] **[{X}.0][FR-Y] {API Name} Data Extraction**
  - [ ] [{X}.1] Query {API Name} endpoint: {METHOD} {URL}
    - Request payload: {exact payload from tech research}
    - Authentication: {auth method from tech research}
  - [ ] [{X}.2] Parse response and extract fields per tech research mapping:
    - Extract `{api_field_path}` -> store as `{domain_field_name}` ({data type})
    - Extract `{api_field_path}` -> store as `{domain_field_name}` ({data type})
    - (List ALL fields from tech research "Field Extraction Mapping")
  - [ ] [{X}.3] Validate extracted data matches expected structure:
    - Assert `{domain_field_name}` is not None
    - Assert `{domain_field_name}` type is {expected_type}
    - Log extraction: logger.debug("Extracted fields", {field_name}={value})
  - [ ] [{X}.4] Handle missing/malformed fields:
    - If `{critical_field}` missing -> log warning, skip record
    - If `{optional_field}` missing -> use default value
  - [ ] [{X}.5] Integration test: Verify extraction with real API call
```

### Anti-Pattern (FORBIDDEN)

```markdown
WRONG: Vague task without field-specific extraction
- [ ] [14.1] Query API for data
- [ ] [14.2] Extract data

CORRECT: Field-specific extraction per tech research
- [ ] [14.1] Query endpoint: POST https://api.example.com/info
  - Request payload: {"type": "metaAndAssetCtxs"}
- [ ] [14.2] Parse response and extract fields per tech research section 2.3:
  - Extract `data[0].universe[i].name` -> store as `base_token` (str)
  - Extract `data[1][i].midPx` -> store as `direct_price` (Decimal)
```

### Enforcement (BLOCKING FAILURE)
- If tech research has "API Research" section BUT impl plan has vague tasks -> **BLOCKING FAILURE**
- If tasks don't reference exact field paths from tech research -> **BLOCKING FAILURE**
- If no validation subtask exists for extracted fields -> **BLOCKING FAILURE**

---

## Subtask Sizing

Target: 15-30 minutes per subtask for an AI developer agent.

**Too large** (split): "Implement the entire API client with all endpoints"
**Too small** (merge): "Import the requests library"
**Right size**: "Implement authentication header injection with Bearer token format"

---

## Cost Documentation

When the plan involves non-zero costs, document in metadata:

```markdown
## Cost Summary
| Item | Monthly Cost | Approved | Alternative |
|------|-------------|----------|-------------|
| {Service} | ${amount} | {Yes/No} | {Alternative} |
```

All costs MUST have been approved by the user during Q&A Point 3.
