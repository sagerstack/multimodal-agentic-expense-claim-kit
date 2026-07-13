<overview>
CamelCase naming conventions for Python code. Applied everywhere: classes, functions, methods, variables, and test functions.
</overview>

<naming_rules>
## CamelCase Everywhere

**Classes:** PascalCase
```python
class OrderService:
    pass

class SqlAlchemyOrderRepository:
    pass

class PlaceOrderCommand:
    pass
```

**Functions and Methods:** camelCase
```python
def placeOrder(orderId: str) -> None:
    pass

def calculateTotal(items: list) -> Money:
    pass

class Order:
    def addLine(self, productId: str, quantity: int) -> None:
        pass

    def collectEvents(self) -> list:
        pass
```

**Variables:** camelCase
```python
orderId = "123"
customerName = "John Doe"
totalAmount = Money(1000)
isActive = True
```

**Constants:** UPPER_SNAKE_CASE (exception)
```python
MAX_RETRY_COUNT = 3
DEFAULT_CURRENCY = "USD"
API_BASE_URL = "https://api.example.com"
```

**Module/File Names:** camelCase
```
src/orders/domain/orderLine.py
src/orders/application/placeOrder.py
src/shared/domain/valueObjects.py
```
</naming_rules>

<test_naming>
## Test Naming

**Test files:** `test` prefix + camelCase
```
tests/unit/orders/testOrder.py
tests/unit/orders/testPlaceOrder.py
tests/integration/testSqlalchemyRepo.py
```

**Test functions:** `test` prefix + camelCase description
```python
def testPlaceOrderWithEmptyCart():
    pass

def testCannotPlaceEmptyOrder():
    pass

def testOrderTotalSumsAllLines():
    pass

def testEmailValidationRejectsInvalidFormat():
    pass
```

**Test classes:** `Test` prefix + PascalCase
```python
class TestOrder:
    def testPlaceOrder(self):
        pass

    def testAddLine(self):
        pass

class TestPlaceOrderHandler:
    def testSuccessfulPlacement(self):
        pass

    def testFailsWithEmptyOrder(self):
        pass
```
</test_naming>

<examples>
## Complete Examples

```python
# src/orders/domain/order.py
from dataclasses import dataclass, field
from src.shared.domain.valueObjects import Money, OrderId, CustomerId
from .orderLine import OrderLine
from .events import OrderPlaced
from .exceptions import EmptyOrderError, OrderNotDraftError

@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)
    status: str = "draft"
    _events: list = field(default_factory=list, repr=False)

    def addLine(self, productId: str, quantity: int, unitPrice: Money) -> None:
        if self.status != "draft":
            raise OrderNotDraftError(self.id)
        newLine = OrderLine(productId, quantity, unitPrice)
        self.lines.append(newLine)

    def place(self) -> None:
        if not self.lines:
            raise EmptyOrderError(self.id)
        self.status = "placed"
        placedEvent = OrderPlaced(orderId=self.id.value)
        self._events.append(placedEvent)

    def calculateTotal(self) -> Money:
        totalAmount = Money(0)
        for line in self.lines:
            lineSubtotal = line.calculateSubtotal()
            totalAmount = totalAmount.add(lineSubtotal)
        return totalAmount

    def collectEvents(self) -> list:
        collectedEvents = self._events.copy()
        self._events.clear()
        return collectedEvents
```

```python
# src/orders/application/placeOrder.py
from dataclasses import dataclass
from src.orders.domain.repository import OrderRepository
from src.orders.domain.order import Order
from src.shared.domain.result import Result
from src.shared.domain.valueObjects import OrderId

@dataclass
class PlaceOrderCommand:
    orderId: str

class PlaceOrderHandler:
    def __init__(self, orderRepo: OrderRepository, eventBus):
        self._orderRepo = orderRepo
        self._eventBus = eventBus

    def handle(self, command: PlaceOrderCommand) -> Result[None]:
        orderId = OrderId(command.orderId)
        existingOrder = self._orderRepo.getById(orderId)

        if not existingOrder:
            errorMessage = f"Order {command.orderId} not found"
            return Result.failure(errorMessage)

        try:
            existingOrder.place()
        except DomainError as domainError:
            return Result.failure(str(domainError))

        self._orderRepo.save(existingOrder)

        pendingEvents = existingOrder.collectEvents()
        for event in pendingEvents:
            self._eventBus.publish(event)

        return Result.success(None)
```

```python
# tests/unit/orders/testOrder.py
import pytest
from src.orders.domain.order import Order
from src.orders.domain.exceptions import EmptyOrderError
from src.shared.domain.valueObjects import OrderId, CustomerId, Money

class TestOrder:
    def testCannotPlaceEmptyOrder(self):
        orderId = OrderId("order-123")
        customerId = CustomerId("customer-456")
        emptyOrder = Order(id=orderId, customerId=customerId)

        with pytest.raises(EmptyOrderError):
            emptyOrder.place()

    def testPlaceOrderEmitsEvent(self):
        orderId = OrderId("order-123")
        customerId = CustomerId("customer-456")
        order = Order(id=orderId, customerId=customerId)
        unitPrice = Money(1000)

        order.addLine(productId="prod-1", quantity=2, unitPrice=unitPrice)
        order.place()

        collectedEvents = order.collectEvents()
        assert len(collectedEvents) == 1
        assert collectedEvents[0].orderId == "order-123"

    def testCalculateTotalSumsAllLines(self):
        orderId = OrderId("order-123")
        customerId = CustomerId("customer-456")
        order = Order(id=orderId, customerId=customerId)

        order.addLine(productId="prod-1", quantity=2, unitPrice=Money(1000))
        order.addLine(productId="prod-2", quantity=1, unitPrice=Money(500))

        totalAmount = order.calculateTotal()
        expectedTotal = Money(2500)

        assert totalAmount == expectedTotal
```
</examples>

<anti_patterns>
## Anti-Patterns

```python
# ❌ WRONG: snake_case
def place_order(order_id: str) -> None:
    pass

customer_name = "John"
is_active = True

# ❌ WRONG: Mixed styles
def placeOrder(order_id: str) -> None:  # Mixed parameter naming
    pass

# ❌ WRONG: Test naming
def test_place_order_with_empty_cart():  # snake_case
    pass
```

```python
# ✅ CORRECT: CamelCase everywhere
def placeOrder(orderId: str) -> None:
    pass

customerName = "John"
isActive = True

def testPlaceOrderWithEmptyCart():
    pass
```
</anti_patterns>
