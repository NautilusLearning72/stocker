"""Add instrument metrics

Revision ID: b7d3a8c2f91e
Revises: 893a09ca3205
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d3a8c2f91e"
down_revision: Union[str, None] = "893a09ca3205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_metrics",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("period_type", sa.String(length=10), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("market_cap", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("enterprise_value", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("shares_outstanding", sa.BigInteger(), nullable=True),
        sa.Column("float_shares", sa.BigInteger(), nullable=True),
        sa.Column("beta", sa.Numeric(precision=6, scale=4), nullable=True),
        sa.Column("pe_ttm", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("pe_forward", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_to_book", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_to_sales", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("peg_ratio", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("ev_to_ebitda", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("ev_to_ebit", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("fcf_yield", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("dividend_rate", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("payout_ratio", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("revenue", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("ebitda", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("net_income", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("free_cash_flow", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("gross_margin", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("operating_margin", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("net_margin", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("ebitda_margin", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("roe", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("roa", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("roic", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("revenue_growth_yoy", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("earnings_growth_yoy", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("eps_growth_yoy", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("fcf_growth_yoy", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("net_debt_to_ebitda", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("interest_coverage", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("current_ratio", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("quick_ratio", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "symbol",
            "as_of_date",
            "period_type",
            "source",
            name="uq_instrument_metrics_symbol_date_period_source",
        ),
    )
    op.create_index(
        op.f("ix_instrument_metrics_as_of_date"),
        "instrument_metrics",
        ["as_of_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_instrument_metrics_symbol"),
        "instrument_metrics",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_instrument_metrics_symbol"), table_name="instrument_metrics")
    op.drop_index(op.f("ix_instrument_metrics_as_of_date"), table_name="instrument_metrics")
    op.drop_table("instrument_metrics")
