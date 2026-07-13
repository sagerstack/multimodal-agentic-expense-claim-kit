"""Repository Implementation Template.

A Repository Implementation:
- Lives in the INFRASTRUCTURE layer
- Implements the domain interface
- Contains all persistence technology details (SQLAlchemy, etc.)
- Translates between domain entities and persistence models

Customize:
- Replace 'Order' with your Entity name
- Update the ORM model mapping
- Adjust query implementations for your schema
"""

from typing import Sequence

from sqlalchemy import select, func
from sqlalchemy.orm import Session

# Import from domain layer (interface and types)
from src.orders.domain.order import Order
from src.orders.domain.order_id import OrderId
from src.orders.domain.customer_id import CustomerId
from src.orders.domain.order_status import OrderStatus
from src.orders.domain.order_repository import OrderRepository
from src.orders.domain.exceptions import OrderNotFoundError

# Import infrastructure ORM models
from .models import OrderModel, OrderLineModel


class SqlalchemyOrderRepository(OrderRepository):
    """SQLAlchemy implementation of OrderRepository.

    Handles persistence using SQLAlchemy ORM models and translates
    between domain entities and database records.
    """

    def __init__(self, session: Session) -> None:
        """Initialize with database session.

        Args:
            session: SQLAlchemy session for database operations
        """
        self._session = session

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    def save(self, order: Order) -> None:
        """Persist an order to the database.

        Args:
            order: Order entity to persist
        """
        model = self._toModel(order)
        self._session.merge(model)
        self._session.flush()

    def getById(self, orderId: OrderId) -> Order | None:
        """Retrieve an order by ID.

        Args:
            orderId: Order identifier

        Returns:
            Order entity if found, None otherwise
        """
        stmt = select(OrderModel).where(OrderModel.id == str(orderId))
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return self._toDomain(model)

    def delete(self, orderId: OrderId) -> None:
        """Delete an order from the database.

        Args:
            orderId: Order identifier

        Raises:
            OrderNotFoundError: If order doesn't exist
        """
        stmt = select(OrderModel).where(OrderModel.id == str(orderId))
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            raise OrderNotFoundError(orderId)
        self._session.delete(model)
        self._session.flush()

    # =========================================================================
    # Query Methods
    # =========================================================================

    def findByCustomer(self, customerId: CustomerId) -> Sequence[Order]:
        """Find all orders for a customer.

        Args:
            customerId: Customer identifier

        Returns:
            List of orders
        """
        stmt = (
            select(OrderModel)
            .where(OrderModel.customer_id == str(customerId))
            .order_by(OrderModel.created_at.desc())
        )
        models = self._session.execute(stmt).scalars().all()
        return [self._toDomain(m) for m in models]

    def findByStatus(self, status: OrderStatus) -> Sequence[Order]:
        """Find all orders with a specific status.

        Args:
            status: Order status

        Returns:
            List of orders
        """
        stmt = (
            select(OrderModel)
            .where(OrderModel.status == status.value)
            .order_by(OrderModel.created_at.desc())
        )
        models = self._session.execute(stmt).scalars().all()
        return [self._toDomain(m) for m in models]

    def findPending(self) -> Sequence[Order]:
        """Find all pending orders (PLACED status).

        Returns:
            List of pending orders
        """
        return self.findByStatus(OrderStatus.PLACED)

    def count(self) -> int:
        """Count total orders.

        Returns:
            Total count
        """
        stmt = select(func.count()).select_from(OrderModel)
        return self._session.execute(stmt).scalar_one()

    def countByStatus(self, status: OrderStatus) -> int:
        """Count orders with a specific status.

        Args:
            status: Order status

        Returns:
            Count of orders with that status
        """
        stmt = (
            select(func.count())
            .select_from(OrderModel)
            .where(OrderModel.status == status.value)
        )
        return self._session.execute(stmt).scalar_one()

    def exists(self, orderId: OrderId) -> bool:
        """Check if an order exists.

        Args:
            orderId: Order identifier

        Returns:
            True if exists
        """
        stmt = (
            select(func.count())
            .select_from(OrderModel)
            .where(OrderModel.id == str(orderId))
        )
        return self._session.execute(stmt).scalar_one() > 0

    # =========================================================================
    # Mapping: Domain <-> ORM Model
    # =========================================================================

    def _toModel(self, order: Order) -> OrderModel:
        """Convert domain entity to ORM model.

        Args:
            order: Domain entity

        Returns:
            ORM model
        """
        model = OrderModel(
            id=str(order.id),
            customer_id=str(order.customerId),
            status=order.status.value,
            created_at=order.createdAt,
            metadata=order.metadata,
        )

        # Map line items
        model.lines = [
            OrderLineModel(
                order_id=str(order.id),
                product_id=line.productId,
                quantity=line.quantity,
                unit_price=line.unitPrice.amount,
                currency=line.unitPrice.currency,
            )
            for line in order.lines
        ]

        return model

    def _toDomain(self, model: OrderModel) -> Order:
        """Convert ORM model to domain entity.

        Args:
            model: ORM model

        Returns:
            Domain entity
        """
        from src.orders.domain.order_line import OrderLine
        from src.orders.domain.money import Money

        # Map line items
        lines = [
            OrderLine(
                productId=line.product_id,
                quantity=line.quantity,
                unitPrice=Money(amount=line.unit_price, currency=line.currency),
            )
            for line in model.lines
        ]

        # Create domain entity
        # Note: We bypass __post_init__ validation by setting fields directly
        order = object.__new__(Order)
        order.id = OrderId(model.id)
        order.customerId = CustomerId(model.customer_id)
        order.status = OrderStatus(model.status)
        order.lines = lines
        order.createdAt = model.created_at
        order.metadata = model.metadata or {}
        order.version = model.version

        return order


# =============================================================================
# ORM Models (can be in separate models.py file)
# =============================================================================
"""
Example ORM models. In a real project, these would typically be in a
separate models.py file in the infrastructure layer.

from sqlalchemy import Column, String, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    pass


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    metadata = Column(JSON, nullable=True)
    version = Column(Integer, default=0)

    lines = relationship("OrderLineModel", back_populates="order", cascade="all, delete-orphan")


class OrderLineModel(Base):
    __tablename__ = "order_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), ForeignKey("orders.id"), nullable=False)
    product_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)  # In cents
    currency = Column(String(3), default="USD")

    order = relationship("OrderModel", back_populates="lines")
"""
