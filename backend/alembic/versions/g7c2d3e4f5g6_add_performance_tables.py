"""add_performance_tables

Revision ID: g7c2d3e4f5g6
Revises: a1b2c3d4e5f6, f6b1c2d3e4f5
Create Date: 2026-01-01 13:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "g7c2d3e4f5g6"
down_revision = ("a1b2c3d4e5f6", "f6b1c2d3e4f5")  # Merge both heads
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Performance Metrics Daily
    op.create_table(
        "performance_metrics_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("portfolio_id", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("daily_return", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("daily_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("rolling_sharpe_30d", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("rolling_vol_30d", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("rolling_max_dd_30d", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("long_exposure", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("short_exposure", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "date", name="uq_perf_metrics_daily_port_date"
        ),
    )
    op.create_index(
        "ix_perf_metrics_daily_portfolio_date",
        "performance_metrics_daily",
        ["portfolio_id", "date"],
    )

    # Execution Metrics Daily
    op.create_table(
        "execution_metrics_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("portfolio_id", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("orders_placed", sa.Integer(), default=0),
        sa.Column("orders_filled", sa.Integer(), default=0),
        sa.Column("orders_partial", sa.Integer(), default=0),
        sa.Column("orders_rejected", sa.Integer(), default=0),
        sa.Column("total_slippage", sa.Numeric(precision=18, scale=4), default=0),
        sa.Column("total_commission", sa.Numeric(precision=18, scale=4), default=0),
        sa.Column("avg_fill_rate", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("avg_fill_time_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "date", name="uq_exec_metrics_daily_port_date"
        ),
    )
    op.create_index(
        "ix_exec_metrics_daily_portfolio_date",
        "execution_metrics_daily",
        ["portfolio_id", "date"],
    )

    # Signal Performance
    op.create_table(
        "signal_performance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("portfolio_id", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.SmallInteger(), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("holding_days", sa.Integer(), nullable=True),
        sa.Column("realized_return", sa.Numeric(precision=12, scale=8), nullable=True),
        sa.Column("is_winner", sa.Boolean(), nullable=True),
        sa.Column("exit_reason", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_signal_perf_portfolio",
        "signal_performance",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_signal_perf_symbol",
        "signal_performance",
        ["symbol"],
    )
    op.create_index(
        "ix_signal_perf_signal_date",
        "signal_performance",
        ["signal_date"],
    )
    op.create_index(
        "ix_signal_perf_exit_date",
        "signal_performance",
        ["exit_date"],
    )

    # Add unique constraint to portfolio_state for time-series queries
    op.create_index(
        "ix_portfolio_state_portfolio_date",
        "portfolio_state",
        ["portfolio_id", "date"],
    )


def downgrade() -> None:
    # Remove portfolio_state index
    op.drop_index("ix_portfolio_state_portfolio_date", table_name="portfolio_state")

    # Signal Performance
    op.drop_index("ix_signal_perf_exit_date", table_name="signal_performance")
    op.drop_index("ix_signal_perf_signal_date", table_name="signal_performance")
    op.drop_index("ix_signal_perf_symbol", table_name="signal_performance")
    op.drop_index("ix_signal_perf_portfolio", table_name="signal_performance")
    op.drop_table("signal_performance")

    # Execution Metrics Daily
    op.drop_index("ix_exec_metrics_daily_portfolio_date", table_name="execution_metrics_daily")
    op.drop_table("execution_metrics_daily")

    # Performance Metrics Daily
    op.drop_index("ix_perf_metrics_daily_portfolio_date", table_name="performance_metrics_daily")
    op.drop_table("performance_metrics_daily")
