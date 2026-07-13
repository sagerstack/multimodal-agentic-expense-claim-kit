<overview>
Complete Python project folder layouts following Vertical Slice Architecture with DDD. Each slice is self-contained with domain, application, infrastructure, and API layers.
</overview>

<single_module_project>
## Single-Module Project (Vertical Slices)

```
myApi/
├── src/
│   ├── shared/                            # Cross-cutting concerns
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── valueObjects.py            # Money, Email, UserId, etc.
│   │   │   ├── base.py                    # BaseEntity, BaseAggregate
│   │   │   ├── events.py                  # DomainEvent base class
│   │   │   ├── result.py                  # Result pattern
│   │   │   └── exceptions.py              # Base DomainError
│   │   └── infrastructure/
│   │       ├── __init__.py
│   │       ├── config.py                  # Pydantic Settings
│   │       ├── database.py                # DB session factory
│   │       ├── eventBus.py                # Event publisher
│   │       └── logging.py                 # Structured logging setup
│   │
│   ├── orders/                            # ── ORDERS SLICE ──
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── order.py                   # Order aggregate root
│   │   │   ├── orderLine.py               # OrderLine entity
│   │   │   ├── events.py                  # OrderPlaced, OrderShipped
│   │   │   ├── repository.py              # OrderRepository ABC
│   │   │   ├── services.py                # Domain services
│   │   │   └── exceptions.py              # OrderNotFound, etc.
│   │   ├── application/
│   │   │   ├── __init__.py
│   │   │   ├── placeOrder.py              # PlaceOrderCommand + Handler
│   │   │   ├── shipOrder.py               # ShipOrderCommand + Handler
│   │   │   ├── getOrder.py                # GetOrderQuery + Handler
│   │   │   └── listOrders.py              # ListOrdersQuery + Handler
│   │   ├── infrastructure/
│   │   │   ├── __init__.py
│   │   │   ├── models.py                  # SQLAlchemy ORM models
│   │   │   ├── mappers.py                 # Domain <-> ORM mappers
│   │   │   └── sqlalchemyRepo.py          # OrderRepository impl
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── routes.py                  # POST/GET /orders
│   │       ├── schemas.py                 # Pydantic request/response
│   │       └── dependencies.py            # Slice-specific DI
│   │
│   ├── customers/                         # ── CUSTOMERS SLICE ──
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── customer.py                # Customer aggregate
│   │   │   ├── repository.py
│   │   │   └── exceptions.py
│   │   ├── application/
│   │   │   ├── registerCustomer.py
│   │   │   └── getCustomer.py
│   │   ├── infrastructure/
│   │   │   ├── models.py
│   │   │   ├── mappers.py
│   │   │   └── sqlalchemyRepo.py
│   │   └── api/
│   │       ├── routes.py
│   │       └── schemas.py
│   │
│   ├── payments/                          # ── PAYMENTS SLICE ──
│   │   ├── domain/
│   │   ├── application/
│   │   ├── infrastructure/
│   │   │   └── stripeGateway.py           # External service adapter
│   │   └── api/
│   │
│   └── main.py                            # FastAPI app, compose routers
│
├── tests/                                 # Horizontal test structure
│   ├── unit/
│   │   ├── orders/
│   │   │   ├── testOrder.py               # Aggregate tests (no mocks)
│   │   │   ├── testOrderLine.py
│   │   │   └── testPlaceOrder.py          # Handler tests (mock repo)
│   │   ├── customers/
│   │   │   └── testCustomer.py
│   │   └── shared/
│   │       └── testValueObjects.py
│   ├── integration/
│   │   ├── orders/
│   │   │   └── testSqlalchemyRepo.py      # Real DB tests
│   │   └── customers/
│   └── e2e/
│       ├── testOrderWorkflow.py           # Full API workflow tests
│       └── testCustomerWorkflow.py
│
├── pyproject.toml
├── .env.example                           # Template (committed)
├── .env.local                             # Local secrets (gitignored)
├── .env.tests                             # Test secrets (gitignored)
└── .gitignore
```
</single_module_project>

<import_rules>
## Import Rules for Vertical Slices

```python
# ✅ ALLOWED: Import from shared
from src.shared.domain.valueObjects import Money, Email
from src.shared.infrastructure.config import settings

# ✅ ALLOWED: Import within same slice
from src.orders.domain.order import Order
from src.orders.domain.repository import OrderRepository

# ✅ ALLOWED: Cross-slice via application layer
from src.customers.application.getCustomer import GetCustomerHandler

# ❌ FORBIDDEN: Import domain from another slice
from src.customers.domain.customer import Customer  # NO!
```
</import_rules>

