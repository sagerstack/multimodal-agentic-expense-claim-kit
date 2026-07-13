# Escalation Protocol

When and how to escalate issues to the user during builder team execution.

---

## Escalation Categories

### 1. QA Failure After Maximum Retries

**Trigger**: Code QA reports FAIL for a story after 2 remediation cycles.

**What to Include**:
```
ESCALATION: US-{NNN} in epic-{NNN}-{desc} - QA Failure After 2 Retries

WHAT FAILED:
- {Concise description of remaining failures}
- AC results: {X}/{Y} passed
- Quality checks: {X}/9 passed

WHAT WAS ATTEMPTED:
- Retry 1: {specific fixes attempted and outcomes}
- Retry 2: {specific fixes attempted and outcomes}

REMAINING ISSUES:
- {Issue 1}: {file}:{line} - {description}
- {Issue 2}: {file}:{line} - {description}

RECOMMENDATION:
- {Specific manual intervention suggested}
- {Alternative approach if applicable}

ARTIFACTS:
- QA Report: docs/phases/epic-{NNN}-{desc}/qa/story-{NNN}-{desc}-qa-report.md
- Impl Plan: docs/phases/epic-{NNN}-{desc}/plans/story-{NNN}-{desc}-plan.md
- Developer Log: docs/phases/epic-{NNN}-{desc}/logs/story-{NNN}-{desc}-dev-log.md
```

**User Options**:
1. Provide guidance on how to fix the remaining issues
2. Skip the failing story and continue to the next
3. Abort the phase build

---

### 2. Infrastructure Failure

**Trigger**: Docker build fails, LocalStack unavailable, Poetry install fails, or similar environment issues that prevent implementation.

**What to Include**:
```
ESCALATION: Infrastructure Failure in phase {N.M}

WHAT FAILED:
- {Specific infrastructure component}
- Error output: {relevant error message}

WHAT WAS ATTEMPTED:
- {Troubleshooting steps taken}

IMPACT:
- {Which tasks/stories are blocked}
- {What can still proceed without this infrastructure}

RECOMMENDATION:
- {Specific fix the user should try}
- {Alternative approach if infrastructure cannot be fixed}
```

**User Options**:
1. Fix the infrastructure and confirm when ready
2. Skip infrastructure-dependent tasks (document as known risk)
3. Abort the phase build

---

### 3. MANUAL Task Requiring User Action

**Trigger**: Implementation plan contains `[MANUAL]` tasks that require human action (API key creation, account setup, service configuration, etc.).

**What to Include**:
```
MANUAL ACTION REQUIRED: phase {N.M}, Story {N}

TASK: [X.0][MANUAL] {task description}

WHAT TO DO:
1. {Step-by-step instructions for the manual action}
2. {Step 2}
3. {Step N}

WHY AUTOMATED EXECUTION IS NOT POSSIBLE:
- {Reason: requires login, payment, human verification, etc.}

BLOCKED TASKS:
- {List of tasks waiting on this manual action}

When complete, please confirm so implementation can continue.
```

**User Options**:
1. Complete the action and confirm
2. Skip this task (downstream tasks may fail)
3. Provide alternative approach

---

### 4. Agent Crash or Unresponsive Agent

**Trigger**: A teammate (Developer or QA) stops responding after 2 re-send attempts.

**What to Include**:
```
ESCALATION: Agent Unresponsive in phase {N.M}

AGENT: {software-developer / code-qa}

LAST KNOWN STATE:
- Task in progress: {task description}
- Last message received: {timestamp and content summary}
- Re-send attempts: 2 (both failed to elicit response)

PROGRESS PRESERVED:
- TaskList tasks completed: {list}
- Impl plan tasks marked [x]: {count}
- Git commits made: {count}

RECOMMENDATION:
- Re-invoke /sagerstack:builder for phase {N.M}
- Builder will resume from first incomplete task
- No work will be lost (progress is on disk)
```

**User Options**:
1. Re-invoke the builder skill (auto-resumes from incomplete work)
2. Investigate the issue manually
3. Abort the phase build

---

### 5. External API Unavailable

**Trigger**: Integration tests or live verification tasks fail because an external API is down or unreachable.

**What to Include**:
```
ESCALATION: External API Unavailable in phase {N.M}

SERVICE: {API/service name}
ENDPOINT: {URL that failed}
ERROR: {connection error, timeout, HTTP status}

IMPACT:
- Affected tasks: {list of tasks requiring this API}
- Affected ACs: {list of acceptance criteria that cannot be validated}

WHAT WAS COMPLETED:
- Unit tests: PASS (mocked dependencies)
- Integration tests with mocks: PASS
- Live verification: SKIPPED (API unavailable)

RECOMMENDATION:
- Continue with unit + integration test coverage
- Document skipped live verifications as known risk
- Re-run live verification when API is available
```

**User Options**:
1. Skip live verification, accept documented risk
2. Wait for API to become available, then re-run QA
3. Provide alternative API endpoint or credentials

---

### 6. Coverage Below Threshold After Remediation

**Trigger**: Test coverage remains below 90% after 2 remediation attempts.

**What to Include**:
```
ESCALATION: Coverage Gap in phase {N.M}, Story {N}

CURRENT COVERAGE: {N}% (threshold: 90%)

UNCOVERED CODE:
- {file}:{lines} - {description of uncovered code}
- {file}:{lines} - {description of uncovered code}

WHAT WAS ATTEMPTED:
- Retry 1: Added {N} tests for {area}. Coverage improved from {X}% to {Y}%.
- Retry 2: Added {N} tests for {area}. Coverage at {Z}%.

CHALLENGE:
- {Why remaining code is hard to cover: unreachable paths, external dependencies, etc.}

RECOMMENDATION:
- {Accept current coverage with documented gaps}
- {OR add specific test type to cover remaining code}
```

**User Options**:
1. Accept current coverage with documented gaps
2. Provide guidance on how to test the uncovered code
3. Lower threshold for this story (temporary exception)

---

### 7. Task Dependency Deadlock

**Trigger**: Blocked tasks cannot unblock because of circular or unresolvable dependencies.

**What to Include**:
```
ESCALATION: Dependency Deadlock in phase {N.M}

BLOCKED TASKS:
- Task {A} blocked by Task {B}
- Task {B} blocked by Task {C}
- Task {C} blocked by Task {A} (circular)

ANALYSIS:
- {How the deadlock was created}
- {Which tasks are actually independent}

RECOMMENDATION:
- {Suggested dependency reordering}
- {Which task should be unblocked first}
```

**User Options**:
1. Approve the suggested reordering
2. Specify a different resolution
3. Remove specific dependencies

---

## Escalation Severity Levels

| Severity | Response Time | User Action Required |
|----------|--------------|---------------------|
| **Blocking** | Immediate (cannot continue) | MANUAL tasks, infrastructure failures, agent crashes |
| **Degraded** | After retries exhausted | QA failures, coverage gaps |
| **Informational** | At story/phase completion | External API unavailable (documented risk) |

## Escalation Rules

1. **Always exhaust automated remediation first** -- never escalate on first failure
2. **Maximum 2 retries** before escalation for QA failures and coverage gaps
3. **Immediate escalation** for MANUAL tasks and infrastructure blockers
4. **Include all artifacts** -- QA reports, dev logs, impl plans
5. **Provide clear options** -- user should know exactly what actions they can take
6. **Preserve progress** -- escalation never causes work loss
