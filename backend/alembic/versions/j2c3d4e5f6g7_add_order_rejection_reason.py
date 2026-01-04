"""add_order_rejection_reason

Revision ID: j2c3d4e5f6g7
Revises: i8d9e0f1g2h3
Create Date: 2026-01-04 00:00:00.000000

Add rejection_reason column to orders for broker rejection details.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "j2c3d4e5f6g7"
down_revision = "i8d9e0f1g2h3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("rejection_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "rejection_reason")
