"""Expand market sentiment fields

Revision ID: 6a4b9ddc3f6a
Revises: 893a09ca3205
Create Date: 2025-12-30 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a4b9ddc3f6a"
down_revision: Union[str, None] = "893a09ca3205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "market_sentiment",
        sa.Column("period", sa.String(length=10), nullable=False, server_default="WEEKLY"),
    )
    op.add_column(
        "market_sentiment",
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column("market_sentiment", sa.Column("positive_count", sa.Integer(), nullable=True))
    op.add_column("market_sentiment", sa.Column("neutral_count", sa.Integer(), nullable=True))
    op.add_column("market_sentiment", sa.Column("negative_count", sa.Integer(), nullable=True))
    op.add_column("market_sentiment", sa.Column("source_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "market_sentiment",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("market_sentiment", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint(
        "uq_market_sentiment_symbol_date_source_period",
        "market_sentiment",
        ["symbol", "date", "source", "period", "window_days"],
    )
    op.alter_column("market_sentiment", "period", server_default=None)
    op.alter_column("market_sentiment", "window_days", server_default=None)
    op.alter_column("market_sentiment", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_market_sentiment_symbol_date_source_period",
        "market_sentiment",
        type_="unique",
    )
    op.drop_column("market_sentiment", "updated_at")
    op.drop_column("market_sentiment", "created_at")
    op.drop_column("market_sentiment", "source_hash")
    op.drop_column("market_sentiment", "negative_count")
    op.drop_column("market_sentiment", "neutral_count")
    op.drop_column("market_sentiment", "positive_count")
    op.drop_column("market_sentiment", "window_days")
    op.drop_column("market_sentiment", "period")
