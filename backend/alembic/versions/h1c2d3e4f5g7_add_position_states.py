"""add_position_states

Revision ID: h1c2d3e4f5g7
Revises: 72717c4be009
Create Date: 2026-01-02 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "h1c2d3e4f5g7"
down_revision = "72717c4be009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("portfolio_id", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.SmallInteger(), nullable=False, default=0),
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("peak_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("trough_price", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("pending_direction", sa.SmallInteger(), nullable=True),
        sa.Column("signal_flip_date", sa.Date(), nullable=True),
        sa.Column("consecutive_flip_days", sa.Integer(), default=0),
        sa.Column("entry_atr", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "portfolio_id", "symbol", name="uq_position_states_port_sym"
        ),
    )
    op.create_index(
        "ix_position_states_portfolio_id",
        "position_states",
        ["portfolio_id"],
    )
    op.create_index(
        "ix_position_states_symbol",
        "position_states",
        ["symbol"],
    )


def downgrade() -> None:
    op.drop_index("ix_position_states_symbol", table_name="position_states")
    op.drop_index("ix_position_states_portfolio_id", table_name="position_states")
    op.drop_table("position_states")
