# Git Workflow

Branch naming, commit conventions, PR creation, and merge protocol for the builder team.

---

## Branch Naming

### Feature Branches

One feature branch per story:

```
feature/epic-{NNN}-story-{NNN}
```

**Examples:**
- `feature/epic-001-story-001`
- `feature/epic-001-story-002`
- `feature/epic-003-story-003`

### Creating a Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/epic-001-story-001
```

### Switching Between Story Branches

When moving from one story to the next within an epic:
```bash
git checkout main
git pull origin main
git checkout -b feature/epic-001-story-002
```

---

## Commit Conventions

### When to Commit

Commit after each **parent task** completion, when ALL quality checks pass:

1. All subtasks `[X.1]` through `[X.N]` are implemented and tests pass
2. Quality check pipeline passes (pytest, coverage, mypy, ruff, bandit)
3. Parent task `[X.0]` is marked `[x]` in the impl plan

### Commit Message Format

Use descriptive conventional commit messages:

```
{type}: {description}

{optional body with details}
```

**Types:**
- `feat`: New feature or capability
- `fix`: Bug fix
- `refactor`: Code restructuring without behavior change
- `test`: Adding or modifying tests
- `chore`: Setup, config, dependencies
- `docs`: Documentation changes

**Examples:**
```
feat: implement Order aggregate with 10-item limit invariant

- OrderId value object with UUID validation
- Order entity with addItem, removeItem, submit methods
- Domain events: OrderItemAdded, OrderSubmitted
- 15 unit tests, 100% domain coverage

chore: set up project structure and dependencies

- Vertical Slice directory layout (orders/)
- Poetry dependencies (pytest, mypy, ruff, bandit)
- .env.example and tests/.env.test templates
- conftest.py with test environment loading

test: add integration tests for order repository

- PostgresOrderRepository with SQLAlchemy session
- Tests cover: save, getById, findAll, delete
- Coverage for infrastructure layer: 95%
```

### Staging Files

Always stage specific files, never use `git add .` or `git add -A`:

```bash
git add src/orders/domain/order.py src/orders/domain/orderId.py
git add tests/unit/orders/testOrder.py tests/unit/orders/testOrderId.py
git add pyproject.toml
```

### Committing

```bash
git commit -m "feat: implement Order aggregate with 10-item limit invariant"
```

---

## Pre-Push Protocol

Before pushing a feature branch:

### 1. Merge Latest from Main

```bash
git fetch origin main
git merge origin/main
```

If merge conflicts occur:
1. Resolve conflicts
2. Re-run full test suite
3. Commit the merge resolution

### 2. Final Quality Check

Run the full quality pipeline one more time:
```bash
poetry run pytest tests/ -v
poetry run pytest --cov=src --cov-fail-under=90
poetry run mypy src/ --strict
poetry run ruff check src/ tests/
poetry run bandit -r src/
```

### 3. Push

```bash
git push -u origin feature/epic-001-story-001
```

---

## Pull Request Creation

PRs are created after all stories in an epic pass QA, or per-story if user prefers.

### PR Scope Options

| Option | When | Branch |
|--------|------|--------|
| Per-story PR | User prefers incremental review | `feature/epic-{NNN}-story-{NNN}` -> `main` |
| Per-epic PR | All stories pass QA, user wants single review | Merge all story branches, then PR to `main` |

### PR Title Format

```
[Epic {NNN}] US-{NNN}: {story title}
```

or for per-epic:

```
[Epic {NNN}] {epic name}: {N} stories implemented
```

### PR Description Template

```markdown
## Summary
- Epic: {NNN} - {epic name}
- Stories implemented: {count}
- Total tasks: {count}
- Test coverage: {N}%

## Stories
- US-{NNN}: {title} - QA PASS
- US-{NNN}: {title} - QA PASS

## Changes
- {Brief description of what was built}

## Quality
- All 9 quality checks passed per story
- Coverage: {N}% (threshold: 90%)
- QA reports: docs/phases/epic-{NNN}-{desc}/qa/

## Test Plan
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] E2E tests pass (if applicable)
- [ ] Docker build succeeds
```

---

## Rules (Non-Negotiable)

1. **Never push directly to main** -- always use feature branches and PRs
2. **Always merge latest from main** before pushing feature branch
3. **Never force push** unless explicitly requested by user
4. **Stage specific files** -- never use `git add .` or `git add -A`
5. **Feature branch per story** -- keep story work isolated
6. **Quality checks before every commit** -- no exceptions
7. **Clean working tree** -- no uncommitted changes when story is "done"
