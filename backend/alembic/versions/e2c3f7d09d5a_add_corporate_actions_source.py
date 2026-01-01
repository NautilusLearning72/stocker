"""Add corporate actions source metadata

Revision ID: e2c3f7d09d5a
Revises: 6a4b9ddc3f6a
Create Date: 2025-12-31 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2c3f7d09d5a"
down_revision: Union[str, None] = "6a4b9ddc3f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "corporate_actions",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="yfinance"),
    )
    op.add_column(
        "corporate_actions",
        sa.Column("source_hash", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_corporate_actions_symbol_date_type_source",
        "corporate_actions",
        ["symbol", "date", "action_type", "source"],
    )
    op.alter_column("corporate_actions", "source", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_corporate_actions_symbol_date_type_source",
        "corporate_actions",
        type_="unique",
    )
    op.drop_column("corporate_actions", "source_hash")
    op.drop_column("corporate_actions", "source")
