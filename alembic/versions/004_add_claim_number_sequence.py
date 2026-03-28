"""Add claim number sequence and idempotency key

Revision ID: 004
Revises: 003
Create Date: 2026-03-28

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sequence for claim numbers
    op.execute("CREATE SEQUENCE claim_number_seq START WITH 1")

    # Add idempotency_key column (nullable initially for backfill)
    op.add_column(
        "claims",
        sa.Column("idempotency_key", sa.String(200), nullable=True)
    )

    # Create unique index on idempotency_key
    op.create_index(
        "idx_claims_idempotency_key",
        "claims",
        ["idempotency_key"],
        unique=True
    )

    # Set claim_number default to use sequence
    op.execute(
        """
        ALTER TABLE claims
        ALTER COLUMN claim_number
        SET DEFAULT 'CLAIM-' || LPAD(nextval('claim_number_seq')::TEXT, 3, '0')
        """
    )

    # Backfill existing rows with legacy idempotency keys
    op.execute(
        """
        UPDATE claims
        SET idempotency_key = id::text || '_legacy'
        WHERE idempotency_key IS NULL
        """
    )

    # Make idempotency_key NOT NULL after backfill
    op.alter_column("claims", "idempotency_key", nullable=False)


def downgrade() -> None:
    # Make idempotency_key nullable before dropping
    op.alter_column("claims", "idempotency_key", nullable=True)

    # Remove default from claim_number
    op.execute(
        """
        ALTER TABLE claims
        ALTER COLUMN claim_number
        DROP DEFAULT
        """
    )

    # Drop unique index
    op.drop_index("idx_claims_idempotency_key", table_name="claims")

    # Drop idempotency_key column
    op.drop_column("claims", "idempotency_key")

    # Drop sequence
    op.execute("DROP SEQUENCE claim_number_seq")
