<overview>
Structured logging for Python applications. Format: `[yyyymmdd-HH24:MM:ss] [PID] [CorrelationID] [Class] [Function] [Level] message`
</overview>

<logging_setup>
## Logging Setup

```python
# src/shared/infrastructure/logging.py
import structlog
import logging
import os
from datetime import datetime

def setupLogging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""

    # Custom processor for our format
    def customFormatter(logger, methodName, eventDict):
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        pid = os.getpid()
        correlationId = eventDict.pop("correlationId", "-")
        className = eventDict.pop("className", "-")
        functionName = eventDict.pop("functionName", "-")
        level = methodName.upper()
        message = eventDict.pop("event", "")

        # Format: [timestamp] [PID] [CorrelationID] [Class] [Function] [Level] message
        formatted = f"[{timestamp}] [{pid}] [{correlationId}] [{className}] [{functionName}] [{level}] {message}"

        # Add any remaining context as key=value pairs
        if eventDict:
            context = " ".join(f"{k}={v}" for k, v in eventDict.items())
            formatted = f"{formatted} {context}"

        eventDict["event"] = formatted
        return eventDict

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            customFormatter,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper()),
    )
```
</logging_setup>

<logger_usage>
## Using the Logger

```python
# src/orders/application/placeOrder.py
import structlog

class PlaceOrderHandler:
    def __init__(self, orderRepo: OrderRepository, eventBus):
        self._orderRepo = orderRepo
        self._eventBus = eventBus
        self._logger = structlog.getLogger()

    def handle(self, command: PlaceOrderCommand, correlationId: str = None) -> Result[Order]:
        self._logger.info(
            "Processing place order command",
            className="PlaceOrderHandler",
            functionName="handle",
            correlationId=correlationId,
            orderId=command.orderId
        )

        order = self._orderRepo.getById(OrderId(command.orderId))
        if not order:
            self._logger.warning(
                "Order not found",
                className="PlaceOrderHandler",
                functionName="handle",
                correlationId=correlationId,
                orderId=command.orderId
            )
            return Result.failure(f"Order {command.orderId} not found")

        try:
            order.place()
            self._logger.info(
                "Order placed successfully",
                className="PlaceOrderHandler",
                functionName="handle",
                correlationId=correlationId,
                orderId=command.orderId,
                status=order.status
            )
        except DomainError as e:
            self._logger.error(
                "Failed to place order",
                className="PlaceOrderHandler",
                functionName="handle",
                correlationId=correlationId,
                orderId=command.orderId,
                error=str(e)
            )
            return Result.failure(str(e))

        self._orderRepo.save(order)
        return Result.success(order)
```

**Output:**
```
[20260121-14:30:45] [12345] [req-abc-123] [PlaceOrderHandler] [handle] [INFO] Processing place order command orderId=order-456
[20260121-14:30:45] [12345] [req-abc-123] [PlaceOrderHandler] [handle] [INFO] Order placed successfully orderId=order-456 status=placed
```
</logger_usage>

<correlation_id>
## Correlation ID Middleware

```python
# src/shared/infrastructure/middleware.py
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, callNext):
        correlationId = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

        # Bind correlation ID to all logs in this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlationId=correlationId)

        response = await callNext(request)
        response.headers["X-Correlation-ID"] = correlationId
        return response
```

```python
# src/main.py
from fastapi import FastAPI
from src.shared.infrastructure.middleware import CorrelationIdMiddleware
from src.shared.infrastructure.logging import setupLogging

app = FastAPI()

setupLogging()
app.add_middleware(CorrelationIdMiddleware)
```
</correlation_id>

<log_levels>
## Log Levels

| Level | Use For |
|-------|---------|
| DEBUG | Detailed diagnostic info (disabled in prod) |
| INFO | Normal operations, state transitions, business events |
| WARNING | Unexpected but handled situations |
| ERROR | Errors that need attention but don't crash the app |
| CRITICAL | System failures requiring immediate action |

```python
# DEBUG - detailed diagnostic
logger.debug("Parsing order items", itemCount=len(items))

# INFO - normal operations
logger.info("Order placed", orderId=orderId, total=total)

# WARNING - handled but unexpected
logger.warning("Retry attempt", attempt=3, maxAttempts=5)

# ERROR - needs attention
logger.error("Payment failed", orderId=orderId, error=str(e))

# CRITICAL - system failure
logger.critical("Database connection lost", host=dbHost)
```
</log_levels>

<class_logger_pattern>
## Class Logger Pattern

```python
# src/orders/domain/order.py
import structlog

class Order:
    _logger = structlog.getLogger()

    def place(self) -> None:
        if not self.lines:
            self._logger.warning(
                "Attempted to place empty order",
                className="Order",
                functionName="place",
                orderId=self.id.value
            )
            raise EmptyOrderError(self.id)

        self.status = "placed"
        self._events.append(OrderPlaced(orderId=self.id.value))

        self._logger.info(
            "Order status changed to placed",
            className="Order",
            functionName="place",
            orderId=self.id.value,
            lineCount=len(self.lines)
        )
```
</class_logger_pattern>

<lambda_logging>
## Lambda/CloudWatch Logging

For AWS Lambda, use JSON output for CloudWatch:

```python
# src/shared/infrastructure/lambdaLogging.py
import structlog
import logging
import os

def setupLambdaLogging() -> None:
    """Configure JSON logging for AWS Lambda/CloudWatch."""

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),  # JSON for CloudWatch
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    )
```

**Output (JSON for CloudWatch):**
```json
{
  "timestamp": "2026-01-21T14:30:45.123Z",
  "level": "info",
  "event": "Order placed",
  "correlationId": "req-abc-123",
  "className": "PlaceOrderHandler",
  "functionName": "handle",
  "orderId": "order-456"
}
```
</lambda_logging>