<configuration_files>
## Configuration Files

```python
# src/shared/infrastructure/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    databaseUrl: str

    # AWS (for production)
    awsRegion: str = "us-east-1"

    # Application
    debug: bool = False
    environment: str = "local"  # local | prod

    class Config:
        env_file = ".env.local"
        env_file_encoding = "utf-8"

@lru_cache
def getSettings() -> Settings:
    return Settings()

settings = getSettings()
```

```python
# src/shared/infrastructure/testConfig.py
from pydantic_settings import BaseSettings

class TestSettings(BaseSettings):
    databaseUrl: str = "sqlite:///:memory:"

    class Config:
        env_file = ".env.tests"
        env_file_encoding = "utf-8"
```

**.env.example (committed):**
```
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
AWS_REGION=us-east-1
DEBUG=false
ENVIRONMENT=local
```

**.env.local (gitignored):**
```
DATABASE_URL=postgresql://devuser:devpass@localhost:5432/mydb_dev
AWS_REGION=us-east-1
DEBUG=true
ENVIRONMENT=local
```

**.env.tests (gitignored):**
```
DATABASE_URL=postgresql://testuser:testpass@localhost:5432/mydb_test
AWS_REGION=us-east-1
DEBUG=false
ENVIRONMENT=local
```
</configuration_files>

<main_composition>
## Main Application Composition

```python
# src/main.py
from fastapi import FastAPI
from src.orders.api.routes import router as ordersRouter
from src.customers.api.routes import router as customersRouter
from src.payments.api.routes import router as paymentsRouter
from src.shared.infrastructure.logging import setupLogging

app = FastAPI(title="My API")

# Setup structured logging
setupLogging()

# Compose all routers
app.include_router(ordersRouter, prefix="/orders", tags=["orders"])
app.include_router(customersRouter, prefix="/customers", tags=["customers"])
app.include_router(paymentsRouter, prefix="/payments", tags=["payments"])

@app.get("/health")
def healthCheck():
    return {"status": "healthy"}
```
</main_composition>

<multi_module_project>
## Multi-Module Project

For larger projects with separate deployable units:

```
myProject/
├── backend/
│   ├── src/
│   │   ├── shared/
│   │   ├── orders/
│   │   ├── customers/
│   │   └── main.py
│   ├── tests/
│   ├── pyproject.toml
│   └── .env.example
│
├── worker/                            # Background job processor
│   ├── src/
│   │   ├── shared/                    # Can share with backend
│   │   ├── jobs/
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   └── infrastructure/
│   │   └── main.py
│   ├── tests/
│   └── pyproject.toml
│
├── terraform/                         # Infrastructure
│   ├── environments/
│   │   ├── local/
│   │   └── prod/
│   └── modules/
│
└── .github/
    └── workflows/
```
</multi_module_project>

<lambda_project>
## Lambda/Serverless Project

```
tradingSystem/
├── lib/                               # Shared library (pip installable)
│   ├── src/
│   │   ├── shared/
│   │   │   ├── domain/
│   │   │   └── infrastructure/
│   │   ├── trading/
│   │   │   ├── domain/
│   │   │   ├── application/
│   │   │   └── contracts/             # ABCs for adapters
│   │   └── strategies/
│   └── pyproject.toml
│
├── app/                               # Application layer
│   ├── infrastructure/                # Concrete implementations
│   │   ├── binanceAdapter.py
│   │   └── s3StateRepository.py
│   ├── lambda/                        # Lambda handlers
│   │   ├── tradingLambda.py
│   │   ├── executionLambda.py
│   │   └── requirements.txt
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── e2e/
│
├── tests/                             # Library tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docker-compose.yml                 # LocalStack
├── terraform/
└── pyproject.toml
```
</lambda_project>

<key_rules>
## Key Rules Summary

**Slice independence:**
```
orders/     ← Never imports from customers/domain or payments/domain
customers/  ← Never imports from orders/domain or payments/domain
payments/   ← Never imports from orders/domain or customers/domain
```

**Shared only for truly shared concerns:**
```
shared/
├── domain/           # Value objects used by multiple slices
└── infrastructure/   # Config, DB, event bus, logging
```

**Tests are horizontal:**
```
tests/
├── unit/             # Fast, isolated tests
├── integration/      # Tests with real dependencies
└── e2e/              # Full workflow tests
```

**Configuration by environment:**
```
.env.example          # Template (committed)
.env.local            # Local development (gitignored)
.env.tests            # Test execution (gitignored)
AWS Secrets Manager   # Production secrets
```
</key_rules>
