<overview>
Test pyramid strategy for Python applications. Unit tests at the base (fast, many), integration in the middle, E2E at the top (slow, few). Always maintain 90%+ coverage.
</overview>

<pyramid>
## The Testing Pyramid

```
        /\
       /  \      E2E Tests (few, slow)
      /----\     - Full workflow tests
     /      \    - Real HTTP calls
    /--------\   Integration Tests (some)
   /          \  - Real DB, LocalStack
  /------------\ - External service mocks
 /              \
/________________\ Unit Tests (many, fast)
                   - Domain logic
                   - Pure Python, no mocks
```

| Type | Count | Speed | Dependencies |
|------|-------|-------|--------------|
| Unit | Many (70%) | Fast (<1s) | None |
| Integration | Some (20%) | Medium (1-10s) | DB, LocalStack |
| E2E | Few (10%) | Slow (10s+) | Full stack |
</pyramid>

<unit_tests>
## Unit Tests

**Location:** `tests/unit/`

**Purpose:** Test individual functions/classes in isolation

**Characteristics:**
- No external dependencies (no DB, no network)
- Domain tests need NO mocks (pure Python)
- Application tests mock repositories
- Fast: entire suite runs in seconds

```python
# tests/unit/orders/testOrder.py
import pytest
from src.orders.domain.order import Order
from src.orders.domain.exceptions import EmptyOrderError
from src.shared.domain.valueObjects import OrderId, CustomerId, Money

class TestOrder:
    def testCannotPlaceEmptyOrder(self):
        order = Order(id=OrderId("1"), customerId=CustomerId("c1"))

        with pytest.raises(EmptyOrderError):
            order.place()

    def testPlaceOrderEmitsEvent(self):
        order = Order(id=OrderId("1"), customerId=CustomerId("c1"))
        order.addLine("prod-1", quantity=1, unitPrice=Money(1000))

        order.place()

        events = order.collectEvents()
        assert len(events) == 1
        assert events[0].orderId == "1"

    def testCalculateTotalSumsLines(self):
        order = Order(id=OrderId("1"), customerId=CustomerId("c1"))
        order.addLine("prod-1", quantity=2, unitPrice=Money(1000))
        order.addLine("prod-2", quantity=1, unitPrice=Money(500))

        total = order.calculateTotal()

        assert total == Money(2500)
```

**When to mock in unit tests:**
- Application layer: mock repositories
- NEVER mock domain objects
- NEVER mock value objects

```python
# tests/unit/orders/testPlaceOrderHandler.py
from unittest.mock import Mock
from src.orders.application.placeOrder import PlaceOrderHandler, PlaceOrderCommand
from src.orders.domain.repository import OrderRepository

def testHandlerSavesOrder():
    mockRepo = Mock(spec=OrderRepository)
    order = createTestOrder()
    order.addLine("prod-1", 1, Money(100))
    mockRepo.getById.return_value = order

    handler = PlaceOrderHandler(orderRepo=mockRepo, eventBus=Mock())
    result = handler.handle(PlaceOrderCommand(orderId="1"))

    assert result.isSuccess
    mockRepo.save.assert_called_once()
```
</unit_tests>

<integration_tests>
## Integration Tests

**Location:** `tests/integration/`

**Purpose:** Test component interactions with real dependencies

**Characteristics:**
- Uses real database (test DB)
- Uses LocalStack for AWS services
- Tests repository implementations
- Module-scoped fixtures for setup/teardown

```python
# tests/integration/orders/testSqlalchemyRepo.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.orders.infrastructure.sqlalchemyRepo import SqlAlchemyOrderRepository
from src.orders.domain.order import Order
from src.shared.domain.valueObjects import OrderId, CustomerId, Money

@pytest.fixture(scope="module")
def dbSession(settings):
    engine = create_engine(settings.databaseUrl)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

class TestSqlAlchemyOrderRepository:
    def testSaveAndRetrieve(self, dbSession):
        repo = SqlAlchemyOrderRepository(dbSession)
        order = Order(id=OrderId("order-1"), customerId=CustomerId("cust-1"))
        order.addLine("prod-1", quantity=2, unitPrice=Money(1000))

        repo.save(order)
        dbSession.commit()

        retrieved = repo.getById(OrderId("order-1"))

        assert retrieved is not None
        assert retrieved.id == order.id
        assert len(retrieved.lines) == 1
```

