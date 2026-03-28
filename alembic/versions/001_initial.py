"""Initial — create btst_positions table

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "btst_positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_date", sa.Text(), nullable=False),
        sa.Column("entry_time", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("entry_premium", sa.Float(), nullable=False),
        sa.Column("strike_price", sa.Integer(), nullable=True),
        sa.Column("exit_premium", sa.Float(), nullable=True),
        sa.Column("exit_date", sa.Text(), nullable=True),
        sa.Column("exit_time", sa.Text(), nullable=True),
        sa.Column("pnl_rupees", sa.Float(), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="OPEN"),
        sa.Column("prediction", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("gap_day_flag", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gap_risk_score", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("gap_risk_label", sa.Text(), nullable=False, server_default="LOW"),
        sa.Column("holiday_name", sa.Text(), nullable=True),
        sa.Column("days_to_next_trading", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    # Index for common queries
    op.create_index("ix_btst_status", "btst_positions", ["status"])
    op.create_index("ix_btst_symbol", "btst_positions", ["symbol"])
    op.create_index("ix_btst_entry_date", "btst_positions", ["entry_date"])


def downgrade() -> None:
    op.drop_index("ix_btst_entry_date")
    op.drop_index("ix_btst_symbol")
    op.drop_index("ix_btst_status")
    op.drop_table("btst_positions")
