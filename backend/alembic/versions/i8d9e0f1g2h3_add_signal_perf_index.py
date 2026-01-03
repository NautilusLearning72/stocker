"""add_signal_perf_index

Revision ID: i8d9e0f1g2h3
Revises: h1c2d3e4f5g7
Create Date: 2026-01-03 12:00:00.000000

Add partial index on signal_performance for faster lookup of open positions.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "i8d9e0f1g2h3"
down_revision = "h1c2d3e4f5g7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add partial index for open positions (where exit_date IS NULL)
    # This speeds up queries that find open signal performance records
    op.create_index(
        "ix_signal_perf_open",
        "signal_performance",
        ["portfolio_id", "symbol", "direction"],
        postgresql_where=sa.text("exit_date IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_signal_perf_open", table_name="signal_performance")
