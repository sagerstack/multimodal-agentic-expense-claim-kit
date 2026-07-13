<overview>
Clean Architecture principles for Python applications. Layers, dependency rule, and how it integrates with DDD and Vertical Slice Architecture.
</overview>

<layers>
## Clean Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    API / Presentation                        │
│              Routes, Schemas, Serialization                  │
│                   (FastAPI, Flask)                           │
├─────────────────────────────────────────────────────────────┤
│                      Application                             │
│          Commands, Queries, Application Services             │
│              (Orchestration, no business logic)              │
├─────────────────────────────────────────────────────────────┤
│                        Domain                                │
│   Entities, Value Objects, Aggregates, Domain Services       │
│              Repository Interfaces, Domain Events            │
│                   (Pure Python, no dependencies)             │
├─────────────────────────────────────────────────────────────┤
│                     Infrastructure                           │
│       Repository Implementations, External APIs, DB          │
│           (SQLAlchemy, boto3, requests, etc.)                │
└─────────────────────────────────────────────────────────────┘
         ↑ Dependencies point inward (Dependency Rule)
```
</layers>

<dependency_rule>
## The Dependency Rule

**Inner layers NEVER import from outer layers.**

```python
# ✅ CORRECT: Infrastructure implements domain interface
# src/orders/domain/repository.py (DOMAIN)
from abc import ABC, abstractmethod

class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None:
        raise NotImplementedError()

# src/orders/infrastructure/sqlalchemyRepo.py (INFRASTRUCTURE)
from src.orders.domain.repository import OrderRepository  # Import from inner layer

class SqlAlchemyOrderRepository(OrderRepository):
    def save(self, order: Order) -> None:
        # Implementation using SQLAlchemy
        pass
```

```python
# ❌ WRONG: Domain importing from infrastructure
# src/orders/domain/order.py
from sqlalchemy import Column  # NEVER import framework in domain!
```

**Dependency direction:**
```
API → Application → Domain
                      ↑
              Infrastructure
```

Infrastructure depends on Domain (implements interfaces), but Domain doesn't know Infrastructure exists.
</dependency_rule>

<layer_responsibilities>
## Layer Responsibilities

<api_layer>
### API Layer (Presentation)

**Purpose:** Handle HTTP concerns, serialization, authentication

**Contains:**
- Route definitions (FastAPI routers)
- Request/Response schemas (Pydantic models)
- Dependency injection setup
- Authentication/Authorization middleware

```python
# src/orders/api/routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from .schemas import PlaceOrderRequest, OrderResponse
from .dependencies import getPlaceOrderHandler
from src.orders.application.placeOrder import PlaceOrderHandler, PlaceOrderCommand

router = APIRouter()

@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def placeOrder(
    request: PlaceOrderRequest,
    handler: PlaceOrderHandler = Depends(getPlaceOrderHandler)
):
    command = PlaceOrderCommand(
        customerId=request.customerId,
        items=request.items
    )
    result = handler.handle(command)

    if not result.isSuccess:
        raise HTTPException(status_code=400, detail=result.error)

    return OrderResponse.fromDomain(result.value)
```

**Rules:**
- No business logic here
- Convert between HTTP and application layer
- Handle HTTP-specific concerns (status codes, headers)
</api_layer>

<application_layer>
### Application Layer

**Purpose:** Orchestrate domain objects, transaction boundaries

**Contains:**
- Command handlers (write operations)
- Query handlers (read operations)
- Application services (complex orchestration)

```python
# src/orders/application/placeOrder.py
from dataclasses import dataclass
from src.orders.domain.repository import OrderRepository
from src.orders.domain.order import Order
from src.shared.domain.result import Result
from src.shared.infrastructure.eventBus import EventBus

@dataclass
class PlaceOrderCommand:
    customerId: str
    items: list[dict]

class PlaceOrderHandler:
    def __init__(self, orderRepo: OrderRepository, eventBus: EventBus):
        self._orderRepo = orderRepo
        self._eventBus = eventBus

    def handle(self, command: PlaceOrderCommand) -> Result[Order]:
        # Create domain object
        order = Order.create(
            customerId=CustomerId(command.customerId),
            items=command.items
        )

        # Execute domain logic
        try:
            order.place()
        except DomainError as e:
            return Result.failure(str(e))

        # Persist
        self._orderRepo.save(order)

        # Publish events
        for event in order.collectEvents():
            self._eventBus.publish(event)

        return Result.success(order)
