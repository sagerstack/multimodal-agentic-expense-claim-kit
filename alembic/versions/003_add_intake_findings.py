"""Add intake_findings JSONB column to claims table

Revision ID: 003
Revises: 002
Create Date: 2026-03-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add intake_findings JSONB column with default empty object
    op.add_column(
        "claims",
        sa.Column(
            "intake_findings",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}"
        )
    )

    # Add GIN index for efficient JSONB queries
    op.create_index(
        "idx_claims_intake_findings",
        "claims",
        ["intake_findings"],
        postgresql_using="gin"
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index("idx_claims_intake_findings", table_name="claims")

    # Drop column
    op.drop_column("claims", "intake_findings")
