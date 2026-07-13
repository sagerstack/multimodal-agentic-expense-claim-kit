# TDD Workflow

Test-Driven Development is mandatory for all production code. This workflow describes the red-green-refactor cycle in detail.

## The TDD Cycle

```
RED -> GREEN -> REFACTOR -> REPEAT
```

### 1. RED: Write a Failing Test

Start by writing a test that describes the behavior you want. The test MUST fail initially.

```python
def testOrderCalculatesTotalFromLines():
    """Test that order calculates total from all line items."""
    # Arrange
    orderId = OrderId("order-123")
    customerId = CustomerId("customer-456")
    order = Order(id=orderId, customerId=customerId)

    # Act
    order.addLine(productId="prod-1", quantity=2, unitPrice=Money(1000))
    order.addLine(productId="prod-2", quantity=1, unitPrice=Money(500))
    total = order.calculateTotal()

    # Assert
    assert total == Money(2500)
```

**Key points:**
- Test name describes the behavior being tested
- Use CamelCase for test function names
- Follow Arrange-Act-Assert pattern
- Test should fail because the code doesn't exist yet

### 2. GREEN: Write Minimum Code to Pass

Write the simplest code that makes the test pass. Do NOT over-engineer.

```python
@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)

    def addLine(self, productId: str, quantity: int, unitPrice: Money) -> None:
        line = OrderLine(productId=productId, quantity=quantity, unitPrice=unitPrice)
        self.lines.append(line)

    def calculateTotal(self) -> Money:
        return Money(sum(line.subtotal().amount for line in self.lines))
```

**Key points:**
- Only write code needed to pass the test
- Don't add features "you might need later"
- Don't optimize prematurely

### 3. REFACTOR: Improve the Code

Now that tests are green, improve the code quality without changing behavior.

```python
@dataclass
class Order:
    id: OrderId
    customerId: CustomerId
    lines: list[OrderLine] = field(default_factory=list)

    def addLine(self, productId: str, quantity: int, unitPrice: Money) -> None:
        self._validateNewLine(productId, quantity, unitPrice)
        line = OrderLine(productId=productId, quantity=quantity, unitPrice=unitPrice)
        self.lines.append(line)

    def calculateTotal(self) -> Money:
        if not self.lines:
            return Money(0)
        return Money(sum(self._lineSubtotals()))

    def _lineSubtotals(self) -> list[int]:
        return [line.subtotal().amount for line in self.lines]

    def _validateNewLine(self, productId: str, quantity: int, unitPrice: Money) -> None:
        if quantity <= 0:
            raise InvalidQuantityError(quantity)
        if unitPrice.amount <= 0:
            raise InvalidPriceError(unitPrice)
```

**Key points:**
- Tests must stay green after refactoring
- Extract methods for clarity
- Add validation (with corresponding tests!)
- Improve naming

### 4. REPEAT

Write the next failing test and continue the cycle.

## When to Write Which Type of Test

### Unit Tests (80% of tests)

Write unit tests for:
- Domain entities and value objects
- Business logic and calculations
- Validation rules
- Domain services

```python
# tests/unit/orders/testOrder.py
def testOrderRejectsEmptyCart():
    order = Order(id=OrderId("1"), customerId=CustomerId("c1"))

    with pytest.raises(EmptyOrderError):
        order.place()
```

### Integration Tests (15% of tests)

Write integration tests for:
- Repository implementations
- External service adapters
- API endpoints
- Database operations

```python
# tests/integration/orders/testSqlalchemyOrderRepository.py
def testSaveAndRetrieveOrder(dbSession):
    repository = SqlalchemyOrderRepository(dbSession)
    order = createTestOrder()

    repository.save(order)
    retrieved = repository.getById(order.id)

    assert retrieved.id == order.id
    assert len(retrieved.lines) == len(order.lines)
```

### E2E Tests (5% of tests)

Write E2E tests for:
- Critical user workflows
- Cross-slice operations
- System-wide behavior

```python
# tests/e2e/testOrderWorkflow.py
def testCompleteOrderWorkflow(apiClient):
    # Create customer
    customerResponse = apiClient.post("/customers", json={"name": "John"})
    customerId = customerResponse.json()["id"]

    # Create order
    orderResponse = apiClient.post("/orders", json={"customerId": customerId})
    orderId = orderResponse.json()["id"]

    # Add items and place
    apiClient.post(f"/orders/{orderId}/lines", json={"productId": "p1", "quantity": 2})
    apiClient.post(f"/orders/{orderId}/place")

    # Verify
    order = apiClient.get(f"/orders/{orderId}").json()
    assert order["status"] == "placed"
```

## TDD for Domain Models

When building domain models, follow this sequence:

1. **Test Value Object creation and validation**
   ```python
   def testMoneyRejectsNegativeAmount():
       with pytest.raises(InvalidMoneyError):
           Money(-100)
   ```

2. **Test Entity creation**
   ```python
   def testOrderCreatesWithEmptyLines():
       order = Order(id=OrderId("1"), customerId=CustomerId("c1"))
       assert len(order.lines) == 0
   ```

3. **Test Entity behavior**
   ```python
   def testOrderAddLineIncreasesCount():
       order = createTestOrder()
       order.addLine("prod-1", quantity=1, unitPrice=Money(100))
       assert len(order.lines) == 1
   ```

4. **Test business rules and invariants**
   ```python
   def testOrderCannotExceedMaxLines():
       order = createTestOrder()
       for i in range(Order.MAX_LINES):
           order.addLine(f"prod-{i}", quantity=1, unitPrice=Money(100))

       with pytest.raises(MaxLinesExceededError):
           order.addLine("prod-extra", quantity=1, unitPrice=Money(100))
   ```

## Test Naming Convention

Use descriptive names that explain the behavior:

```python
# Pattern: test{Unit}{Behavior}[When{Condition}]

# Good names
def testOrderCalculatesTotalFromAllLines():
def testOrderRejectsNegativeQuantity():
def testMoneyFormatsAsCurrency():
def testPlaceOrderFailsWhenCartIsEmpty():

# Bad names
def testOrder():
def testCalculate():
def test1():
```

## Running the TDD Cycle

```bash
# 1. Run the specific test (should fail - RED)
poetry run pytest tests/unit/orders/testOrder.py::testOrderCalculatesTotal -v

# 2. Write code to make it pass (GREEN)
# ... edit source code ...

# 3. Run test again (should pass)
poetry run pytest tests/unit/orders/testOrder.py::testOrderCalculatesTotal -v

# 4. Run all tests to ensure no regressions
poetry run pytest

# 5. Check coverage
poetry run pytest --cov --cov-fail-under=90
```

## Common TDD Mistakes to Avoid

1. **Writing code before tests** - Always write the test first
2. **Writing too much code at once** - Take baby steps
3. **Testing implementation details** - Test behavior, not internals
4. **Skipping the refactor step** - Clean code matters
5. **Testing multiple things in one test** - One assertion per concept
6. **Mocking everything** - Only mock external dependencies
