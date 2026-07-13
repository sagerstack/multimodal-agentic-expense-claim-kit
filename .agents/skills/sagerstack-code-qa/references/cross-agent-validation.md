# Cross-Agent Validation Reference (QA Perspective)

## Purpose

Validation rules that the QA agent applies when checking developer output. These rules catch common issues that arise from miscommunication between the Solution Architect (who wrote the impl plan) and the Developer (who implemented it).

---

## Developer Output Validation

### Pre-Validation Environment Checks

Before running any tests, QA must verify the environment:

- [ ] **Docker running**: If E2E or Docker tests exist, verify Docker daemon is active
- [ ] **.env.local exists**: If integration/live tests reference .env.local credentials
- [ ] **.env.test exists**: Verify `tests/.env.test` exists for test configuration
- [ ] **Dependencies installed**: `poetry install` has been run

---

### Test Execution Validation

#### Suspicious Results Detection

Flag these results as requiring investigation -- they likely indicate bugs, not passing behavior:

| Red Flag | Likely Issue |
|----------|-------------|
| "0 events detected" for live data streams | Connection issue, not a valid pass |
| "No transactions in N blocks" on mainnet | Network query failing silently |
| Test passes with empty result set | Missing assertions or broken data path |
| Test skipped when .env.local exists | Configuration error, not legitimate skip |
| All tests pass in < 1 second for integration suite | Tests are mocked when they should not be |
| 100% coverage but no assertions | Tests run code but never assert outcomes |

#### E2E Test Prerequisites

Before running E2E tests that use HTTP endpoints:

- [ ] **Presentation layer exists**: API routes/endpoints are implemented (not just domain logic)
- [ ] **Docker containers rebuilt**: `docker-compose up -d --build` to ensure latest code
- [ ] **Wait for readiness**: Health check passes before running tests
- [ ] **Correct ports**: Verify port numbers match docker-compose configuration

**If E2E test requires endpoints that do not exist:**
- Report as FAIL with note: "Presentation layer missing. E2E tests require API endpoints."
- Map to impl plan -- presentation layer should have been a task

#### Docker Redeployment Rule

- ALWAYS rebuild Docker containers before E2E and live tests
- Use: `docker-compose up -d --build`
- Wait for services to be ready (health check or sleep)
- Running tests against stale containers produces false results

#### Live Test Validation

When `.env.local` exists with credentials:

- [ ] Live tests MUST execute (not be skipped)
- [ ] Live tests MUST connect to real service endpoints
- [ ] Live tests MUST validate non-zero results for liquid instruments
- [ ] Live tests MUST specify monitoring duration and expected event count

---

### AC-to-Test Coverage Validation

#### Every AC Must Have 4 Test Levels

For each AC in the user story, verify the impl plan specified (and developer implemented) these test levels:

| Test Level | Impl Plan Task | What QA Verifies |
|------------|----------------|-------------------|
| Unit tests | `[{X}.4]` subtask | Tests exist in `tests/unit/`, mock external dependencies |
| Integration tests | `[{X}.5]` subtask | Tests exist in `tests/integration/`, use real or test-double dependencies |
| E2E tests | `[{X}.6]` subtask | Tests exist in `tests/e2e/`, use docker-compose + curl |
| Live verification | `[{X}.7]` subtask | Tests verify behavior with real production-like services |

**If any test level is missing:** Report as a gap with reference to the impl plan task that should have included it.

#### Config Value Validation

If the user story defines configuration values (e.g., `TOKEN_VOLUME_THRESHOLD_USD=50000`):

- [ ] At least one AC validates that the config value is actually used in logic
- [ ] At least one test asserts behavior changes when config value changes
- [ ] Config value is loaded from environment (not hardcoded in source)

**Detection:**
```bash
# Verify config value is referenced in source code
grep -rn "TOKEN_VOLUME_THRESHOLD_USD" src/ --include="*.py"

# Verify config value is tested
grep -rn "TOKEN_VOLUME_THRESHOLD_USD" tests/ --include="*.py"
```

#### Business Logic Validation

ACs must test OUTCOMES, not just PROCESS:

| GOOD AC Validation | BAD AC Validation |
|-------------------|-------------------|
| "Cache contains 100-500 tokens AND all have volume >= $50K" | "Cache seeding completes successfully" |
| "Response time < 200ms for 10K records" | "Performance test runs" |
| "Error message includes order ID and reason" | "Error handling works" |

