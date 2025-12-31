"""Add strategy config table

Revision ID: a1b2c3d4e5f6
Revises: 2d6c6be6a1c1
Create Date: 2025-12-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from stocker.core.config import settings


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "2d6c6be6a1c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Trading parameters to seed with their metadata
TRADING_PARAMS = [
    # Strategy Parameters
    {"key": "LOOKBACK_DAYS", "value_type": "int", "category": "strategy", "description": "Trend signal lookback period (~6 months)"},
    {"key": "EWMA_LAMBDA", "value_type": "float", "category": "strategy", "description": "Volatility smoothing factor (RiskMetrics standard)"},
    {"key": "TARGET_VOL", "value_type": "float", "category": "strategy", "description": "Annualized portfolio volatility target"},

    # Risk Limits
    {"key": "SINGLE_INSTRUMENT_CAP", "value_type": "float", "category": "risk", "description": "Maximum exposure per instrument"},
    {"key": "GROSS_EXPOSURE_CAP", "value_type": "float", "category": "risk", "description": "Maximum total leverage"},
    {"key": "DRAWDOWN_THRESHOLD", "value_type": "float", "category": "risk", "description": "Circuit breaker trigger level"},
    {"key": "DRAWDOWN_SCALE_FACTOR", "value_type": "float", "category": "risk", "description": "Position reduction when triggered"},

    # Trend Confirmation
    {"key": "CONFIRMATION_ENABLED", "value_type": "bool", "category": "confirmation", "description": "Enable trend confirmation filters"},
    {"key": "CONFIRMATION_TYPE", "value_type": "str", "category": "confirmation", "description": "Type: donchian | dual_ma | both"},
    {"key": "DONCHIAN_PERIOD", "value_type": "int", "category": "confirmation", "description": "Donchian channel lookback days"},
    {"key": "MA_FAST_PERIOD", "value_type": "int", "category": "confirmation", "description": "Fast moving average period"},
    {"key": "MA_SLOW_PERIOD", "value_type": "int", "category": "confirmation", "description": "Slow moving average period"},

    # Exit Rules
    {"key": "EXIT_RULES_ENABLED", "value_type": "bool", "category": "exit", "description": "Enable position-level exit rules"},
    {"key": "TRAILING_STOP_ATR_MULTIPLE", "value_type": "float", "category": "exit", "description": "ATRs from peak to trigger stop"},
    {"key": "ATR_EXIT_MULTIPLE", "value_type": "float", "category": "exit", "description": "ATRs against entry to exit"},
    {"key": "ATR_PERIOD", "value_type": "int", "category": "exit", "description": "ATR calculation period"},
    {"key": "PERSISTENCE_DAYS", "value_type": "int", "category": "exit", "description": "Days signal must persist before flip"},

    # Diversification
    {"key": "DIVERSIFICATION_ENABLED", "value_type": "bool", "category": "diversification", "description": "Enable sector/correlation controls"},
    {"key": "SECTOR_CAP", "value_type": "float", "category": "diversification", "description": "Max exposure per sector"},
    {"key": "ASSET_CLASS_CAP", "value_type": "float", "category": "diversification", "description": "Max exposure per asset class"},
    {"key": "CORRELATION_THROTTLE_ENABLED", "value_type": "bool", "category": "diversification", "description": "Throttle correlated position adds"},
    {"key": "CORRELATION_THRESHOLD", "value_type": "float", "category": "diversification", "description": "Correlation level to trigger throttle"},
    {"key": "CORRELATION_LOOKBACK", "value_type": "int", "category": "diversification", "description": "Days for rolling correlation"},
    {"key": "CORRELATION_SCALE_FACTOR", "value_type": "float", "category": "diversification", "description": "Scale factor when throttled"},

    # Sizing
    {"key": "FRACTIONAL_SIZING_ENABLED", "value_type": "bool", "category": "sizing", "description": "Allow fractional share orders"},
    {"key": "FRACTIONAL_DECIMALS", "value_type": "int", "category": "sizing", "description": "Decimal places for fractional qty"},
    {"key": "MIN_NOTIONAL_USD", "value_type": "float", "category": "sizing", "description": "Minimum order size in dollars"},
    {"key": "MIN_NOTIONAL_MODE", "value_type": "str", "category": "sizing", "description": "Mode: fixed | nav_scaled | liquidity_scaled"},
    {"key": "MIN_NOTIONAL_NAV_BPS", "value_type": "float", "category": "sizing", "description": "Bps of NAV when nav_scaled"},
    {"key": "ALLOW_SHORT_SELLING", "value_type": "bool", "category": "sizing", "description": "Enable short positions"},
]


def upgrade() -> None:
    # Create strategy_config table
    op.create_table(
        "strategy_config",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("key", name="uq_strategy_config_key"),
    )

    # Seed with current values from settings
    conn = op.get_bind()
    for param in TRADING_PARAMS:
        key = param["key"]
        value = str(getattr(settings, key))
        # Convert bool to lowercase string for consistency
        if param["value_type"] == "bool":
            value = value.lower()
        conn.execute(
            sa.text(
                """
                INSERT INTO strategy_config (key, value, value_type, category, description, created_at)
                VALUES (:key, :value, :value_type, :category, :description, now())
                """
            ),
            {
                "key": key,
                "value": value,
                "value_type": param["value_type"],
                "category": param["category"],
                "description": param["description"],
            },
        )


def downgrade() -> None:
    op.drop_table("strategy_config")
