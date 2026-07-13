"""Value Object Template.

A Value Object has:
- No identity (defined entirely by its attributes)
- Immutable (frozen=True)
- Self-validating (validates in __post_init__)
- Equality by value (two VOs with same attributes are equal)

Customize:
- Replace 'Money' with your Value Object name
- Replace 'amount', 'currency' with your attributes
- Add validation rules in __post_init__
- Add domain-specific behavior methods
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Self

# Import domain exceptions (from same domain slice)
from .exceptions import InvalidMoneyError


@dataclass(frozen=True)
class Money:
    """Money value object representing a monetary amount.

    Immutable and self-validating. Two Money objects with the same
    amount and currency are considered equal.
    """

    # Attributes (immutable due to frozen=True)
    amount: int  # Amount in smallest currency unit (e.g., cents)
    currency: str = "USD"

    def __post_init__(self) -> None:
        """Validate value object invariants.

        Raises:
            InvalidMoneyError: If amount is negative or currency is invalid
        """
        if self.amount < 0:
            raise InvalidMoneyError(
                f"Amount cannot be negative: {self.amount}"
            )
        if not self.currency or len(self.currency) != 3:
            raise InvalidMoneyError(
                f"Invalid currency code: {self.currency}"
            )

    # =========================================================================
    # Behavior Methods (Return new instances - immutable)
    # =========================================================================

    def add(self, other: Self) -> Self:
        """Add two Money values.

        Args:
            other: Money to add

        Returns:
            New Money with sum of amounts

        Raises:
            ValueError: If currencies don't match
        """
        self._ensureSameCurrency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Self) -> Self:
        """Subtract Money value.

        Args:
            other: Money to subtract

        Returns:
            New Money with difference

        Raises:
            ValueError: If currencies don't match
            InvalidMoneyError: If result would be negative
        """
        self._ensureSameCurrency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def multiply(self, factor: int | float) -> Self:
        """Multiply by a factor.

        Args:
            factor: Multiplication factor

        Returns:
            New Money with multiplied amount
        """
        newAmount = int(self.amount * factor)
        return Money(amount=newAmount, currency=self.currency)

    def divide(self, divisor: int | float) -> Self:
        """Divide by a divisor.

        Args:
            divisor: Division factor

        Returns:
            New Money with divided amount (rounded down)

        Raises:
            ValueError: If divisor is zero
        """
        if divisor == 0:
            raise ValueError("Cannot divide by zero")
        newAmount = int(self.amount / divisor)
        return Money(amount=newAmount, currency=self.currency)

    # =========================================================================
    # Query Methods
    # =========================================================================

    def isZero(self) -> bool:
        """Check if amount is zero.

        Returns:
            True if amount is zero
        """
        return self.amount == 0

    def isGreaterThan(self, other: Self) -> bool:
        """Compare with another Money.

        Args:
            other: Money to compare

        Returns:
            True if this amount is greater

        Raises:
            ValueError: If currencies don't match
        """
        self._ensureSameCurrency(other)
        return self.amount > other.amount

    def isLessThan(self, other: Self) -> bool:
        """Compare with another Money.

        Args:
            other: Money to compare

        Returns:
            True if this amount is less

        Raises:
            ValueError: If currencies don't match
        """
        self._ensureSameCurrency(other)
        return self.amount < other.amount

    def toDecimal(self) -> Decimal:
        """Convert to decimal in major currency unit.

        Returns:
            Decimal representation (e.g., 10.50 for 1050 cents)
        """
        return Decimal(self.amount) / Decimal(100)

    def format(self) -> str:
        """Format as currency string.

        Returns:
            Formatted string (e.g., "$10.50")
        """
        symbol = {"USD": "$", "EUR": "E", "GBP": "L"}.get(self.currency, self.currency)
        return f"{symbol}{self.toDecimal():.2f}"

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def fromDecimal(cls, value: Decimal | float, currency: str = "USD") -> Self:
        """Create Money from decimal amount.

        Args:
            value: Amount in major currency unit (e.g., 10.50)
            currency: Currency code

        Returns:
            Money instance
        """
        amount = int(Decimal(str(value)) * 100)
        return cls(amount=amount, currency=currency)

    @classmethod
    def zero(cls, currency: str = "USD") -> Self:
        """Create zero Money.

        Args:
            currency: Currency code

        Returns:
            Money with zero amount
        """
        return cls(amount=0, currency=currency)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _ensureSameCurrency(self, other: Self) -> None:
        """Ensure currencies match for operations.

        Raises:
            ValueError: If currencies don't match
        """
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} vs {other.currency}"
            )


# =============================================================================
# Simple Value Object Example (Single Value)
# =============================================================================


@dataclass(frozen=True)
class OrderId:
    """Order identifier value object.

    Wraps a string ID with validation.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate ID format."""
        if not self.value:
            raise ValueError("OrderId cannot be empty")
        if len(self.value) > 50:
            raise ValueError("OrderId too long (max 50 characters)")

    def __str__(self) -> str:
        """String representation."""
        return self.value


@dataclass(frozen=True)
class Email:
    """Email address value object.

    Validates email format on creation.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate email format."""
        if not self.value or "@" not in self.value:
            raise ValueError(f"Invalid email format: {self.value}")
        local, domain = self.value.rsplit("@", 1)
        if not local or not domain or "." not in domain:
            raise ValueError(f"Invalid email format: {self.value}")

    def domain(self) -> str:
        """Extract email domain.

        Returns:
            Domain part of email
        """
        return self.value.rsplit("@", 1)[1]

    def __str__(self) -> str:
        """String representation."""
        return self.value
