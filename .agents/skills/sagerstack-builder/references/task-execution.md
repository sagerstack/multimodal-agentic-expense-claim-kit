# Task Execution Patterns

Adapted from the process implementation plan management guidelines for the builder team's task execution model.

---

## Task Structure in Implementation Plans

Implementation plans use a hierarchical checkbox structure:

```markdown
- [ ] **[X.0][CATEGORY] Parent Task Description**
  - [ ] [X.1] Subtask 1
  - [ ] [X.2] Subtask 2
  - [ ] [X.N] Final subtask
```

### Category Types

| Category | Prefix | Description | Execution Order |
|----------|--------|-------------|-----------------|
| Manual Prerequisites | `[MANUAL]` | Requires user action (API key setup, account creation) | First (blocks all others) |
| Environment & Setup | `[SETUP]` | Project scaffolding, dependencies, config files | Second |
| Functional Requirements | `[FR-N]` | Implements a specific functional requirement from the user story | Third (in order) |
| Technical Requirements | `[TR-N]` | Implements a specific technical requirement | Fourth (in order) |
| Acceptance Criteria | `[AC-N]` | Validates acceptance criteria with 4 test levels | Fifth (in order) |
| Documentation | `[DOC]` | CHANGELOG, developer log, documentation updates | Last |

### AC Tasks Include 4 Test Levels

Every `[AC-N]` parent task MUST include subtasks for:

1. `[X.4]` Unit tests (mocked dependencies)
2. `[X.5]` Integration tests (component integration)
3. `[X.6]` E2E test (docker-compose + curl)
4. `[X.7]` Live environment verification

---

## Completion Protocol

### Subtask Completion

When a subtask is finished:
1. Mark it as completed: change `[ ]` to `[x]` in the impl plan file
2. Move to the next subtask within the same parent task

### Parent Task Completion

When ALL subtasks under a parent task are `[x]`:
1. Mark the parent task as `[x]`
2. Run the quality check pipeline (5 checks):
   - `poetry run pytest tests/ -v` (all tests pass)
   - `poetry run pytest --cov=src --cov-fail-under=90` (coverage >= 90%)
   - `poetry run mypy src/ --strict` (zero type errors)
   - `poetry run ruff check src/ tests/` (zero lint violations)
   - `poetry run bandit -r src/` (no security issues)
3. If all checks pass, commit to feature branch
4. Mark the TaskList task as completed
5. Report completion to Team Lead

### Quality Check Failure Protocol

If any quality check fails after completing a parent task:
1. Fix the issue within the same parent task scope
2. Re-run ALL quality checks from Check 1 (not just the failed one)
3. Only commit and mark complete when ALL checks pass

---

## Relevant Files Tracking

The implementation plan maintains a "Relevant Files" section that lists every file created or modified during execution.

### Format

```markdown
## Relevant Files

| File | Purpose |
|------|---------|
| `src/orders/domain/order.py` | Order aggregate root with business logic |
| `src/orders/domain/orderLine.py` | OrderLine value object |
| `src/orders/application/placeOrder.py` | Place order command handler |
| `tests/unit/orders/testOrder.py` | Order entity unit tests |
| `tests/integration/orders/testOrderRepo.py` | Repository integration tests |
```

### Maintenance Rules

- Add every new file created during implementation
- Add every existing file modified during implementation
- Include a one-line description of the file's purpose
- Update as you work, not just at the end

---

## Subtask Ordering Rules

1. **MANUAL tasks first**: Always isolated, block everything else
2. **SETUP tasks second**: Project scaffolding before feature code
3. **FR tasks in plan order**: Follow the impl plan's declared sequence
4. **TR tasks after FR**: Technical requirements build on functional foundation
5. **AC tasks after FR and TR**: Validation requires both functional and technical code
6. **DOC tasks last**: Documentation captures the final state

### Dependency Handling

- If subtask X.2 depends on subtask X.1, they MUST be executed in order
- Cross-parent-task dependencies are handled by the TaskList dependency chain
- SETUP tasks have no blockers (they come first)
- QA validation task is blocked by ALL impl tasks for the story

---

## Task Execution per TDD

For each subtask, the Developer follows this precise cycle:

### 1. Read the Subtask

Read the subtask description from the impl plan. Understand:
- What needs to be built
- What the expected behavior is
- What tests are implied

### 2. Write Failing Test (RED)

```python
# Write the test FIRST
def testPlaceOrderWithValidItems():
    order = Order(id=OrderId("o1"), customerId=CustomerId("c1"))
    order.addLine("prod-1", quantity=2, unitPrice=Money(1000))

    order.place()

    assert order.status == OrderStatus.PLACED
```

Run the test. It MUST fail (class/method doesn't exist yet).

### 3. Write Minimal Code (GREEN)

Write the absolute minimum production code to make the test pass:

```python
@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING

    def place(self) -> None:
        self.status = OrderStatus.PLACED
```

Run the test. It MUST pass now.

### 4. Refactor

Clean up the code while keeping tests green:
- Extract methods if too long
- Rename for clarity
- Remove duplication
- Apply DDD patterns from `references/ddd-patterns.md`

### 5. Mark Subtask Complete

Change `[ ]` to `[x]` for this subtask in the impl plan file.

---

## Progress Tracking

Progress is tracked through multiple mechanisms:

| Mechanism | What It Tracks | Persists Across Sessions |
|-----------|---------------|-------------------------|
| Impl plan `[x]` markers | Which subtasks are done | Yes (file on disk) |
| TaskList task status | Which parent tasks are done | Yes (team task list) |
| Git commits | Which code changes are saved | Yes (git history) |
| Developer log | What was implemented and how | Yes (file on disk) |

### Resuming After Interruption

If a session crashes or is interrupted:
1. Read TaskList to find incomplete tasks
2. Read impl plan to find first unchecked `[ ]` subtask
3. Resume from that subtask
4. Git log confirms which commits were made
5. Developer log shows what was completed

---

## MANUAL Task Handling

When the impl plan contains `[MANUAL]` tasks:

1. Team Lead creates the task in TaskList with status `pending`
2. Team Lead notifies user:
   ```
   MANUAL ACTION REQUIRED:
   - Task: {description}
   - What to do: {specific user action needed}
   - Why: {reason this cannot be automated}
   - Blocked tasks: {list of tasks waiting on this}

   Please complete and confirm when done.
   ```
3. All downstream tasks are blocked until user confirms
4. When user confirms, Team Lead marks the MANUAL task as completed
5. Blocked tasks auto-unblock
