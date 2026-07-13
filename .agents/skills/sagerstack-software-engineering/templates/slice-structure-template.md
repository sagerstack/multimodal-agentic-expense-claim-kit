# Vertical Slice Structure Template

This template shows the folder structure for a feature slice following
Vertical Slice Architecture + DDD principles.

## Slice Structure

```
src/
├── {slice_name}/                    # Feature bounded context
│   ├── __init__.py
│   │
│   ├── domain/                      # Domain layer (pure Python, no dependencies)
│   │   ├── __init__.py
│   │   │
│   │   ├── # Entities (have identity, mutable)
│   │   ├── order.py                 # Order entity
│   │   ├── order_line.py            # OrderLine entity
│   │   │
│   │   ├── # Value Objects (immutable, no identity)
│   │   ├── order_id.py              # OrderId value object
│   │   ├── customer_id.py           # CustomerId value object
│   │   ├── money.py                 # Money value object
│   │   ├── order_status.py          # OrderStatus enum
│   │   │
│   │   ├── # Repository interfaces (ABC only)
│   │   ├── order_repository.py      # OrderRepository ABC
│   │   │
│   │   ├── # Domain services (cross-entity logic)
│   │   ├── pricing_service.py       # PricingService
│   │   │
│   │   └── # Domain exceptions
│   │   └── exceptions.py            # OrderNotFoundError, EmptyOrderError, etc.
│   │
│   ├── application/                 # Application layer (use cases)
│   │   ├── __init__.py
│   │   │
│   │   ├── # Commands (write operations)
│   │   ├── place_order.py           # PlaceOrderCommand, PlaceOrderHandler
│   │   ├── cancel_order.py          # CancelOrderCommand, CancelOrderHandler
│   │   ├── add_line.py              # AddLineCommand, AddLineHandler
│   │   │
│   │   └── # Queries (read operations)
│   │   ├── get_order.py             # GetOrderQuery, GetOrderHandler
│   │   └── list_orders.py           # ListOrdersQuery, ListOrdersHandler
│   │
│   ├── infrastructure/              # Infrastructure layer (implementations)
│   │   ├── __init__.py
│   │   │
│   │   ├── # Repository implementations
│   │   ├── sqlalchemy_order_repository.py
│   │   │
│   │   ├── # ORM models
│   │   ├── models.py                # OrderModel, OrderLineModel
│   │   │
│   │   └── # External service adapters
│   │   └── payment_gateway_adapter.py
│   │
│   └── api/                         # API layer (presentation)
│       ├── __init__.py
│       │
│       ├── # Route definitions
│       ├── routes.py                # FastAPI/Flask routes
│       │
│       ├── # Request/Response schemas
│       ├── schemas.py               # Pydantic models for API
│       │
│       └── # Dependencies
│       └── dependencies.py          # DI container setup
│
└── shared/                          # Cross-cutting concerns
    ├── __init__.py
    │
    ├── domain/                      # Shared domain types
    │   ├── __init__.py
    │   ├── money.py                 # Shared Money value object
    │   └── email.py                 # Shared Email value object
    │
    └── infrastructure/              # Shared infrastructure
        ├── __init__.py
        ├── config/
        │   ├── settings.py          # Pydantic settings
        │   └── test_config.py       # Test settings loader
        ├── database/
        │   └── session.py           # SQLAlchemy session factory
        └── event_bus/
            └── event_bus.py         # Domain event publishing
```

## Tests Structure (Horizontal)

```
tests/
├── __init__.py
├── conftest.py                      # Shared fixtures
│
├── unit/                            # Unit tests (fast, isolated)
│   ├── {slice_name}/
│   │   ├── test_order.py            # Order entity tests
│   │   ├── test_money.py            # Money VO tests
│   │   └── test_place_order.py      # Handler tests with mocks
│   └── shared/
│       └── test_email.py
│
├── integration/                     # Integration tests (with real deps)
│   ├── {slice_name}/
│   │   └── test_sqlalchemy_order_repository.py
│   └── localstack/
│       └── test_s3_integration.py
│
└── e2e/                             # End-to-end tests
    └── test_order_workflow.py
```

## Layer Dependencies

```
┌─────────────────────────────────────────────────┐
│                    API Layer                     │
│         (routes, schemas, dependencies)          │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│               Application Layer                  │
│         (commands, queries, handlers)            │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│                 Domain Layer                     │
│    (entities, VOs, repository interfaces)        │
│            NO EXTERNAL DEPENDENCIES              │
└─────────────────────────────────────────────────┘
                        ▲
                        │
┌─────────────────────────────────────────────────┐
│              Infrastructure Layer                │
│        (repository impl, ORM, adapters)          │
│            IMPLEMENTS domain interfaces          │
└─────────────────────────────────────────────────┘
```

## Key Rules

### Domain Layer
- ZERO external dependencies (no SQLAlchemy, Pydantic, etc.)
- Pure Python with dataclasses
- Contains ALL business logic
- Defines repository interfaces (ABC)

### Application Layer
- Orchestrates domain logic
- Handles logging, transactions
- Depends only on domain abstractions
- No business logic here

### Infrastructure Layer
- Implements domain interfaces
- Contains all external dependencies
- ORM models, API clients, etc.
- Can depend on domain layer

### API Layer
- HTTP/GraphQL endpoints
- Request validation (Pydantic schemas)
- Calls application handlers
- No business logic

## Creating a New Slice

1. Create the folder structure above
2. Start with domain layer (TDD):
   - Write tests for Value Objects
   - Write tests for Entities
   - Define repository interface
3. Implement application layer:
   - Write tests for handlers
   - Implement handlers
4. Implement infrastructure:
   - Repository implementation
   - ORM models
5. Add API layer:
   - Routes
   - Schemas
   - Wire up DI

## Cross-Slice Communication

Slices can communicate via:

1. **Direct service calls** (synchronous):
   ```python
   from src.customers.application.get_customer import GetCustomerHandler

   class PlaceOrderHandler:
       def __init__(self, customerHandler: GetCustomerHandler):
           self.customerHandler = customerHandler
   ```

2. **Domain events** (asynchronous):
   ```python
   self.eventBus.publish("order.placed", {"orderId": str(order.id)})
   ```

**Never import from another slice's domain layer directly.**
