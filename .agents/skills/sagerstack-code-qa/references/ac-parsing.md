# Acceptance Criteria Parsing Reference

## Purpose

Defines how the QA agent parses and validates Acceptance Criteria from user story artifacts. The AC table is the primary input for all QA validation.

---

## AC Table Structure

User stories contain an AC table with these columns:

| Column | Description | QA Usage |
|--------|-------------|----------|
| Status | Checkbox `[ ]` or `[x]` | QA updates to `[x]` after validation |
| ID | AC identifier (AC-1, AC-2, ...) | Primary reference for reporting |
| Given | Initial context or state | Setup conditions for the test |
| When | Specific user action or trigger | Action to perform or test to run |
| Then | Expected system response or outcome | Assertion to verify |
| Type | Category of the AC | Determines validation method |
| Validates | FR/TR IDs this AC validates | Traceability link |
| Priority | P1 (highest) to P5 (lowest) | Validation order (P1 first) |

---

## AC Types and Validation Methods

### Functional Types

**Happy Path** (`Functional - Happy Path`)
- Validates the primary success flow
- Run the corresponding unit/integration test
- Verify the "Then" outcome matches test assertions
- Example Given/When/Then:
  - Given: "Valid order with 3 line items"
  - When: "User submits the order"
  - Then: "Order is created with status PENDING and total calculated correctly"

**Failure Scenario** (`Functional - Failure Scenario`)
- Validates graceful handling of known failure conditions
- Run test with failure inputs, verify error handling
- Example:
  - Given: "External payment service is unavailable"
  - When: "User attempts payment"
  - Then: "System returns friendly error message and queues retry"

**Edge Case** (`Functional - Edge Case`)
- Validates boundary conditions and unusual inputs
- Run test with edge inputs (empty, max, min, special characters)
- Example:
  - Given: "Order with maximum allowed 999 line items"
  - When: "User adds one more item"
  - Then: "System rejects with 'Maximum items exceeded' error"

**Error Handling** (`Functional - Error Handling`)
- Validates system response to invalid input or unexpected errors
- Run test with invalid input, verify appropriate error response
- Example:
  - Given: "Malformed JSON request body"
  - When: "Request sent to API endpoint"
  - Then: "System returns 400 with validation error details"

**Integration** (`Functional - Integration`)
- Validates interaction with external services or components
- Run integration test (with real or mocked services depending on .env availability)
- If `.env.local` exists with credentials: use real services
- If no credentials: use mocked services (but note in report)
- Example:
  - Given: "External service available with valid credentials in .env.local"
  - When: "System calls external API"
  - Then: "Integration succeeds and returns expected data structure"

**End-to-End** (`Functional - End-to-End`)
- Validates complete workflow through the deployed system
- Requires Docker or local process UAT
- Test via HTTP requests (curl or equivalent)
- Example:
  - Given: "Complete system deployed via docker-compose"
  - When: "User performs full create-read-update workflow"
  - Then: "All operations succeed with correct HTTP status codes and response bodies"

### Technical Types

**Performance** (`Technical - Performance`)
- Validates response time, throughput, or resource constraints
- Run performance-specific tests or measure execution time
- Compare against threshold in "Then" column
- Example:
  - Given: "Database with 10,000 records"
  - When: "User queries all active records"
  - Then: "Response returned within 200ms"

**Security** (`Technical - Security`)
- Validates security controls
- Run security scan (bandit) and verify no relevant vulnerabilities
- Check authentication/authorization if specified
- Example:
  - Given: "Unauthenticated request"
  - When: "Request sent to protected endpoint"
  - Then: "System returns 401 Unauthorized"

**Reliability** (`Technical - Reliability`)
- Validates fault tolerance, availability, recovery behavior
- Run reliability-specific tests (circuit breaker, retry, timeout)
- Example:
  - Given: "Database connection intermittently failing"
  - When: "System processes requests during instability"
  - Then: "Circuit breaker activates after 3 failures, returns cached data"

---

## Parsing Algorithm

### Step 1: Extract AC Table

Read the user story markdown. Locate the `## Acceptance Criteria` section. Parse the markdown table rows.

```
Pattern to locate: "## Acceptance Criteria" followed by a markdown table
Each row after the header represents one AC
```

### Step 2: Parse Each AC Row

For each row, extract:
- `acId`: The AC-N identifier
- `given`: The Given column text
- `when`: The When column text
- `then`: The Then column text (this is the primary assertion)
- `type`: The Type column (determines validation method)
- `validates`: The Validates column (FR/TR IDs for traceability)
- `priority`: The Priority column (P1-P5, determines validation order)

### Step 3: Locate Corresponding Tests

For each AC, find the test(s) that validate it:

1. **Search by AC ID**: `grep -r "AC-{N}" tests/` -- Tests may reference AC IDs in comments or names
2. **Search by FR/TR ID**: `grep -r "FR-{N}" tests/` -- Tests may reference requirement IDs
3. **Search by keyword**: Extract key terms from the "Then" column and search test names
4. **Search by file mapping**: Use impl plan to find which test files correspond to which tasks

If no test found for an AC: Report as FAIL with note "No corresponding test found"

### Step 4: Validate Each AC

Run the located test(s) and compare output against the "Then" assertion.

**Pass criteria:**
- Test exits with code 0
- Test assertions match the "Then" description
- No warnings or unexpected behavior

**Fail criteria:**
- Test exits with non-zero code
- Assertion error (actual != expected)
- Test not found
- Test skipped without valid reason

---

## Validates Column Cross-Reference

The "Validates" column links ACs to Functional Requirements (FR-N) and Technical Requirements (TR-N).

**Validation rules:**
- Every FR in the user story MUST be validated by at least one AC
- Every TR in the user story MUST be validated by at least one AC
- If QA finds an FR/TR without a corresponding AC: Flag as coverage gap in report

**How to verify coverage:**
1. Extract all FR IDs from the Functional Requirements table
2. Extract all TR IDs from the Technical Requirements table
3. For each FR/TR, check if at least one AC lists it in the Validates column
4. Report any gaps

---

## Priority-Based Validation Order

Validate ACs in priority order:
1. P1 (Highest) -- These are blocking. If P1 ACs fail, the story cannot pass.
2. P2 -- Important but not blocking on their own.
3. P3-P5 -- Lower priority, still must be validated.

All ACs must pass for the story to receive PASS status, regardless of priority. Priority determines validation order and reporting emphasis.

---

## Common Parsing Edge Cases

**Multiple FR/TR in Validates column:**
- `FR-1, TR-2` means this AC validates both requirements
- Report under both FR and TR coverage

**Range notation:**
- `FR-1-6` means this AC validates FR-1 through FR-6
- Expand the range when checking coverage

**Empty Validates column:**
- Flag as a story quality issue -- every AC should trace to at least one requirement
- Still validate the AC, but note the missing traceability

**Given clause references environment:**
- "Given .env.local credentials" -- Check if .env.local exists before running
- If .env.local missing: Skip test, report as SKIPPED (not FAIL)
- "Given Docker environment running" -- Ensure docker-compose is up
