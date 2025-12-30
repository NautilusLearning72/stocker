"""Add trading universe

Revision ID: cc2c5f2b8c1f
Revises: b7d3a8c2f91e
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc2c5f2b8c1f"
down_revision: Union[str, None] = "b7d3a8c2f91e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trading_universe",
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("avg_dollar_volume", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "as_of_date",
            "symbol",
            "source",
            name="uq_trading_universe_date_symbol_source",
        ),
    )
    op.create_index(
        op.f("ix_trading_universe_as_of_date"),
        "trading_universe",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trading_universe_symbol"),
        "trading_universe",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trading_universe_symbol"), table_name="trading_universe")
    op.drop_index(op.f("ix_trading_universe_as_of_date"), table_name="trading_universe")
    op.drop_table("trading_universe")
