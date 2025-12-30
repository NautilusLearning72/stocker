"""Add user managed universes

Revision ID: 2d6c6be6a1c1
Revises: cc2c5f2b8c1f
Create Date: 2025-01-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from stocker.core.config import settings


# revision identifiers, used by Alembic.
revision: str = "2d6c6be6a1c1"
down_revision: Union[str, None] = "cc2c5f2b8c1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_universe",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_global", sa.Boolean(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "instrument_universe_member",
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["instrument_universe.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("universe_id", "symbol", name="uq_universe_symbol"),
    )
    op.create_index(
        op.f("ix_instrument_universe_member_symbol"),
        "instrument_universe_member",
        ["symbol"],
        unique=False,
    )
    op.create_index(
        op.f("ix_instrument_universe_member_universe_id"),
        "instrument_universe_member",
        ["universe_id"],
        unique=False,
    )
    op.create_table(
        "strategy_universe",
        sa.Column("strategy_id", sa.String(length=100), nullable=False),
        sa.Column("universe_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["universe_id"],
            ["instrument_universe.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", name="uq_strategy_universe_strategy"),
    )
    op.create_index(
        op.f("ix_strategy_universe_strategy_id"),
        "strategy_universe",
        ["strategy_id"],
        unique=False,
    )

    # Seed global universe + default strategy mapping
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            INSERT INTO instrument_universe (name, description, is_global, is_deleted, created_at)
            VALUES (:name, :description, true, false, now())
            RETURNING id
            """
        ),
        {
            "name": "Global",
            "description": "Default global universe",
        },
    )
    global_universe_id = result.scalar_one()

    # Seed members from existing static settings
    symbols = settings.TRADING_UNIVERSE
    if symbols:
        values = [
            {
                "universe_id": global_universe_id,
                "symbol": symbol,
            }
            for symbol in symbols
        ]
        conn.execute(
            sa.text(
                """
                INSERT INTO instrument_universe_member (universe_id, symbol, is_deleted, created_at)
                VALUES (:universe_id, :symbol, false, now())
                """
            ),
            values,
        )

    # Seed strategy mapping
    conn.execute(
        sa.text(
            """
            INSERT INTO strategy_universe (strategy_id, universe_id, created_at)
            VALUES (:strategy_id, :universe_id, now())
            """
        ),
        {
            "strategy_id": settings.DEFAULT_STRATEGY_ID,
            "universe_id": global_universe_id,
        },
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_strategy_universe_strategy_id"), table_name="strategy_universe")
    op.drop_table("strategy_universe")
    op.drop_index(op.f("ix_instrument_universe_member_universe_id"), table_name="instrument_universe_member")
    op.drop_index(op.f("ix_instrument_universe_member_symbol"), table_name="instrument_universe_member")
    op.drop_table("instrument_universe_member")
    op.drop_table("instrument_universe")
