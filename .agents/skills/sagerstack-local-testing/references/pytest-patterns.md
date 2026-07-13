<overview>
pytest patterns for Python testing: fixtures, parametrize, markers, and best practices for test organization.
</overview>

<fixtures>
## Fixtures

**Scope levels:**
- `function` (default): New fixture per test
- `class`: Shared within test class
- `module`: Shared within test file
- `session`: Shared across entire test run

```python
# tests/conftest.py
import pytest
from src.shared.infrastructure.testConfig import getTestSettings

@pytest.fixture(scope="session")
def settings():
    """Session-scoped settings loaded from .env.tests"""
    return getTestSettings()

@pytest.fixture(scope="module")
def dbEngine(settings):
    """Module-scoped database engine"""
    engine = create_engine(settings.databaseUrl)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture
def dbSession(dbEngine):
    """Function-scoped session with rollback"""
    Session = sessionmaker(bind=dbEngine)
    session = Session()
    yield session
    session.rollback()
    session.close()
```

**Factory fixtures:**
```python
@pytest.fixture
def createOrder():
    """Factory fixture for creating test orders"""
    def _createOrder(
        orderId: str = "order-1",
        customerId: str = "customer-1",
        withLines: bool = False
    ) -> Order:
        order = Order(
            id=OrderId(orderId),
            customerId=CustomerId(customerId)
        )
        if withLines:
            order.addLine("prod-1", quantity=1, unitPrice=Money(1000))
        return order
    return _createOrder

def testPlaceOrder(createOrder):
    order = createOrder(withLines=True)
    order.place()
    assert order.status == "placed"
```
</fixtures>

<parametrize>
## Parametrize

Test multiple inputs with single test function:

```python
import pytest

@pytest.mark.parametrize("quantity,unitPrice,expectedTotal", [
    (1, 1000, 1000),
    (2, 1000, 2000),
    (3, 500, 1500),
    (0, 1000, 0),
])
def testOrderLineSubtotal(quantity, unitPrice, expectedTotal):
    line = OrderLine(
        productId="prod-1",
        quantity=quantity,
        unitPrice=Money(unitPrice)
    )

    subtotal = line.calculateSubtotal()

    assert subtotal == Money(expectedTotal)
```

**Parametrize with IDs:**
```python
@pytest.mark.parametrize("email,isValid", [
    ("user@example.com", True),
    ("user.name@domain.co.uk", True),
    ("invalid", False),
    ("@nodomain.com", False),
    ("noat.com", False),
], ids=["valid_simple", "valid_complex", "no_at", "no_local", "no_domain"])
def testEmailValidation(email, isValid):
    if isValid:
        Email(email)  # Should not raise
    else:
        with pytest.raises(InvalidEmailError):
            Email(email)
```

**Multiple parametrize decorators (cartesian product):**
```python
@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
@pytest.mark.parametrize("amount", [100, 1000, 10000])
def testMoneyCreation(currency, amount):
    money = Money(amount=amount, currency=currency)
    assert money.amount == amount
    assert money.currency == currency
```
</parametrize>

<markers>
## Markers

**Built-in markers:**
```python
@pytest.mark.skip(reason="Not implemented yet")
def testFutureFeature():
    pass

@pytest.mark.skipif(
    not os.environ.get("BINANCE_API_KEY"),
    reason="Binance credentials not available"
)
def testBinanceIntegration():
    pass

@pytest.mark.xfail(reason="Known bug, fix pending")
def testKnownBugScenario():
    pass
```

**Custom markers:**
```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests as integration tests",
    "e2e: marks tests as end-to-end tests",
    "localstack: marks tests requiring LocalStack",
]
```

```python
# tests/integration/testS3Repo.py
import pytest

@pytest.mark.integration
@pytest.mark.localstack
def testS3StateRepository(s3Client, s3Bucket):
    # Test requiring LocalStack
    pass
```

**Running with markers:**
```bash
# Run only unit tests (exclude integration, e2e)
poetry run pytest -m "not integration and not e2e"

# Run only LocalStack tests
poetry run pytest -m localstack

# Run everything except slow tests
poetry run pytest -m "not slow"
```
</markers>

<assertions>
## Assertions

**Basic assertions:**
```python
def testOrderStatus():
    order = createOrder()

    assert order.status == "draft"
    assert order.lines == []
    assert order.id is not None
```

**Exception assertions:**
```python
def testEmptyOrderRaises():
    order = Order(id=OrderId("1"), customerId=CustomerId("c1"))

    with pytest.raises(EmptyOrderError) as excInfo:
        order.place()

    assert excInfo.value.orderId == "1"
    assert "empty" in str(excInfo.value).lower()
```

**Approximate assertions (floats):**
```python
def testCalculation():
    result = calculatePercentage(1, 3)

    assert result == pytest.approx(0.333, rel=0.01)
    # Or with absolute tolerance
    assert result == pytest.approx(0.333, abs=0.001)
```

**Collection assertions:**
```python
def testOrderLines():
    order = createOrder()
    order.addLine("prod-1", 1, Money(100))
    order.addLine("prod-2", 2, Money(200))

    assert len(order.lines) == 2
    assert any(line.productId == "prod-1" for line in order.lines)
```
</assertions>

<conftest>
## conftest.py Organization

```python
# tests/conftest.py
"""Root conftest - shared across all tests"""
import pytest
from src.shared.infrastructure.testConfig import getTestSettings

@pytest.fixture(scope="session")
def settings():
    return getTestSettings()


# tests/unit/conftest.py
"""Unit test fixtures - no external dependencies"""
import pytest
from src.shared.domain.valueObjects import OrderId, CustomerId, Money

@pytest.fixture
def orderId():
    return OrderId("test-order-123")

@pytest.fixture
def customerId():
    return CustomerId("test-customer-456")


# tests/integration/conftest.py
"""Integration test fixtures - DB, LocalStack"""
import pytest
import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="module")
def dbEngine(settings):
    engine = create_engine(settings.databaseUrl)
    yield engine
    engine.dispose()

@pytest.fixture(scope="module")
def localstackClient(settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.awsEndpointUrl,
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )


# tests/e2e/conftest.py
"""E2E test fixtures - full application"""
import pytest
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)
```
</conftest>

<test_isolation>
## Test Isolation

**Each test must be independent:**
```python
# ❌ WRONG: Tests depend on each other
class TestOrder:
    order = None

    def testCreateOrder(self):
        TestOrder.order = Order(...)

    def testPlaceOrder(self):
        TestOrder.order.place()  # Depends on previous test!


# ✅ CORRECT: Each test creates its own data
class TestOrder:
    def testCreateOrder(self, createOrder):
        order = createOrder()
        assert order.status == "draft"

    def testPlaceOrder(self, createOrder):
        order = createOrder(withLines=True)
        order.place()
        assert order.status == "placed"
```

**Database isolation with transactions:**
```python
@pytest.fixture
def dbSession(dbEngine):
    """Each test runs in a transaction that gets rolled back"""
    connection = dbEngine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```
</test_isolation>

<async_tests>
## Async Tests

```python
import pytest

@pytest.mark.asyncio
async def testAsyncOperation():
    result = await someAsyncFunction()
    assert result == expected

# With async fixture
@pytest.fixture
async def asyncClient():
    async with AsyncClient(app) as client:
        yield client

@pytest.mark.asyncio
async def testAsyncEndpoint(asyncClient):
    response = await asyncClient.get("/endpoint")
    assert response.status_code == 200
```

**pyproject.toml:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```
</async_tests>
