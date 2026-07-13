---
name: sagerstack:software-engineering
description: Python code architecture with Vertical Slice + DDD and Clean Architecture. Use when designing Python projects, structuring code, creating domain models, defining bounded contexts, or reviewing architecture. Enforces strict domain purity, CamelCase naming, and proper layer separation.
---

<essential_principles>

## How Python Architecture Works

These principles ALWAYS apply when designing Python code.

### 1. Vertical Slice + DDD (Strictly Enforced)

Organize by **feature/bounded context**, not technical layer. Each slice owns its full stack.

```
src/
├── shared/                    # Cross-cutting concerns only
│   ├── domain/                # Shared Value Objects (Money, Email)
│   └── infrastructure/        # Config, DB, event bus
├── orders/                    # Feature slice
│   ├── domain/                # Entities, Aggregates, Repository ABC
│   ├── application/           # Commands, Queries, Handlers
│   ├── infrastructure/        # Repository impl, external APIs
│   └── api/                   # Routes, schemas
├── customers/                 # Another slice
└── payments/                  # Another slice
```

### 2. Strict Domain Purity

Domain layer has **ZERO external dependencies**:
- No SQLAlchemy, Pydantic, or framework types in entities
- Business logic lives in Entities, Value Objects, Domain Services
- Never in API routes or Application layer

```python
# ✅ Domain entity - pure Python
@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine]

    def place(self) -> None:
        if not self.lines:
            raise EmptyOrderError()

# ❌ WRONG - framework types in domain
@dataclass
class Order:
    id: UUID  # Should be OrderId Value Object
    data: BaseModel  # Framework type!
```

### 3. Dependency Rule

Inner layers NEVER import from outer layers. Dependencies point inward.

```
API → Application → Domain ← Infrastructure
                      ↑
              (Domain defines interfaces,
               Infrastructure implements)
```

### 4. CamelCase Naming (Everywhere)

```python
# Classes
class OrderService:
    pass

# Functions and methods
def placeOrder(self, orderId: str) -> None:
    pass

# Variables
orderId = "123"
customerName = "John"

# Even in tests
def testPlaceOrderWithEmptyCart(self):
    pass
```

### 5. Cross-Slice Communication

Direct service calls allowed. Slices can call each other's application services.

```python
# ✅ Allowed - calling another slice's service
from src.customers.application.getCustomer import GetCustomerHandler

class PlaceOrderHandler:
    def __init__(self, customerHandler: GetCustomerHandler):
        self.customerHandler = customerHandler
```

**Also supported:** Domain events for async communication when appropriate.

### 6. Configuration Management

```
.env.local      # Local dev secrets (gitignored)
.env.tests      # Test secrets (gitignored)
.env.example    # Template (committed)
```

Production uses **AWS Secrets Manager**.

### 7. Custom Exceptions + Result Pattern

```python
# Custom exceptions in domain
class OrderNotFoundError(DomainError):
    def __init__(self, orderId: str):
        super().__init__(f"Order {orderId} not found")

# Result pattern for operations that can fail
@dataclass
class Result[T]:
    value: T | None
    error: str | None

    @property
    def isSuccess(self) -> bool:
        return self.error is None
```

### 8. Structured Logging

Format: `[yyyymmdd-HH24:MM:ss] [PID] [CorrelationID] [Class] [Function] [Level] message`

```python
import structlog

logger = structlog.getLogger()
logger.info("Order placed", orderId=orderId, customerId=customerId)
```

### 9. Documentation On Demand Only

Do NOT auto-generate docstrings, README files, or documentation unless explicitly requested.

### 10. Test-Driven Development (Mandatory)

Write failing test -> Write minimum code to pass -> Refactor -> Repeat

**Never write production code without a test first.**

```python
# Step 1: Write failing test
def testCalculateTotalReturnsSum():
    order = Order(id=OrderId("1"), customerId=CustomerId("c1"))
    order.addLine("prod-1", quantity=2, unitPrice=Money(1000))

    total = order.calculateTotal()

    assert total == Money(2000)

# Step 2: Write minimum code to make it pass
def calculateTotal(self) -> Money:
    return Money(sum(line.subtotal().amount for line in self.lines))

# Step 3: Refactor if needed
# Step 4: Next test
```

See `workflows/tdd-workflow.md` for the detailed red-green-refactor process.

### 11. Code Coverage: 90%+ Required

No exceptions. Configure in pyproject.toml:

```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=90"
```

If coverage drops below 90%, the test suite fails. This ensures comprehensive test coverage as a non-negotiable quality standard.

</essential_principles>

<intake>
**What would you like to do?**

1. Design a new feature/bounded context
2. Review existing architecture
3. Refactor to Clean Architecture
4. Add a new slice to existing project
5. Design domain model (Entities, VOs, Aggregates)
6. Something else

**Wait for response, then read the matching workflow.**
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "new", "design", "feature", "create" | `workflows/design-new-feature.md` |
| 2, "review", "audit", "check" | `workflows/review-architecture.md` |
| 3, "refactor", "migrate", "clean" | `workflows/refactor-to-clean-arch.md` |
| 4, "add slice", "bounded context", "new slice" | `workflows/add-bounded-context.md` |
| 5, "domain", "entity", "aggregate", "value object" | `workflows/design-domain-model.md` |
| 6, other | Clarify, then select workflow or references |
</routing>

<reference_index>
## Domain Knowledge

All in `references/`:

**Architecture:**
- clean-architecture.md — Layers, dependency rule, when to use
- vertical-slice.md — Slice organization, independence rules
- project-structures.md — Complete folder layouts

**DDD Patterns:**
- ddd-patterns.md — Entities, Value Objects, Aggregates, Events
- repository-pattern.md — Interface in domain, impl in infrastructure
- domain-services.md — Cross-entity business logic

**Code Style:**
- naming-conventions.md — CamelCase everywhere
- error-handling.md — Custom exceptions, Result pattern
- logging.md — Structured logging format

**Configuration:**
- configuration-management.md — .env files, secrets, pydantic-settings

**Testing:**
- tdd-workflow.md — Red-green-refactor cycle, when to write unit vs integration tests
</reference_index>

<workflows_index>
## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| design-new-feature.md | Design a feature from scratch with DDD |
| review-architecture.md | Audit existing code structure |
| refactor-to-clean-arch.md | Migrate code to Clean Architecture |
| add-bounded-context.md | Add new slice to existing project |
| design-domain-model.md | Create Entities, VOs, Aggregates |
</workflows_index>

<verification>
## After Every Design Decision

Verify:
- [ ] Domain layer has no infrastructure imports
- [ ] Business logic is in domain layer, not API/application
- [ ] Value Objects used instead of primitives where appropriate
- [ ] Slices are independent (no cross-slice domain imports)
- [ ] CamelCase naming throughout
- [ ] Custom exceptions defined for domain errors
- [ ] Tests written FIRST (TDD workflow followed)
- [ ] Coverage >= 90% (run `poetry run pytest --cov`)
</verification>
