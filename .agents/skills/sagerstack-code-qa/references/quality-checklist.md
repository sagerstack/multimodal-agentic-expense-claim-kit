# Quality Checklist Reference

## Purpose

Comprehensive quality check pipeline and code quality standards for QA validation. Combines the 9-check sequential pipeline with architectural and code quality verification.

---

## 9-Check Quality Pipeline

### Execution Rules

- Run ALL checks sequentially (1 through 9)
- If a check fails: Note the failure, continue remaining checks, report ALL failures
- Never skip a check unless explicitly not applicable (e.g., no Docker in project)
- Record exact command output for evidence

---

### Check 1: Full Test Suite

**Command:**
```bash
poetry run pytest tests/ -v
```

**Purpose:** Validate entire test suite passes without conflicts

**Success:** Exit code 0, all tests pass

**Failure indicators:**
- Non-zero exit code
- Failed assertions
- Collection errors (import failures)
- Test isolation issues (test passes alone but fails in suite)

**Evidence to capture:** Total test count, pass count, fail count, error details

---

### Check 2: Test Coverage

**Command:**
```bash
poetry run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=90
```

**Purpose:** Ensure minimum 90% code coverage

**Threshold:** >= 90% (aligned with sagerstack:software-engineering skill)

**Success:** Coverage meets or exceeds 90%

**Failure evidence to capture:**
- Current coverage percentage
- List of uncovered files with line numbers (from `term-missing` report)
- Map uncovered lines to impl plan tasks for remediation

**Notes:**
- Coverage exceptions (`# pragma: no cover`) are acceptable for truly untestable code
- Flag files below 80% coverage individually

---

### Check 3: Static Type Checking

**Command:**
```bash
poetry run mypy src/ --strict
```

**Purpose:** Verify all type hints are correct (strict mode)

**Success:** Zero type errors, all functions have type hints

**Failure evidence:**
- File, line, error description for each type error
- Total error count

---

### Check 4: Linting

**Command:**
```bash
poetry run ruff check src/ tests/
```

**Purpose:** Ensure code follows style guidelines

**Success:** Zero violations

**Failure evidence:**
- File, line, rule ID, description for each violation
- Total violation count

---

### Check 5: Formatting

**Command:**
```bash
poetry run ruff format --check src/ tests/
```

**Purpose:** Ensure consistent code formatting

**Success:** All files already formatted

**Failure evidence:**
- List of unformatted files

---

### Check 6: Security Scanning

**Command:**
```bash
poetry run bandit -r src/
```

**Purpose:** Detect security vulnerabilities

**Success:** No HIGH or CRITICAL severity issues

**Failure evidence:**
- Issue ID, severity, confidence, file, line, description
- Only HIGH and CRITICAL are blocking
- MEDIUM issues should be noted but are not blocking
- LOW issues are informational

---

### Check 7: Docker Build Verification

**Command:**
```bash
docker-compose build
```

**Purpose:** Ensure application builds successfully in Docker

**Success:** Build completes with exit code 0

**Skip condition:** No `docker-compose.yml` or `docker-compose.yaml` in project root

**If skipped:** Note in report as "SKIPPED (no docker-compose found)"

**Failure evidence:**
- Build error output
- Stage where build failed

---

### Check 8: CHANGELOG Verification

**Purpose:** Verify CHANGELOG.md entry exists for this story

**Verification steps:**
1. Check if `CHANGELOG.md` exists in project root
2. Search for the story ID (e.g., "US-025") in the file
3. Verify entry is under `## [Unreleased]` section
4. Verify entry describes the changes made

**Success:** Entry found with story reference

**Failure:** No entry found, or entry lacks story reference

---

### Check 9: Git Status

**Command:**
```bash
git status
```

**Purpose:** Verify clean working tree (all changes committed)

**Success:** No uncommitted changes, no untracked files (excluding expected gitignored files)

**Failure evidence:**
- List of uncommitted modified files
- List of untracked files

---

## Code Quality Standards Verification

Beyond the 9-check pipeline, QA must verify adherence to architectural standards.

### CamelCase Naming Verification

**What to check:**
- Function and method names use camelCase: `placeOrder`, `calculateTotal`
- Variable names use camelCase: `orderId`, `customerName`
- Class names use PascalCase: `OrderService`, `PlaceOrderHandler`
- Test function names use camelCase: `testPlaceOrderWithEmptyCart`

**How to detect violations:**
```bash
# Search for snake_case function definitions in src/
grep -rn "def [a-z]*_[a-z]" src/ --include="*.py" | grep -v "__" | grep -v "test_"
```

**Exceptions:**
- Python dunder methods (`__init__`, `__post_init__`, etc.) are allowed
- Third-party library overrides (e.g., Pydantic `model_config`) are allowed
- Environment variable names follow UPPER_SNAKE_CASE convention

