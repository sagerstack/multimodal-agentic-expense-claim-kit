"""Repository Interface Template.

A Repository Interface:
- Lives in the DOMAIN layer
- Defines the contract for data persistence
- Has NO implementation details (no SQLAlchemy, no Pydantic)
- Uses domain types (Value Objects, Entities)

The implementation goes in the INFRASTRUCTURE layer.

Customize:
- Replace 'Order' with your Entity name
- Replace 'OrderId' with your Entity's ID type
- Add domain-specific query methods
"""

from abc import ABC, abstractmethod
from typing import Sequence

# Import domain types (from same domain slice)
from .order import Order
from .order_id import OrderId
from .customer_id import CustomerId
from .order_status import OrderStatus


class OrderRepository(ABC):
    """Repository interface for Order aggregate persistence.

    This interface lives in the domain layer and defines the contract
    for storing and retrieving Order aggregates. Implementations
    (e.g., SqlalchemyOrderRepository) live in the infrastructure layer.
    """

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    @abstractmethod
    def save(self, order: Order) -> None:
        """Persist an order.

        Handles both insert (new) and update (existing) operations.

        Args:
            order: Order to persist
        """
        raise NotImplementedError(
            "OrderRepository.save() must be implemented by subclasses"
        )

    @abstractmethod
    def getById(self, orderId: OrderId) -> Order | None:
        """Retrieve an order by its ID.

        Args:
            orderId: Order identifier

        Returns:
            Order if found, None otherwise
        """
        raise NotImplementedError(
            "OrderRepository.getById() must be implemented by subclasses"
        )

    @abstractmethod
    def delete(self, orderId: OrderId) -> None:
        """Delete an order.

        Args:
            orderId: Order identifier

        Raises:
            OrderNotFoundError: If order doesn't exist
        """
        raise NotImplementedError(
            "OrderRepository.delete() must be implemented by subclasses"
        )

    # =========================================================================
    # Query Methods
    # =========================================================================

    @abstractmethod
    def findByCustomer(self, customerId: CustomerId) -> Sequence[Order]:
        """Find all orders for a customer.

        Args:
            customerId: Customer identifier

        Returns:
            Sequence of orders (may be empty)
        """
        raise NotImplementedError(
            "OrderRepository.findByCustomer() must be implemented by subclasses"
        )

    @abstractmethod
    def findByStatus(self, status: OrderStatus) -> Sequence[Order]:
        """Find all orders with a specific status.

        Args:
            status: Order status to filter by

        Returns:
            Sequence of orders (may be empty)
        """
        raise NotImplementedError(
            "OrderRepository.findByStatus() must be implemented by subclasses"
        )

    @abstractmethod
    def findPending(self) -> Sequence[Order]:
        """Find all pending orders (PLACED but not PROCESSING).

        Returns:
            Sequence of pending orders
        """
        raise NotImplementedError(
            "OrderRepository.findPending() must be implemented by subclasses"
        )

    @abstractmethod
    def count(self) -> int:
        """Count total orders.

        Returns:
            Total number of orders
        """
        raise NotImplementedError(
            "OrderRepository.count() must be implemented by subclasses"
        )

    @abstractmethod
    def countByStatus(self, status: OrderStatus) -> int:
        """Count orders with a specific status.

        Args:
            status: Order status to filter by

        Returns:
            Number of orders with that status
        """
        raise NotImplementedError(
            "OrderRepository.countByStatus() must be implemented by subclasses"
        )

    # =========================================================================
    # Existence Checks
    # =========================================================================

    @abstractmethod
    def exists(self, orderId: OrderId) -> bool:
        """Check if an order exists.

        Args:
            orderId: Order identifier

        Returns:
            True if order exists
        """
        raise NotImplementedError(
            "OrderRepository.exists() must be implemented by subclasses"
        )


# =============================================================================
# Null Implementation (for testing or when persistence is not needed)
# =============================================================================


class NullOrderRepository(OrderRepository):
    """Null implementation of OrderRepository.

    Useful for tests or when persistence is not required.
    All operations are no-ops or return empty results.
    """

    def save(self, order: Order) -> None:
        """No-op save."""
        pass

    def getById(self, orderId: OrderId) -> Order | None:
        """Always returns None."""
        return None

    def delete(self, orderId: OrderId) -> None:
        """No-op delete."""
        pass

    def findByCustomer(self, customerId: CustomerId) -> Sequence[Order]:
        """Returns empty list."""
        return []

    def findByStatus(self, status: OrderStatus) -> Sequence[Order]:
        """Returns empty list."""
        return []

    def findPending(self) -> Sequence[Order]:
        """Returns empty list."""
        return []

    def count(self) -> int:
        """Returns 0."""
        return 0

    def countByStatus(self, status: OrderStatus) -> int:
        """Returns 0."""
        return 0

    def exists(self, orderId: OrderId) -> bool:
        """Always returns False."""
        return False


# =============================================================================
# In-Memory Implementation (for testing)
# =============================================================================


class InMemoryOrderRepository(OrderRepository):
    """In-memory implementation of OrderRepository.

    Stores orders in a dictionary. Useful for unit tests.
    """

    def __init__(self) -> None:
        """Initialize with empty storage."""
        self._orders: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        """Store order in memory."""
        self._orders[str(order.id)] = order

    def getById(self, orderId: OrderId) -> Order | None:
        """Retrieve from memory."""
        return self._orders.get(str(orderId))

    def delete(self, orderId: OrderId) -> None:
        """Remove from memory."""
        self._orders.pop(str(orderId), None)

    def findByCustomer(self, customerId: CustomerId) -> Sequence[Order]:
        """Filter by customer."""
        return [o for o in self._orders.values() if o.customerId == customerId]

    def findByStatus(self, status: OrderStatus) -> Sequence[Order]:
        """Filter by status."""
        return [o for o in self._orders.values() if o.status == status]

    def findPending(self) -> Sequence[Order]:
        """Find placed orders."""
        return [o for o in self._orders.values() if o.status == OrderStatus.PLACED]

    def count(self) -> int:
        """Count all orders."""
        return len(self._orders)

    def countByStatus(self, status: OrderStatus) -> int:
        """Count by status."""
        return len([o for o in self._orders.values() if o.status == status])

    def exists(self, orderId: OrderId) -> bool:
        """Check existence."""
        return str(orderId) in self._orders

    def clear(self) -> None:
        """Clear all orders (useful for test cleanup)."""
        self._orders.clear()
