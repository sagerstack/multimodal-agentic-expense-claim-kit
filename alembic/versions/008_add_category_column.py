"""Add category VARCHAR column to claims table

Revision ID: 008
Revises: 007
Create Date: 2026-04-08

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("category", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "category")
