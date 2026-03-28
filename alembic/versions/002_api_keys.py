"""Add api_keys table

Revision ID: 002_api_keys
Revises: 001_initial
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_api_keys"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True, server_default="40"),
        sa.Column("total_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=True),
    )
    op.create_index("ix_apikeys_provider", "api_keys", ["provider"])
    op.create_index("ix_apikeys_active", "api_keys", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_apikeys_active")
    op.drop_index("ix_apikeys_provider")
    op.drop_table("api_keys")
