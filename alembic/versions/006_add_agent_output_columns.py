"""Add agent output columns to claims table

Revision ID: 006
Revises: 005
Create Date: 2026-04-06

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("compliance_findings", postgresql.JSONB(), nullable=True))
    op.add_column("claims", sa.Column("fraud_findings", postgresql.JSONB(), nullable=True))
    op.add_column("claims", sa.Column("advisor_decision", sa.String(50), nullable=True))
    op.add_column("claims", sa.Column("approved_by", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "approved_by")
    op.drop_column("claims", "advisor_decision")
    op.drop_column("claims", "fraud_findings")
    op.drop_column("claims", "compliance_findings")
