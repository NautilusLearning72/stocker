"""Add order idempotency constraint

Revision ID: 72717c4be009
Revises: g7c2d3e4f5g6
Create Date: 2026-01-02 16:49:51.327843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72717c4be009'
down_revision: Union[str, None] = 'g7c2d3e4f5g6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint for order idempotency (one order per symbol per day)
    op.create_unique_constraint('uq_order_portfolio_symbol_date', 'orders', ['portfolio_id', 'symbol', 'date'])


def downgrade() -> None:
    op.drop_constraint('uq_order_portfolio_symbol_date', 'orders', type_='unique')