```python
# tests/integration/localstack/testS3Repository.py
import pytest
import boto3

@pytest.fixture(scope="module")
def s3Client(settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.awsEndpointUrl,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=settings.awsRegion
    )

@pytest.fixture(scope="module")
def s3Bucket(s3Client):
    bucketName = "test-bucket"
    s3Client.create_bucket(Bucket=bucketName)
    yield bucketName
    # Cleanup
    response = s3Client.list_objects_v2(Bucket=bucketName)
    for obj in response.get("Contents", []):
        s3Client.delete_object(Bucket=bucketName, Key=obj["Key"])
    s3Client.delete_bucket(Bucket=bucketName)

def testS3StateRepository(s3Client, s3Bucket):
    repo = S3StateRepository(
        bucket=s3Bucket,
        client=s3Client
    )
    state = TradingState(version=1)

    repo.save(state)
    loaded = repo.load()

    assert loaded.version == 1
```
</integration_tests>

<e2e_tests>
## E2E Tests

**Location:** `tests/e2e/`

**Purpose:** Test complete user workflows end-to-end

**Characteristics:**
- Full stack running
- Real HTTP requests
- Tests user journeys
- Few tests, high value

```python
# tests/e2e/testOrderWorkflow.py
import pytest
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture(scope="module")
def client():
    return TestClient(app)

class TestOrderWorkflow:
    def testCompleteOrderFlow(self, client):
        # 1. Create customer
        customerResponse = client.post("/customers", json={
            "name": "John Doe",
            "email": "john@example.com"
        })
        assert customerResponse.status_code == 201
        customerId = customerResponse.json()["id"]

        # 2. Create order
        orderResponse = client.post("/orders", json={
            "customerId": customerId,
            "items": [
                {"productId": "prod-1", "quantity": 2, "price": 1000}
            ]
        })
        assert orderResponse.status_code == 201
        orderId = orderResponse.json()["id"]

        # 3. Place order
        placeResponse = client.post(f"/orders/{orderId}/place")
        assert placeResponse.status_code == 200
        assert placeResponse.json()["status"] == "placed"

        # 4. Verify order state
        getResponse = client.get(f"/orders/{orderId}")
        assert getResponse.status_code == 200
        assert getResponse.json()["status"] == "placed"
```
</e2e_tests>

<coverage_requirements>
## Coverage Requirements

**Target:** 90%+ (no exceptions)

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src --cov-report=term-missing --cov-fail-under=90"
```

**Coverage by layer:**

| Layer | Target | Approach |
|-------|--------|----------|
| Domain | 95%+ | Unit tests, no mocks |
| Application | 90%+ | Unit tests, mock repos |
| Infrastructure | 80%+ | Integration tests |
| API | 80%+ | E2E tests |

**Exclude from coverage:**
```toml
[tool.coverage.run]
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/migrations/*"
]
```
</coverage_requirements>

<test_organization>
## Test File Organization

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── conftest.py          # Unit test fixtures
│   ├── orders/
│   │   ├── testOrder.py
│   │   ├── testOrderLine.py
│   │   └── testPlaceOrder.py
│   ├── customers/
│   │   └── testCustomer.py
│   └── shared/
│       └── testValueObjects.py
├── integration/
│   ├── conftest.py          # Integration fixtures (DB, LocalStack)
│   ├── orders/
│   │   └── testSqlalchemyRepo.py
│   └── localstack/
│       ├── testS3Repository.py
│       └── testSnsPublisher.py
└── e2e/
    ├── conftest.py          # E2E fixtures (TestClient)
    ├── testOrderWorkflow.py
    └── testCustomerWorkflow.py
```

**Naming convention:**
- Files: `test{ClassName}.py`
- Functions: `test{MethodName}{Scenario}()`
- Classes: `Test{ClassName}`
</test_organization>
