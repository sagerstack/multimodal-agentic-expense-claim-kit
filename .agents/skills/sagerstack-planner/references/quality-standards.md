# Code Quality Standards

Reference for all planning agents. Defines the quality standards that implementation plans must be designed to satisfy. The builder team enforces these during development.

---

## SOLID Principles

All code must follow SOLID:

| Principle | Rule | Impact on Planning |
|-----------|------|-------------------|
| **SRP** | Each class/function has one reason to change | Implementation tasks should be scoped to single responsibilities |
| **OCP** | Open for extension, closed for modification | Design patterns should support extensibility |
| **LSP** | Subtypes substitutable for base types | Interface contracts must be well-defined in plans |
| **ISP** | Many focused interfaces over one fat interface | Plan should specify narrow interfaces |
| **DIP** | Depend on abstractions, not concretions | Plans should reference interfaces, not implementations |

---

## Type System Requirements

- ALL functions must have type hints (parameters + return types)
- Use `Protocol` from typing for interface definitions
- Use generics for reusable containers
- MyPy strict mode must pass

---

## Error Handling Standards

### Custom Exception Hierarchies
```
DomainException (base)
  ValidationError
    InvalidEmailError
    InvalidAmountError
  BusinessRuleViolation
    InsufficientFundsError
  EntityNotFoundError
```

### Result Pattern
```python
@dataclass
class Result[T]:
    value: T | None
    error: str | None

    @property
    def isSuccess(self) -> bool:
        return self.error is None
```

### Error Message Quality
- Actionable: tell the user WHAT went wrong and HOW to fix it
- Include relevant context (IDs, values that failed validation)
- Never expose internal details or stack traces to end users

---

## Logging Standards

- ALWAYS use structured logging (never `print`)
- Format: `[timestamp] [PID] [CorrelationID] [Class] [Function] [Level] message`
- Include correlation IDs for request tracing
- NEVER log passwords, tokens, or PII without redaction

### Log Levels
| Level | Use |
|-------|-----|
| DEBUG | Variable values, internal state |
| INFO | Use case execution, domain events |
| WARNING | Validation failures, retries |
| ERROR | Unexpected exceptions, integration failures |
| CRITICAL | System failure, database unreachable |

---

## Data Quality Policies

### NO_MOCK_DATA_POLICY
- Production code MUST use real API data extraction
- Follow tech research field mappings exactly
- No placeholder data in production paths
- Unit tests: mocks OK. Integration/E2E: real APIs required.

### NO_HARDCODING_POLICY
- No hardcoded values in source code
- All configuration from .env files or app_config.py
- No hardcoded token pairs, quote tokens, or market structures
- Dynamic discovery from real API data

### NO_ARTIFICIAL_LIMITS_POLICY
- Every numeric limit must have technical justification
- Business criteria filters BEFORE technical limits
- No arbitrary pagination defaults without explanation

### COMPLETE_API_DATA_POLICY
- Cache complete entities from API responses
- Never discard fields that may be needed later
- Derive secondary data from primary cached data

### FILTER_BEFORE_LIMIT_POLICY
- Always: Filter (business rules) -> Sort -> Limit (technical)
- Never: Sort -> Limit -> Filter (wrong order)
- Justify every technical limit with inline comment

---

## Configuration Management

### Separation Rule
| Category | Location | Characteristics |
|----------|----------|-----------------|
| **Secrets** | `.env.local` (gitignored) | API keys, passwords, endpoints. No defaults. |
| **Configuration** | `app_config.py` (in code) | Feature flags, timeouts, thresholds. With defaults. |

### Decision Tree
1. Different per environment? -> `.env.local`
2. Contains sensitive data? -> `.env.local`
3. Can have sensible default? -> `app_config.py`

### Files
- `.env.local` - Secrets only (gitignored)
- `.env.example` - Template showing secret placeholders (committed)
- `tests/.env.test` - Test configuration (in tests/ folder)
- `app_config.py` - Configuration with defaults (committed)

---

## Testing Standards

### Coverage Requirements
- Minimum 90% code coverage (from software-engineering skill)
- All test types: unit, integration, E2E, live verification
- Test naming: `test_should_{behavior}_when_{condition}_given_{context}`

### Test Pyramid
| Level | Scope | Speed | Dependencies |
|-------|-------|-------|-------------|
| Unit | Single function | Fast | Mocked |
| Integration | Component interaction | Medium | Test doubles |
| E2E | Full workflow | Slow | Docker + real services |
| Live | Production-like | Varies | Real external APIs |

### TDD Mandatory
1. RED: Write failing test first
2. GREEN: Minimum code to pass
3. REFACTOR: Clean up while tests pass

---

## Architecture Standards

### Vertical Slice + DDD
- Organize by feature/bounded context, not technical layer
- Each slice owns: domain, application, infrastructure, api
- Shared cross-cutting concerns in `shared/`

### Domain Purity (STRICT)
- Domain layer has ZERO external dependencies
- No SQLAlchemy, Pydantic, or framework types in entities
- Business logic lives in domain layer only

### Dependency Rule
```
API -> Application -> Domain <- Infrastructure
```
Inner layers NEVER import from outer layers.

### CamelCase Naming (EVERYWHERE)
- Classes: `OrderService`
- Functions: `placeOrder`
- Variables: `orderId`
- Tests: `testPlaceOrderWithEmptyCart`

### Dependency Injection
- Constructor injection throughout
- Depend on interfaces (Protocol), not concrete implementations
- No service locator pattern

---

## Quality Check Pipeline

The builder's Code QA agent runs these 9 checks:

| # | Check | Command | Threshold |
|---|-------|---------|-----------|
| 1 | Test Suite | `poetry run pytest tests/ -v` | All pass |
| 2 | Coverage | `poetry run pytest --cov=src --cov-fail-under=90` | >= 90% |
| 3 | Type Check | `poetry run mypy src/ --strict` | 0 errors |
| 4 | Linting | `poetry run ruff check src/ tests/` | 0 violations |
| 5 | Formatting | `poetry run ruff format --check src/ tests/` | All formatted |
| 6 | Security | `poetry run bandit -r src/` | No high/critical |
| 7 | Docker Build | `docker-compose build` | Builds OK |
| 8 | CHANGELOG | Verify entry exists | Present |
| 9 | Git Status | `git status` | Clean tree |

Implementation plans must be designed so that the resulting code can pass all 9 checks.

---

## Immutability Standards

- Value Objects: Use `@dataclass(frozen=True)`
- Validate in `__post_init__`
- Return new instances from operations (no mutation)
- Avoid mutable default arguments

---

## Function Size

- Keep functions under 20 lines
- Single responsibility per function
- Prefer composition over inheritance
- Use generators for large datasets
- Use async/await for I/O-bound operations
