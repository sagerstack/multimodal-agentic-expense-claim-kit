<overview>
Error handling patterns for Python: custom exceptions and Result pattern. Domain errors are explicit, application layer uses Result for flow control.
</overview>

<custom_exceptions>
## Custom Exceptions

Define domain-specific exceptions in each slice's `domain/exceptions.py`.

```python
# src/shared/domain/exceptions.py
class DomainError(Exception):
    """Base class for all domain errors"""
    pass

class ValidationError(DomainError):
    """Raised when domain validation fails"""
    pass
```

```python
# src/orders/domain/exceptions.py
from src.shared.domain.exceptions import DomainError, ValidationError

class OrderError(DomainError):
    """Base class for order-related errors"""
    pass

class OrderNotFoundError(OrderError):
    def __init__(self, orderId: str):
        self.orderId = orderId
        super().__init__(f"Order {orderId} not found")

class EmptyOrderError(OrderError):
    def __init__(self, orderId: str):
        self.orderId = orderId
        super().__init__(f"Cannot place empty order {orderId}")

class OrderNotDraftError(OrderError):
    def __init__(self, orderId: str):
        self.orderId = orderId
        super().__init__(f"Order {orderId} is not in draft status")

class InsufficientStockError(OrderError):
    def __init__(self, productId: str, requested: int, available: int):
        self.productId = productId
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for {productId}: requested {requested}, available {available}"
        )
```

**Exception hierarchy:**
```
Exception
└── DomainError (base)
    ├── ValidationError
    ├── OrderError
    │   ├── OrderNotFoundError
    │   ├── EmptyOrderError
    │   └── OrderNotDraftError
    ├── CustomerError
    │   └── CustomerNotFoundError
    └── PaymentError
        └── PaymentDeclinedError
```
</custom_exceptions>

<result_pattern>
## Result Pattern

Use Result for operations that can fail in expected ways. Avoids exception-based flow control in application layer.

```python
# src/shared/domain/result.py
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass
class Result(Generic[T]):
    value: T | None
    error: str | None

    @property
    def isSuccess(self) -> bool:
        return self.error is None

    @property
    def isFailure(self) -> bool:
        return self.error is not None

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(value=value, error=None)

    @classmethod
    def failure(cls, error: str) -> "Result[T]":
        return cls(value=None, error=error)

    def map(self, fn) -> "Result":
        if self.isFailure:
            return self
        return Result.success(fn(self.value))

    def flatMap(self, fn) -> "Result":
        if self.isFailure:
            return self
        return fn(self.value)
```

**Usage in application layer:**

```python
# src/orders/application/placeOrder.py
from src.shared.domain.result import Result
from src.orders.domain.exceptions import DomainError

class PlaceOrderHandler:
    def handle(self, command: PlaceOrderCommand) -> Result[Order]:
        # Validation that returns Result
        order = self._orderRepo.getById(OrderId(command.orderId))
        if not order:
            return Result.failure(f"Order {command.orderId} not found")

        # Domain logic that throws exceptions - catch and convert
        try:
            order.place()
        except DomainError as e:
            return Result.failure(str(e))

        self._orderRepo.save(order)
        return Result.success(order)
```

**Usage in API layer:**

```python
# src/orders/api/routes.py
from fastapi import HTTPException

@router.post("/{orderId}/place")
def placeOrder(orderId: str, handler = Depends(getPlaceOrderHandler)):
    result = handler.handle(PlaceOrderCommand(orderId=orderId))

    if result.isFailure:
        raise HTTPException(status_code=400, detail=result.error)

    return OrderResponse.fromDomain(result.value)
```
</result_pattern>

<when_to_use>
## When to Use Each

| Scenario | Use |
|----------|-----|
| Invalid domain state (business rule violation) | Custom Exception |
| Entity not found | Result.failure() |
| Validation failure (user input) | Result.failure() |
| Programming error (bug) | Let exception propagate |
| External service failure | Custom Exception or Result |

**Domain layer:** Throw custom exceptions for business rule violations
```python
class Order:
    def place(self) -> None:
        if not self.lines:
            raise EmptyOrderError(self.id)  # Business rule - throw
```

**Application layer:** Catch domain exceptions, return Result
```python
class PlaceOrderHandler:
    def handle(self, command) -> Result[Order]:
        try:
            order.place()
        except DomainError as e:
            return Result.failure(str(e))  # Convert to Result
        return Result.success(order)
```

**API layer:** Convert Result to HTTP response
```python
@router.post("/orders")
def createOrder(request, handler):
    result = handler.handle(command)
    if result.isFailure:
        raise HTTPException(400, result.error)  # HTTP error
    return result.value
```
</when_to_use>

<chaining_results>
## Chaining Results

```python
def processOrder(orderId: str) -> Result[Receipt]:
    return (
        getOrder(orderId)
        .flatMap(validateOrder)
        .flatMap(calculateTotal)
        .flatMap(processPayment)
        .map(generateReceipt)
    )

def getOrder(orderId: str) -> Result[Order]:
    order = repo.getById(orderId)
    if not order:
        return Result.failure(f"Order {orderId} not found")
    return Result.success(order)

def validateOrder(order: Order) -> Result[Order]:
    if not order.lines:
        return Result.failure("Order has no items")
    return Result.success(order)

def calculateTotal(order: Order) -> Result[Money]:
    return Result.success(order.calculateTotal())

def processPayment(amount: Money) -> Result[PaymentConfirmation]:
    try:
        confirmation = paymentGateway.charge(amount)
        return Result.success(confirmation)
    except PaymentDeclinedError as e:
        return Result.failure(str(e))
```
</chaining_results>

<testing_errors>
## Testing Error Handling

```python
# Test custom exceptions
def testEmptyOrderRaisesException():
    order = Order(id=OrderId("1"), customerId=CustomerId("c1"))

    with pytest.raises(EmptyOrderError) as excInfo:
        order.place()

    assert excInfo.value.orderId == "1"
    assert "empty order" in str(excInfo.value).lower()

# Test Result pattern
def testHandlerReturnsFailureWhenOrderNotFound():
    mockRepo = Mock(spec=OrderRepository)
    mockRepo.getById.return_value = None
    handler = PlaceOrderHandler(orderRepo=mockRepo, eventBus=Mock())

    result = handler.handle(PlaceOrderCommand(orderId="nonexistent"))

    assert result.isFailure
    assert "not found" in result.error

def testHandlerReturnsSuccessOnValidOrder():
    mockRepo = Mock(spec=OrderRepository)
    order = createTestOrder()
    order.addLine("prod-1", 1, Money(100))
    mockRepo.getById.return_value = order
    handler = PlaceOrderHandler(orderRepo=mockRepo, eventBus=Mock())

    result = handler.handle(PlaceOrderCommand(orderId=order.id.value))

    assert result.isSuccess
    assert result.value.status == "placed"
```
</testing_errors>
