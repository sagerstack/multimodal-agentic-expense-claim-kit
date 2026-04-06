"""SQLAlchemy ORM models for expense claims database."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Claim(Base):
    """Expense claim aggregate root."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claimNumber: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, name="claim_number"
    )
    employeeId: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, name="employee_id"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    totalAmount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, name="total_amount"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="SGD"
    )
    # Dual currency support (original currency + converted SGD)
    originalCurrency: Mapped[Optional[str]] = mapped_column(
        String(3), nullable=True, name="original_currency"
    )
    originalAmount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, name="original_amount"
    )
    convertedAmountSgd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, name="converted_amount_sgd"
    )
    submissionDate: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, name="submission_date"
    )
    approvalDate: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, name="approval_date"
    )
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), name="created_at"
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        name="updated_at",
    )

    # Relationships
    receipts: Mapped[list["Receipt"]] = relationship(
        "Receipt", back_populates="claim", cascade="all, delete-orphan"
    )
    auditLogs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="claim", cascade="all, delete-orphan"
    )


class Receipt(Base):
    """Receipt entity with line items stored as JSON."""

    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claimId: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True, name="claim_id"
    )
    receiptNumber: Mapped[str] = mapped_column(String(50), nullable=False, name="receipt_number")
    merchant: Mapped[str] = mapped_column(String(200), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    totalAmount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, name="total_amount"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Dual currency support (original currency + converted SGD)
    originalCurrency: Mapped[Optional[str]] = mapped_column(
        String(3), nullable=True, name="original_currency"
    )
    originalAmount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, name="original_amount"
    )
    convertedAmountSgd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True, name="converted_amount_sgd"
    )
    imagePath: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, name="image_path")
    lineItems: Mapped[dict] = mapped_column(JSONB, nullable=False, name="line_items")
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), name="created_at"
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        name="updated_at",
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="receipts")


class AuditLog(Base):
    """Audit trail for claim modifications."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claimId: Mapped[int] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True, name="claim_id"
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    oldValue: Mapped[Optional[str]] = mapped_column(Text, nullable=True, name="old_value")
    newValue: Mapped[Optional[str]] = mapped_column(Text, nullable=True, name="new_value")
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="auditLogs")
