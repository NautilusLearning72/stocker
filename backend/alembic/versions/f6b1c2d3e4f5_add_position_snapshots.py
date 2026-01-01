"""add_position_snapshots

Revision ID: f6b1c2d3e4f5
Revises: e2c3f7d09d5a
Create Date: 2026-01-01 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6b1c2d3e4f5"
down_revision = "e2c3f7d09d5a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("portfolio_id", sa.String(length=50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=True),
        sa.Column("qty", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("cost_basis", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("market_value", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("current_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("lastday_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("change_today", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("unrealized_pl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unrealized_plpc", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("unrealized_intraday_pl", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unrealized_intraday_plpc", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("asset_class", sa.String(length=20), nullable=True),
        sa.Column("exchange", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("as_of_ts", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id",
            "symbol",
            "date",
            "source",
            name="uq_position_snapshots_port_sym_date_source",
        ),
    )
    op.create_index(
        "ix_position_snapshots_portfolio_id",
        "position_snapshots",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_position_snapshots_date",
        "position_snapshots",
        ["date"],
    )
    op.create_index(
        "ix_position_snapshots_symbol",
        "position_snapshots",
        ["symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_position_snapshots_symbol", table_name="position_snapshots")
    op.drop_index("ix_position_snapshots_date", table_name="position_snapshots")
    op.drop_index("ix_position_snapshots_portfolio_id", table_name="position_snapshots")
    op.drop_table("position_snapshots")
