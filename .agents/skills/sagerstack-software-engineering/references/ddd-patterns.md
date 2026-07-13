<overview>
Domain-Driven Design patterns for Python. Entities, Value Objects, Aggregates, Domain Events, and Repository pattern implementations with strict domain purity and CamelCase naming.
</overview>

<value_objects>
## Value Objects

Immutable objects defined by their attributes, not identity. Use instead of primitives.
Place shared value objects in `src/shared/domain/valueObjects.py`.

```python
# src/shared/domain/valueObjects.py
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self) -> None:
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", self.value):
            raise InvalidEmailError(self.value)

@dataclass(frozen=True)
class Money:
    amount: int  # Store as cents to avoid float issues
    currency: str = "USD"

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise CurrencyMismatchError(self.currency, other.currency)
        return Money(self.amount + other.amount, self.currency)

    def multiply(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)

@dataclass(frozen=True)
class UserId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise EmptyUserIdError()

@dataclass(frozen=True)
class OrderId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise EmptyOrderIdError()
```

**When to use Value Objects:**
- Email, Money, Address, DateRange, Quantity, PhoneNumber
- Any domain concept with validation rules
- Replace primitives (`str`, `int`, `float`) with meaningful types
</value_objects>

<entities>
## Entities

Objects with identity that persists over time. Identity matters, not attributes.
Place entities within their feature slice: `src/{slice}/domain/`.

```python
# src/customers/domain/customer.py
from dataclasses import dataclass, field
from datetime import datetime
from src.shared.domain.valueObjects import Email, UserId

@dataclass
class Customer:
    id: UserId
    email: Email
    name: str
    createdAt: datetime = field(default_factory=datetime.utcnow)

    def changeEmail(self, newEmail: Email) -> None:
        """Business rule: email change is allowed"""
        self.email = newEmail

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Customer):
            return False
        return self.id == other.id  # Identity comparison

    def __hash__(self) -> int:
        return hash(self.id)
```

**Entity characteristics:**
- Has unique identity (ID)
- Mutable state
- Equality based on identity, not attributes
- Contains business logic related to its state
</entities>

<aggregates>
## Aggregates

Cluster of entities and value objects with a root entity. All modifications go through the root.
Place aggregates within their feature slice: `src/{slice}/domain/`.

```python
# src/orders/domain/order.py
from dataclasses import dataclass, field
from src.shared.domain.valueObjects import Money, OrderId, CustomerId
from .orderLine import OrderLine
from .events import OrderPlaced
from .exceptions import EmptyOrderError, OrderNotDraftError

@dataclass
class Order:
    """Aggregate Root - all access to OrderLines goes through Order"""
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "draft"
    _events: list = field(default_factory=list, repr=False)

    def addLine(self, productId: str, quantity: int, unitPrice: Money) -> None:
        """Business rule: can only add to draft orders"""
        if self.status != "draft":
            raise OrderNotDraftError(self.id)
        self.lines.append(OrderLine(productId, quantity, unitPrice))

    def place(self) -> None:
        """Business rule: order must have at least one line"""
        if not self.lines:
            raise EmptyOrderError(self.id)
        self.status = "placed"
        self._events.append(OrderPlaced(orderId=self.id.value))

    def total(self) -> Money:
        return sum((line.subtotal() for line in self.lines), Money(0))

    def collectEvents(self) -> list:
        events = self._events.copy()
        self._events.clear()
        return events
```

**Aggregate rules:**
- Never modify child entities directly—always through Aggregate Root
- Aggregates are consistency boundaries
- Keep aggregates small (prefer more small aggregates)
- Reference other aggregates by ID, not direct reference
</aggregates>

<domain_events>
## Domain Events

Record that something happened in the domain. Place in slice's domain folder.
Other slices can subscribe to these events for cross-slice communication.

```python
# src/orders/domain/events.py
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class OrderPlaced:
    orderId: str
    occurredAt: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)
class OrderShipped:
    orderId: str
    trackingNumber: str
    occurredAt: datetime = field(default_factory=datetime.utcnow)

@dataclass(frozen=True)
class OrderCancelled:
    orderId: str
    reason: str
    occurredAt: datetime = field(default_factory=datetime.utcnow)
```

**Event characteristics:**
- Immutable (frozen=True)
- Past tense naming (OrderPlaced, not PlaceOrder)
- Contains all data needed by subscribers
- Timestamp for ordering
</domain_events>

<repository_pattern>
## Repository Pattern

Abstract interfaces in slice's domain folder. Implementations in slice's infrastructure folder.

```python
# src/orders/domain/repository.py
from abc import ABC, abstractmethod
from .order import Order
from src.shared.domain.valueObjects import OrderId, CustomerId

class OrderRepository(ABC):
    """Interface defined in domain - implementation in infrastructure"""

    @abstractmethod
    def save(self, order: Order) -> None:
        raise NotImplementedError("OrderRepository.save() must be implemented")

    @abstractmethod
    def getById(self, orderId: OrderId) -> Order | None:
        raise NotImplementedError("OrderRepository.getById() must be implemented")

    @abstractmethod
    def getByCustomer(self, customerId: CustomerId) -> list[Order]:
        raise NotImplementedError("OrderRepository.getByCustomer() must be implemented")
```