**QA must verify:** Test assertions check concrete outcomes (counts, values, states), not just that code executed.

---

### FR Intent Preservation Validation

QA should verify that the developer's implementation preserves the intent of each Functional Requirement.

#### Action Verb Preservation

Check that the implementation method matches what the FR specified:

| FR Verb | Expected Implementation | Violation |
|---------|------------------------|-----------|
| "query", "fetch", "retrieve" | Proactive API calls (HTTP GET/POST) | Event listening instead of querying |
| "subscribe", "listen", "monitor" | Reactive event handlers | API polling instead of subscriptions |
| "pre-populate", "seed", "initialize" | Upfront data loading BEFORE workflow | Lazy loading during workflow |
| "transform", "normalize", "validate" | Data processing pipeline | Data passed through without processing |

**How to verify:** Read the FR description, then inspect the corresponding source code to confirm the implementation approach matches.

#### Temporal Sequence Preservation

If FR specifies ordering ("before X", "after Y completes"):

- [ ] Verify task dependencies enforce the order in code
- [ ] Verify initialization sequence respects temporal constraints
- [ ] "Pre-populate BEFORE WebSocket activates" means population code runs BEFORE subscription setup

#### Data Source Preservation

If FR specifies data sources ("query Solana API", "from blockchain sources"):

- [ ] Verify implementation calls the specified sources
- [ ] Verify all specified sources are covered (not just one of three)
- [ ] Changing data source without justification is a FAIL

---

### Service Integration Validation

When the impl plan creates a new service, QA must verify complete integration:

1. [ ] Service class file exists in source
2. [ ] Service is imported somewhere in `src/` (not just in tests)
3. [ ] Service is instantiated with proper dependency injection
4. [ ] Service methods are called from application code
5. [ ] Unit tests exist with mocked dependencies
6. [ ] Integration tests exist with real/test-double dependencies

**Detection of orphaned services:**
```bash
# Find service class definition
grep -rn "class {ServiceName}" src/ --include="*.py"

# Verify it is imported in production code (not just tests)
grep -rn "import.*{ServiceName}\|from.*import.*{ServiceName}" src/ --include="*.py" | grep -v "tests/"

# Verify it is instantiated
grep -rn "{ServiceName}(" src/ --include="*.py" | grep -v "tests/" | grep -v "class "
```

If service is defined but never imported/instantiated in production code: Report as FAIL with remediation to add integration wiring.

---

### Task Completion Validation

Verify the impl plan's checkbox status matches reality:

1. Read the impl plan file
2. For each task marked `[x]`:
   - Verify the corresponding code/test actually exists
   - Verify the test passes
3. For each task marked `[ ]` (not completed):
   - Verify it is either a MANUAL task or was intentionally deferred
   - If it should have been completed: Report as incomplete

---

## Common Anti-Patterns to Flag

### Developer Anti-Patterns

| Anti-Pattern | How QA Detects It | Report As |
|-------------|-------------------|-----------|
| Skipping E2E tests because "no presentation layer" | Grep for missing API routes when AC requires E2E | FAIL: Presentation layer missing |
| Skipping live tests when .env.local exists | Check .env.local presence, verify live tests ran | FAIL: Live tests not executed |
| Accepting 0 results from liquid instruments | Check test output for zero-count results | FAIL: Suspicious zero results |
| Running E2E without rebuilding containers | Check if docker-compose build was run before tests | FAIL: Stale container test |
| Mock data in integration test paths | Grep for mock.patch in integration tests when .env.local exists | FAIL: Mock in integration test |
| Service created but never wired | Grep for class definition vs import/instantiation | FAIL: Orphaned service |
| Config defined but never used in logic | Grep for config value in source vs just in .env | FAIL: Unused config |

### Solution Architect Anti-Patterns (detectable in implementation)

| Anti-Pattern | How QA Detects It |
|-------------|-------------------|
| E2E test tasks before presentation layer tasks | Check if routes exist when E2E tests reference endpoints |
| Missing service integration tasks | Service class exists but no wiring code |
| AC approach substitution without justification | FR says "query API" but code uses event listening |
| Orphaned field defers | Tech research says parse field X, no code parses it |
