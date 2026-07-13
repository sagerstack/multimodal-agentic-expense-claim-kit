"""Command Handler (Use Case) Template.

A Command Handler:
- Lives in the APPLICATION layer
- Orchestrates domain logic
- Handles cross-cutting concerns (logging, transactions)
- Depends on domain abstractions (repositories, services)
- Returns domain types or simple results

Customize:
- Replace 'PlaceOrder' with your command name
- Update the handler logic
- Add appropriate logging
- Handle domain events if needed
"""

from dataclasses import dataclass
from typing import Any
import structlog

# Import from domain layer
from src.orders.domain.order import Order
from src.orders.domain.order_id import OrderId
from src.orders.domain.order_repository import OrderRepository
from src.orders.domain.exceptions import OrderNotFoundError, EmptyOrderError

# Import from other slices if needed (via their application layer)
from src.customers.application.get_customer import GetCustomerHandler

# Import shared infrastructure
from src.shared.infrastructure.event_bus import EventBus


# =============================================================================
# Command (Input)
# =============================================================================


@dataclass(frozen=True)
class PlaceOrderCommand:
    """Command to place an order.

    Immutable data transfer object containing all information needed
    to execute the use case.
    """

    orderId: str
    requestedBy: str = ""  # User ID for audit purposes


# =============================================================================
# Result (Output)
# =============================================================================


@dataclass
class PlaceOrderResult:
    """Result of placing an order.

    Contains success/failure information and any relevant data.
    """

    success: bool
    orderId: str | None = None
    totalAmount: int | None = None
    errorMessage: str | None = None

    @classmethod
    def ok(cls, orderId: str, totalAmount: int) -> "PlaceOrderResult":
        """Create success result."""
        return cls(success=True, orderId=orderId, totalAmount=totalAmount)

    @classmethod
    def fail(cls, errorMessage: str) -> "PlaceOrderResult":
        """Create failure result."""
        return cls(success=False, errorMessage=errorMessage)


# =============================================================================
# Handler (Use Case)
# =============================================================================


class PlaceOrderHandler:
    """Handler for placing orders.

    This handler orchestrates the order placement workflow:
    1. Retrieve the order
    2. Validate business rules
    3. Place the order (domain operation)
    4. Persist changes
    5. Publish domain events
    6. Return result
    """

    def __init__(
        self,
        orderRepository: OrderRepository,
        customerHandler: GetCustomerHandler,
        eventBus: EventBus,
        logger: Any = None,
    ) -> None:
        """Initialize handler with dependencies.

        Args:
            orderRepository: Repository for order persistence
            customerHandler: Handler to validate customer
            eventBus: Event bus for domain events
            logger: Logger instance (optional, defaults to structlog)
        """
        self._orderRepository = orderRepository
        self._customerHandler = customerHandler
        self._eventBus = eventBus
        self._logger = logger or structlog.get_logger()

    def execute(self, command: PlaceOrderCommand) -> PlaceOrderResult:
        """Execute the place order command.

        Args:
            command: Command with order ID and metadata

        Returns:
            PlaceOrderResult with success/failure and details
        """
        self._logger.info(
            "Placing order",
            orderId=command.orderId,
            requestedBy=command.requestedBy,
        )

        try:
            # 1. Retrieve the order
            orderId = OrderId(command.orderId)
            order = self._orderRepository.getById(orderId)

            if order is None:
                self._logger.warning("Order not found", orderId=command.orderId)
                return PlaceOrderResult.fail(f"Order {command.orderId} not found")

            # 2. Validate customer exists
            customerExists = self._customerHandler.customerExists(order.customerId)
            if not customerExists:
                self._logger.warning(
                    "Customer not found",
                    orderId=command.orderId,
                    customerId=str(order.customerId),
                )
                return PlaceOrderResult.fail(
                    f"Customer {order.customerId} not found"
                )

            # 3. Place the order (domain operation with business logic)
            order.place()

            # 4. Calculate total for result
            total = order.calculateTotal()

            # 5. Persist changes
            self._orderRepository.save(order)

            # 6. Publish domain events
            self._eventBus.publish(
                "order.placed",
                {
                    "orderId": str(order.id),
                    "customerId": str(order.customerId),
                    "totalAmount": total.amount,
                },
            )

            self._logger.info(
                "Order placed successfully",
                orderId=command.orderId,
                totalAmount=total.amount,
            )

            return PlaceOrderResult.ok(
                orderId=str(order.id),
                totalAmount=total.amount,
            )

        except EmptyOrderError as e:
            self._logger.warning(
                "Cannot place empty order",
                orderId=command.orderId,
                error=str(e),
            )
            return PlaceOrderResult.fail("Cannot place order with no items")

        except OrderNotFoundError as e:
            self._logger.warning(
                "Order not found",
                orderId=command.orderId,
                error=str(e),
            )
            return PlaceOrderResult.fail(str(e))

        except Exception as e:
            self._logger.error(
                "Unexpected error placing order",
                orderId=command.orderId,
                error=str(e),
                exc_info=True,
            )
            return PlaceOrderResult.fail(f"Unexpected error: {str(e)}")


# =============================================================================
# Query Handler Example (Read Operations)
# =============================================================================


@dataclass(frozen=True)
class GetOrderQuery:
    """Query to get order details."""

    orderId: str


@dataclass
class OrderDto:
    """Data transfer object for order details.

    Used to return order data to API layer without exposing domain entities.
    """

    id: str
    customerId: str
    status: str
    totalAmount: int
    lineCount: int


class GetOrderHandler:
    """Handler for retrieving order details.

    Query handlers are simpler than command handlers - they just
    retrieve and transform data without side effects.
    """

    def __init__(
        self,
        orderRepository: OrderRepository,
        logger: Any = None,
    ) -> None:
        """Initialize handler."""
        self._orderRepository = orderRepository
        self._logger = logger or structlog.get_logger()

    def execute(self, query: GetOrderQuery) -> OrderDto | None:
        """Execute the get order query.

        Args:
            query: Query with order ID

        Returns:
            OrderDto if found, None otherwise
        """
        orderId = OrderId(query.orderId)
        order = self._orderRepository.getById(orderId)

        if order is None:
            self._logger.debug("Order not found", orderId=query.orderId)
            return None

        return OrderDto(
            id=str(order.id),
            customerId=str(order.customerId),
            status=order.status.value,
            totalAmount=order.calculateTotal().amount,
            lineCount=order.lineCount(),
        )
