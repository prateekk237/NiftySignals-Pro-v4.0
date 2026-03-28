"""
003: Add SignalLog table + trailing SL + partial exit columns.
"""

from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"


def upgrade():
    # SignalLog table
    op.create_table(
        "signal_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.Text, nullable=False),
        sa.Column("signal_type", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("strike", sa.Integer, nullable=True),
        sa.Column("entry_premium", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("confluence_score", sa.Float, nullable=True),
        sa.Column("premium_30m", sa.Float, nullable=True),
        sa.Column("premium_60m", sa.Float, nullable=True),
        sa.Column("pnl_30m_pct", sa.Float, nullable=True),
        sa.Column("pnl_60m_pct", sa.Float, nullable=True),
        sa.Column("outcome", sa.Text, nullable=True),
        sa.Column("max_favorable", sa.Float, nullable=True),
        sa.Column("max_adverse", sa.Float, nullable=True),
        sa.Column("is_expiry_day", sa.Integer, nullable=False, server_default="0"),
        sa.Column("adx_at_signal", sa.Float, nullable=True),
        sa.Column("vix_at_signal", sa.Float, nullable=True),
        sa.Column("time_of_day", sa.Text, nullable=True),
        sa.Column("weekday", sa.Text, nullable=True),
    )

    # Add columns to btst_positions
    with op.batch_alter_table("btst_positions") as batch:
        batch.add_column(sa.Column("trailing_sl", sa.Float, nullable=True))
        batch.add_column(sa.Column("highest_ltp", sa.Float, nullable=True))
        batch.add_column(sa.Column("trail_stage", sa.Text, nullable=True))
        batch.add_column(sa.Column("total_lots", sa.Integer, nullable=False, server_default="1"))
        batch.add_column(sa.Column("exited_lots", sa.Integer, nullable=False, server_default="0"))
        batch.add_column(sa.Column("partial_exits", sa.Text, nullable=True))


def downgrade():
    op.drop_table("signal_logs")
    with op.batch_alter_table("btst_positions") as batch:
        batch.drop_column("trailing_sl")
        batch.drop_column("highest_ltp")
        batch.drop_column("trail_stage")
        batch.drop_column("total_lots")
        batch.drop_column("exited_lots")
        batch.drop_column("partial_exits")
