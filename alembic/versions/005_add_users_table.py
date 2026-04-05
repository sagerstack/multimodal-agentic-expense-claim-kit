"""Add users table with seed data

Revision ID: 005
Revises: 004
Create Date: 2026-04-05

"""

import bcrypt
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # Seed 4 users with bcrypt-hashed passwords
    users_table = sa.table(
        "users",
        sa.column("username", sa.String),
        sa.column("hashed_password", sa.String),
        sa.column("role", sa.String),
        sa.column("employee_id", sa.String),
        sa.column("display_name", sa.String),
    )

    def _hashPassword(plaintext: str) -> str:
        return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    seed_users = [
        {
            "username": "sagar",
            "hashed_password": _hashPassword("sagar123"),
            "role": "user",
            "employee_id": "1010736",
            "display_name": "Sagar",
        },
        {
            "username": "josiah",
            "hashed_password": _hashPassword("josiah123"),
            "role": "user",
            "employee_id": "1010740",
            "display_name": "Josiah",
        },
        {
            "username": "james",
            "hashed_password": _hashPassword("james123"),
            "role": "reviewer",
            "employee_id": "909090",
            "display_name": "James",
        },
        {
            "username": "tung",
            "hashed_password": _hashPassword("tung123"),
            "role": "reviewer",
            "employee_id": "909091",
            "display_name": "Tung",
        },
    ]

    op.bulk_insert(users_table, seed_users)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