```python
# src/orders/infrastructure/sqlalchemyRepo.py
from sqlalchemy.orm import Session
from src.orders.domain.repository import OrderRepository
from src.orders.domain.order import Order
from .models import OrderModel
from .mappers import OrderMapper

class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, session: Session):
        self._session = session
        self._mapper = OrderMapper()

    def save(self, order: Order) -> None:
        model = self._mapper.toModel(order)
        self._session.merge(model)
        self._session.flush()

    def getById(self, orderId: OrderId) -> Order | None:
        model = self._session.get(OrderModel, orderId.value)
        if not model:
            return None
        return self._mapper.toDomain(model)
```

**Repository rules:**
- Interface in domain (no framework dependencies)
- Implementation in infrastructure (can use SQLAlchemy, etc.)
- Methods return domain objects, not ORM models
- Use mappers to convert between domain and persistence
</repository_pattern>

<domain_services>
## Domain Services

Logic that doesn't belong to a single entity. Place in slice's domain folder.

```python
# src/orders/domain/services.py
from .order import Order
from src.shared.domain.valueObjects import Money

class PricingService:
    """Domain service for cross-aggregate business logic"""

    def calculateDiscount(self, order: Order, customerTier: str) -> Money:
        """Business rule: Gold customers get 10% off orders over $100"""
        total = order.total()
        if customerTier == "gold" and total.amount > 10000:
            return Money(total.amount // 10)
        return Money(0)

class OrderValidationService:
    """Domain service for complex validation across entities"""

    def canPlaceOrder(self, order: Order, customerCredit: Money) -> bool:
        """Business rule: order total cannot exceed customer credit"""
        return order.total().amount <= customerCredit.amount
```

**When to use Domain Services:**
- Logic doesn't naturally belong to any entity
- Operation involves multiple aggregates
- Complex validation or calculation
- Stateless operations
</domain_services>

<application_layer>
## Application Layer (Commands/Queries)

Orchestrates domain objects. No business logic here. Place in slice's application folder.

```python
# src/orders/application/placeOrder.py
from dataclasses import dataclass
from src.orders.domain.repository import OrderRepository
from src.orders.domain.order import Order
from src.shared.infrastructure.eventBus import EventBus
from src.shared.domain.result import Result

@dataclass
class PlaceOrderCommand:
    orderId: str

class PlaceOrderHandler:
    def __init__(
        self,
        orderRepo: OrderRepository,
        eventBus: EventBus
    ):
        self._orderRepo = orderRepo
        self._eventBus = eventBus

    def handle(self, command: PlaceOrderCommand) -> Result[None]:
        order = self._orderRepo.getById(OrderId(command.orderId))
        if not order:
            return Result(value=None, error=f"Order {command.orderId} not found")

        try:
            order.place()  # Domain logic in aggregate
        except DomainError as e:
            return Result(value=None, error=str(e))

        self._orderRepo.save(order)

        # Publish events for other slices
        for event in order.collectEvents():
            self._eventBus.publish(event)

        return Result(value=None, error=None)
```

**Application layer rules:**
- Orchestration only, no business logic
- Uses Result pattern for error handling
- Publishes domain events
- Thin layer between API and domain
</application_layer>

<quick_reference>
## Quick Reference

| Concept | Location | Dependencies | Mutable |
|---------|----------|--------------|---------|
| Value Object (shared) | `shared/domain/` | None | No (frozen) |
| Entity | `{slice}/domain/` | Shared VOs | Yes |
| Aggregate | `{slice}/domain/` | Entities, VOs | Yes |
| Repository Interface | `{slice}/domain/` | Domain types | N/A |
| Domain Service | `{slice}/domain/` | Domain types | Stateless |
| Domain Event | `{slice}/domain/` | None | No (frozen) |
| Repository Impl | `{slice}/infrastructure/` | ORM, Domain | Yes |
| Command/Query Handler | `{slice}/application/` | Repositories | Stateless |
| Routes | `{slice}/api/` | Handlers | Stateless |
</quick_reference>

<slice_independence>
## Slice Independence Rules

```python
# ✅ Within same slice
from src.orders.domain.order import Order

# ✅ From shared
from src.shared.domain.valueObjects import Money

# ✅ Cross-slice via application layer (direct service call)
from src.customers.application.getCustomer import GetCustomerHandler

# ❌ Cross-slice domain import (FORBIDDEN)
from src.customers.domain.customer import Customer
```

**Rule:** Domain layer of one slice NEVER imports from domain layer of another slice.
Cross-slice communication happens via:
1. Application layer service calls
2. Domain events (async)
3. Shared interfaces in `shared/domain/`
</slice_independence>
