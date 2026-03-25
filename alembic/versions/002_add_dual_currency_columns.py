"""Add dual currency columns to claims and receipts

Revision ID: 002
Revises: 001
Create Date: 2026-03-25

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add dual currency columns to claims table
    op.add_column("claims", sa.Column("original_currency", sa.String(3), nullable=True))
    op.add_column("claims", sa.Column("original_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("claims", sa.Column("converted_amount_sgd", sa.Numeric(10, 2), nullable=True))

    # Add dual currency columns to receipts table
    op.add_column("receipts", sa.Column("original_currency", sa.String(3), nullable=True))
    op.add_column("receipts", sa.Column("original_amount", sa.Numeric(10, 2), nullable=True))
    op.add_column("receipts", sa.Column("converted_amount_sgd", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    # Remove dual currency columns from receipts table
    op.drop_column("receipts", "converted_amount_sgd")
    op.drop_column("receipts", "original_amount")
    op.drop_column("receipts", "original_currency")

    # Remove dual currency columns from claims table
    op.drop_column("claims", "converted_amount_sgd")
    op.drop_column("claims", "original_amount")
    op.drop_column("claims", "original_currency")
