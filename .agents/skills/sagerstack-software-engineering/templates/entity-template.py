"""Domain Entity Template.

An Entity has:
- Identity (unique identifier that persists over time)
- Mutable state (can change while identity stays the same)
- Business logic and invariants

Customize:
- Replace 'Order' with your entity name
- Replace 'OrderId', 'CustomerId' with your Value Objects
- Add domain-specific behavior methods
- Add invariant validation in __post_init__
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Import Value Objects from the same domain slice
from .order_id import OrderId
from .customer_id import CustomerId
from .order_line import OrderLine
from .order_status import OrderStatus

# Import domain exceptions
from .exceptions import EmptyOrderError, OrderAlreadyPlacedError


@dataclass
class Order:
    """Order entity representing a customer's order.

    Aggregates order lines and manages order lifecycle.
    """

    # Required fields (identity and core data)
    id: OrderId
    customerId: CustomerId

    # Optional fields with defaults
    status: OrderStatus = OrderStatus.DRAFT
    lines: list[OrderLine] = field(default_factory=list)
    createdAt: datetime = field(default_factory=datetime.utcnow)

    # Computed fields (set in __post_init__)
    version: int = field(init=False, default=0)

    # Metadata for extensibility
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate invariants on creation."""
        self._validateInvariants()

    def _validateInvariants(self) -> None:
        """Validate all entity invariants.

        Called after any state change to ensure consistency.
        """
        # Add your invariant checks here
        pass

    # =========================================================================
    # Behavior Methods (Business Logic)
    # =========================================================================

    def addLine(
        self,
        productId: str,
        quantity: int,
        unitPrice: "Money",  # noqa: F821 - Forward reference
    ) -> None:
        """Add a line item to the order.

        Args:
            productId: Product identifier
            quantity: Number of units
            unitPrice: Price per unit

        Raises:
            OrderAlreadyPlacedError: If order is not in DRAFT status
        """
        self._ensureDraft()
        line = OrderLine(productId=productId, quantity=quantity, unitPrice=unitPrice)
        self.lines.append(line)
        self._validateInvariants()

    def removeLine(self, productId: str) -> None:
        """Remove a line item from the order.

        Args:
            productId: Product identifier to remove

        Raises:
            OrderAlreadyPlacedError: If order is not in DRAFT status
        """
        self._ensureDraft()
        self.lines = [line for line in self.lines if line.productId != productId]
        self._validateInvariants()

    def place(self) -> None:
        """Place the order for processing.

        Raises:
            EmptyOrderError: If order has no lines
            OrderAlreadyPlacedError: If order is not in DRAFT status
        """
        self._ensureDraft()
        if not self.lines:
            raise EmptyOrderError(self.id)
        self.status = OrderStatus.PLACED
        self._validateInvariants()

    def cancel(self) -> None:
        """Cancel the order.

        Raises:
            InvalidOrderStateError: If order cannot be cancelled
        """
        if self.status not in (OrderStatus.DRAFT, OrderStatus.PLACED):
            raise InvalidOrderStateError(  # noqa: F821
                self.id, self.status, "cancel"
            )
        self.status = OrderStatus.CANCELLED
        self._validateInvariants()

    # =========================================================================
    # Query Methods (No side effects)
    # =========================================================================

    def calculateTotal(self) -> "Money":  # noqa: F821
        """Calculate the total price of all line items.

        Returns:
            Total as Money value object
        """
        if not self.lines:
            from .money import Money
            return Money(0)
        from .money import Money
        totalAmount = sum(line.subtotal().amount for line in self.lines)
        return Money(totalAmount)

    def lineCount(self) -> int:
        """Get the number of line items.

        Returns:
            Number of lines
        """
        return len(self.lines)

    def isEmpty(self) -> bool:
        """Check if order has no lines.

        Returns:
            True if order is empty
        """
        return len(self.lines) == 0

    def isPlaced(self) -> bool:
        """Check if order has been placed.

        Returns:
            True if order is placed or beyond
        """
        return self.status in (
            OrderStatus.PLACED,
            OrderStatus.PROCESSING,
            OrderStatus.COMPLETED,
        )

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _ensureDraft(self) -> None:
        """Ensure order is in DRAFT status.

        Raises:
            OrderAlreadyPlacedError: If not in DRAFT status
        """
        if self.status != OrderStatus.DRAFT:
            raise OrderAlreadyPlacedError(self.id)