```

**Rules:**
- Orchestration only, no business logic
- Defines transaction boundaries
- Coordinates between domain and infrastructure
</application_layer>

<domain_layer>
### Domain Layer

**Purpose:** Business logic, domain model, rules

**Contains:**
- Entities and Value Objects
- Aggregates
- Domain Services
- Repository interfaces (ABCs)
- Domain Events
- Domain Exceptions

```python
# src/orders/domain/order.py
from dataclasses import dataclass, field
from src.shared.domain.valueObjects import Money, OrderId, CustomerId
from .exceptions import EmptyOrderError

@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "draft"
    _events: list = field(default_factory=list, repr=False)

    def place(self) -> None:
        """Business rule: order must have items"""
        if not self.lines:
            raise EmptyOrderError(self.id)
        self.status = "placed"
        self._events.append(OrderPlaced(orderId=self.id.value))

    @classmethod
    def create(cls, customerId: CustomerId, items: list[dict]) -> "Order":
        order = cls(
            id=OrderId(generateId()),
            customerId=customerId
        )
        for item in items:
            order.addLine(item["productId"], item["quantity"], Money(item["price"]))
        return order
```

**Rules:**
- ZERO external dependencies (no SQLAlchemy, Pydantic, boto3)
- All business logic lives here
- Pure Python only
- Framework-agnostic
</domain_layer>

<infrastructure_layer>
### Infrastructure Layer

**Purpose:** Technical implementations, external integrations

**Contains:**
- Repository implementations
- External API clients
- Database models (ORM)
- Message queue adapters
- File storage adapters

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
        return self._mapper.toDomain(model) if model else None
```

**Rules:**
- Implements domain interfaces
- Contains all framework-specific code
- Handles persistence, external APIs, etc.
</infrastructure_layer>
</layer_responsibilities>

<testing_by_layer>
## Testing by Layer

| Layer | Test Type | Mocking |
|-------|-----------|---------|
| Domain | Unit tests | None (pure Python) |
| Application | Unit tests | Mock repositories |
| Infrastructure | Integration tests | Real DB/services |
| API | E2E tests | Full stack |

```python
# tests/unit/orders/testOrder.py (Domain - no mocks)
def testCannotPlaceEmptyOrder():
    order = Order(id=OrderId("1"), customerId=CustomerId("c1"))

    with pytest.raises(EmptyOrderError):
        order.place()

# tests/unit/orders/testPlaceOrder.py (Application - mock repo)
def testPlaceOrderSavesToRepository():
    mockRepo = Mock(spec=OrderRepository)
    handler = PlaceOrderHandler(orderRepo=mockRepo, eventBus=Mock())

    result = handler.handle(PlaceOrderCommand(customerId="c1", items=[...]))

    assert result.isSuccess
    mockRepo.save.assert_called_once()

# tests/integration/orders/testSqlalchemyRepo.py (Infrastructure - real DB)
def testSaveAndRetrieveOrder(dbSession):
    repo = SqlAlchemyOrderRepository(dbSession)
    order = Order.create(customerId=CustomerId("c1"), items=[...])

    repo.save(order)
    retrieved = repo.getById(order.id)

    assert retrieved.id == order.id
```
</testing_by_layer>

<anti_patterns>
## Anti-Patterns to Avoid

<anti_pattern name="Anemic Domain Model">
**Problem:** Domain objects are just data holders, logic is in services

```python
# ❌ WRONG
@dataclass
class Order:
    id: str
    status: str
    lines: list

class OrderService:
    def placeOrder(self, order: Order) -> None:
        if not order.lines:
            raise ValueError("Empty order")
        order.status = "placed"
```

```python
# ✅ CORRECT
@dataclass
class Order:
    def place(self) -> None:
        if not self.lines:
            raise EmptyOrderError(self.id)
        self.status = "placed"
```
</anti_pattern>

<anti_pattern name="Leaky Abstractions">
**Problem:** Domain layer knows about persistence details

```python
# ❌ WRONG
@dataclass
class Order:
    id: int  # Auto-increment ID (database concept)

    def save(self) -> None:  # Persistence in domain
        db.session.add(self)
```

```python
# ✅ CORRECT
@dataclass
class Order:
    id: OrderId  # Value object

    # No persistence methods - that's repository's job
```
</anti_pattern>

<anti_pattern name="Business Logic in API">
**Problem:** Routes contain domain rules

```python
# ❌ WRONG
@router.post("/orders")
def createOrder(request: CreateOrderRequest):
    if not request.items:
        raise HTTPException(400, "Order must have items")  # Business rule in API!
    # ...
```

```python
# ✅ CORRECT
@router.post("/orders")
def createOrder(request: CreateOrderRequest, handler = Depends(getHandler)):
    result = handler.handle(CreateOrderCommand(...))
    if not result.isSuccess:
        raise HTTPException(400, result.error)  # Just translating domain error
```
</anti_pattern>
</anti_patterns>