---

### Domain Purity Verification

**Rule:** Domain layer has ZERO external dependencies

**What to check in `src/*/domain/` directories:**
- No imports from SQLAlchemy, Pydantic, FastAPI, httpx, boto3, or any framework
- No imports from infrastructure layer (`from src.*.infrastructure import ...`)
- Business logic lives in domain entities, value objects, and domain services

**How to detect violations:**
```bash
# Check for infrastructure imports in domain layer
grep -rn "import sqlalchemy\|import pydantic\|from fastapi\|import httpx\|import boto3" src/*/domain/ --include="*.py"

# Check for infrastructure layer imports in domain
grep -rn "from src.*infrastructure" src/*/domain/ --include="*.py"
```

---

### No Hardcoded Values Verification

**Rule:** All configuration comes from .env files or app_config.py, never hardcoded in source

**What to check:**
- No string literals used as API endpoints, URLs, or service addresses
- No magic numbers used as thresholds, limits, timeouts, or business rules
- No default parameter values that should be configurable

**Patterns to detect:**
```bash
# Search for common hardcoding patterns
grep -rn "http://\|https://" src/ --include="*.py" | grep -v "test\|mock\|example"
grep -rn "localhost:" src/ --include="*.py" | grep -v "test\|conftest"
```

**Exceptions:**
- Test files may contain hardcoded test data
- Domain constants that are truly invariant (e.g., `SECONDS_PER_DAY = 86400`)

---

### Vertical Slice Structure Verification

**Rule:** Code organized by feature/bounded context, not technical layer

**Expected structure per feature slice:**
```
src/{feature}/
    domain/        # Entities, Value Objects, Repository ABCs
    application/   # Commands, Queries, Handlers
    infrastructure/ # Repository impl, external API clients
    api/           # Routes, schemas
```

**What to check:**
- Each feature directory contains at minimum `domain/` and at least one other layer
- No flat technical layer organization (`src/models/`, `src/controllers/`, `src/services/`)
- Shared code is in `src/shared/` only

---

### SOLID Principles Spot Check

**Quick verification points:**
- **SRP:** Classes have focused responsibility (not mixing business logic with I/O)
- **OCP:** No long if/elif chains for behavior variation (use polymorphism)
- **DIP:** Application layer depends on interfaces (Protocol), not concrete implementations
- **ISP:** Repository interfaces are focused (not fat interfaces with unused methods)

---

### Data Quality Policies

Verify these policies are respected in the implementation:

**NO_MOCK_DATA_POLICY:**
- Production code paths must not contain placeholder/mock data
- Search for: `return Decimal("100.0")`, `return "placeholder"`, `return {}` in non-test code

**NO_HARDCODING_POLICY:**
- No hardcoded token pairs, quote tokens, or market structure assumptions
- Dynamic discovery from APIs, not static mappings

**NO_ARTIFICIAL_LIMITS_POLICY:**
- Any numeric limit must have a comment justifying the constraint
- Business rule filters applied BEFORE technical limits (filter -> sort -> limit order)

**COMPLETE_API_DATA_POLICY:**
- API response fields documented in tech research must be extracted, not silently discarded
- If a field is intentionally omitted, justification must exist in the impl plan

**FILTER_BEFORE_LIMIT_POLICY:**
- Business criteria filters applied BEFORE technical limits
- Never limit -> filter (wrong order)

---

## Quality Check Result Summary Format

### All Checks Pass

```
Quality Check Summary
---------------------
Check 1: Test Suite     PASS (45 tests, 0 failures)
Check 2: Coverage       PASS (95%, exceeds 90% target)
Check 3: Type Checking  PASS (0 errors)
Check 4: Linting        PASS (0 violations)
Check 5: Formatting     PASS (all formatted)
Check 6: Security       PASS (0 high/critical issues)
Check 7: Docker Build   PASS (build successful)
Check 8: CHANGELOG      PASS (entry present)
Check 9: Git Status     PASS (clean tree)

Result: 9/9 checks passed
```

### Some Checks Fail

```
Quality Check Summary
---------------------
Check 1: Test Suite     PASS (45 tests, 0 failures)
Check 2: Coverage       FAIL (87%, target 90%)
Check 3: Type Checking  PASS (0 errors)
Check 4: Linting        PASS (0 violations)
Check 5: Formatting     PASS (all formatted)
Check 6: Security       PASS (0 high/critical issues)
Check 7: Docker Build   SKIPPED (no docker-compose)
Check 8: CHANGELOG      PASS (entry present)
Check 9: Git Status     FAIL (2 uncommitted files)

Result: 7/9 checks passed, 1 failed, 1 skipped
```
