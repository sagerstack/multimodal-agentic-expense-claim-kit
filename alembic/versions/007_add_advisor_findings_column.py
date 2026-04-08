"""Add advisor_findings JSONB column to claims table

Revision ID: 007
Revises: 006
Create Date: 2026-04-07

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("advisor_findings", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "advisor_findings")
