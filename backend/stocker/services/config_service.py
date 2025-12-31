"""
Configuration service for strategy parameters.

Provides CRUD operations for strategy configuration stored in the database.
DB values take precedence over environment variables.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.strategy_config import StrategyConfig

logger = logging.getLogger(__name__)


# Trading parameters metadata for seeding and validation
TRADING_PARAMS: Dict[str, Dict[str, Any]] = {
    # Strategy Parameters
    "LOOKBACK_DAYS": {
        "value_type": "int", "category": "strategy", "min": 1, "max": 500,
        "description": "Days of price history to analyze",
        "tooltip": "How far back to look when deciding if a stock is trending up or down. 126 days = ~6 months. Longer periods catch bigger trends but react slower to changes."
    },
    "EWMA_LAMBDA": {
        "value_type": "float", "category": "strategy", "min": 0.0, "max": 1.0,
        "description": "How much to weight recent volatility",
        "tooltip": "Controls how quickly the system adapts to changing market conditions. Higher values (closer to 1) mean slower adaptation and smoother estimates. 0.94 is an industry standard that balances responsiveness with stability."
    },
    "TARGET_VOL": {
        "value_type": "float", "category": "strategy", "min": 0.01, "max": 1.0,
        "description": "Target portfolio risk level",
        "tooltip": "The amount of price swings you're comfortable with, expressed as a decimal. 0.10 = 10% means you expect your portfolio value to typically move within +/-10% per year. Higher = more risk and potential reward."
    },

    # Risk Limits
    "SINGLE_INSTRUMENT_CAP": {
        "value_type": "float", "category": "risk", "min": 0.0, "max": 1.0,
        "description": "Max % in any single stock",
        "tooltip": "Prevents putting too many eggs in one basket. 0.35 = 35% means no single stock can be more than 35% of your portfolio, even if the system really likes it."
    },
    "GROSS_EXPOSURE_CAP": {
        "value_type": "float", "category": "risk", "min": 0.0, "max": 5.0,
        "description": "Maximum total market exposure",
        "tooltip": "Limits how much total money is at risk. 1.0 = 100% (fully invested), 1.5 = 150% (using some leverage/borrowed money). Values over 1.0 amplify both gains and losses."
    },
    "DRAWDOWN_THRESHOLD": {
        "value_type": "float", "category": "risk", "min": 0.0, "max": 1.0,
        "description": "Loss level that triggers safety mode",
        "tooltip": "If your portfolio drops by this much from its peak, the system automatically reduces positions. 0.10 = 10% means if you're down 10%, safety measures kick in to prevent larger losses."
    },
    "DRAWDOWN_SCALE_FACTOR": {
        "value_type": "float", "category": "risk", "min": 0.0, "max": 1.0,
        "description": "How much to reduce when in safety mode",
        "tooltip": "When the drawdown threshold is hit, positions are multiplied by this factor. 0.50 = 50% means all positions are cut in half to reduce risk during bad times."
    },

    # Trend Confirmation
    "CONFIRMATION_ENABLED": {
        "value_type": "bool", "category": "confirmation",
        "description": "Require extra proof before trading",
        "tooltip": "When enabled, the system needs additional evidence that a trend is real before buying or selling. Reduces false signals but may enter trades later."
    },
    "CONFIRMATION_TYPE": {
        "value_type": "str", "category": "confirmation", "options": ["donchian", "dual_ma", "both"],
        "description": "Method to confirm trends",
        "tooltip": "Donchian: confirms when price hits new highs/lows. Dual MA: confirms when short-term average crosses long-term average. Both: requires both methods to agree (most conservative)."
    },
    "DONCHIAN_PERIOD": {
        "value_type": "int", "category": "confirmation", "min": 1, "max": 500,
        "description": "Days for price channel",
        "tooltip": "Donchian channels track the highest high and lowest low over this many days. 20 days is common. A breakout above/below these levels confirms the trend."
    },
    "MA_FAST_PERIOD": {
        "value_type": "int", "category": "confirmation", "min": 1, "max": 500,
        "description": "Short-term average period",
        "tooltip": "The 'fast' moving average responds quickly to price changes. When it crosses above the slow average, it suggests an uptrend. 50 days is a common choice."
    },
    "MA_SLOW_PERIOD": {
        "value_type": "int", "category": "confirmation", "min": 1, "max": 500,
        "description": "Long-term average period",
        "tooltip": "The 'slow' moving average smooths out noise and shows the bigger picture. 200 days is the classic 'long-term trend' indicator used by many traders."
    },

    # Exit Rules
    "EXIT_RULES_ENABLED": {
        "value_type": "bool", "category": "exit",
        "description": "Use automatic exit triggers",
        "tooltip": "When enabled, positions can be closed automatically based on price movements, not just when the trend signal changes. Helps protect profits and limit losses."
    },
    "TRAILING_STOP_ATR_MULTIPLE": {
        "value_type": "float", "category": "exit", "min": 0.5, "max": 10.0,
        "description": "Profit protection distance",
        "tooltip": "Automatically sells if price drops this many ATRs (a measure of typical daily movement) from its peak. 3.0 means if a stock typically moves $1/day and drops $3 from its high, it's sold to protect profits."
    },
    "ATR_EXIT_MULTIPLE": {
        "value_type": "float", "category": "exit", "min": 0.5, "max": 10.0,
        "description": "Loss limit from entry",
        "tooltip": "Automatically exits if price moves this many ATRs against your entry price. 2.0 means if you buy at $100 and ATR is $2, you'd exit if it drops to $96. Limits losses on bad trades."
    },
    "ATR_PERIOD": {
        "value_type": "int", "category": "exit", "min": 1, "max": 100,
        "description": "Days to calculate typical movement",
        "tooltip": "ATR (Average True Range) measures how much a stock typically moves each day. This setting controls how many days to average. 14 days is standard."
    },
    "PERSISTENCE_DAYS": {
        "value_type": "int", "category": "exit", "min": 0, "max": 30,
        "description": "Days signal must hold before acting",
        "tooltip": "Prevents knee-jerk reactions by requiring a new signal to persist for this many days before acting. 3 days means the system waits to confirm the signal isn't just noise."
    },

    # Diversification
    "DIVERSIFICATION_ENABLED": {
        "value_type": "bool", "category": "diversification",
        "description": "Limit concentration by sector",
        "tooltip": "When enabled, prevents the portfolio from being too heavily weighted in one industry or type of asset. Spreads risk across different areas of the market."
    },
    "SECTOR_CAP": {
        "value_type": "float", "category": "diversification", "min": 0.0, "max": 1.0,
        "description": "Max % in any sector",
        "tooltip": "Limits exposure to any single sector (like Technology, Healthcare, etc.). 0.50 = 50% means no sector can be more than half your portfolio, even if many tech stocks are trending."
    },
    "ASSET_CLASS_CAP": {
        "value_type": "float", "category": "diversification", "min": 0.0, "max": 1.0,
        "description": "Max % in any asset class",
        "tooltip": "Limits exposure to asset types (stocks, bonds, commodities, etc.). 0.60 = 60% means you'll always have some diversification across different types of investments."
    },
    "CORRELATION_THROTTLE_ENABLED": {
        "value_type": "bool", "category": "diversification",
        "description": "Reduce similar-moving positions",
        "tooltip": "When enabled, if you already own stocks that move together (high correlation), the system will reduce the size of new positions in similar stocks. Prevents hidden concentration."
    },
    "CORRELATION_THRESHOLD": {
        "value_type": "float", "category": "diversification", "min": 0.0, "max": 1.0,
        "description": "Similarity level to trigger reduction",
        "tooltip": "Correlation ranges from -1 to 1. Stocks above this threshold are considered 'too similar'. 0.70 means if two stocks move together 70%+ of the time, new positions get reduced."
    },
    "CORRELATION_LOOKBACK": {
        "value_type": "int", "category": "diversification", "min": 5, "max": 252,
        "description": "Days to measure similarity",
        "tooltip": "How many days of price history to use when calculating if stocks move together. 60 days captures recent relationships without being too noisy."
    },
    "CORRELATION_SCALE_FACTOR": {
        "value_type": "float", "category": "diversification", "min": 0.0, "max": 1.0,
        "description": "Size reduction for similar stocks",
        "tooltip": "When correlation throttle triggers, new position sizes are multiplied by this factor. 0.50 = 50% means you only take half the normal position in highly correlated stocks."
    },

    # Sizing
    "FRACTIONAL_SIZING_ENABLED": {
        "value_type": "bool", "category": "sizing",
        "description": "Allow buying partial shares",
        "tooltip": "When enabled, you can buy 2.5 shares instead of rounding to 2 or 3. This allows more precise position sizing, especially important for expensive stocks or small accounts."
    },
    "FRACTIONAL_DECIMALS": {
        "value_type": "int", "category": "sizing", "min": 0, "max": 8,
        "description": "Decimal places for share quantities",
        "tooltip": "How precisely to calculate share amounts. 4 decimals means you could buy 10.2537 shares. More decimals = more precision but check if your broker supports it."
    },
    "MIN_NOTIONAL_USD": {
        "value_type": "float", "category": "sizing", "min": 0.0, "max": 10000.0,
        "description": "Smallest trade size in dollars",
        "tooltip": "Trades smaller than this are skipped to avoid excessive fees or broker minimums. $50 is typical. Trades below this threshold won't be placed."
    },
    "MIN_NOTIONAL_MODE": {
        "value_type": "str", "category": "sizing", "options": ["fixed", "nav_scaled", "liquidity_scaled"],
        "description": "How to calculate minimum trade",
        "tooltip": "Fixed: always use MIN_NOTIONAL_USD. NAV Scaled: minimum grows with your portfolio size. Liquidity Scaled: minimum based on how easily the stock trades."
    },
    "MIN_NOTIONAL_NAV_BPS": {
        "value_type": "float", "category": "sizing", "min": 0.0, "max": 100.0,
        "description": "Min trade as % of portfolio (bps)",
        "tooltip": "When using NAV Scaled mode, this sets the minimum trade as basis points (1/100th of a percent) of portfolio value. 5 bps on a $100K portfolio = $50 minimum."
    },
    "ALLOW_SHORT_SELLING": {
        "value_type": "bool", "category": "sizing",
        "description": "Allow betting against stocks",
        "tooltip": "When enabled, the system can 'short sell' - profiting when stocks go down. This allows making money in falling markets but adds complexity and risk. Disable for long-only strategy."
    },
}


class ConfigService:
    """
    Service for managing strategy configuration.

    DB values take precedence over environment variables.
    On startup, missing keys are seeded from .env/defaults.
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def get_all(self) -> List[StrategyConfig]:
        """Get all configuration entries."""
        async with self._get_session() as session:
            stmt = select(StrategyConfig).order_by(StrategyConfig.category, StrategyConfig.key)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_by_category(self, category: str) -> List[StrategyConfig]:
        """Get configuration entries by category."""
        async with self._get_session() as session:
            stmt = (
                select(StrategyConfig)
                .where(StrategyConfig.category == category)
                .order_by(StrategyConfig.key)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get(self, key: str) -> Optional[StrategyConfig]:
        """Get a single configuration entry by key."""
        async with self._get_session() as session:
            stmt = select(StrategyConfig).where(StrategyConfig.key == key)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update(self, key: str, value: str) -> Optional[StrategyConfig]:
        """
        Update a configuration value.

        Args:
            key: Configuration key
            value: New value as string

        Returns:
            Updated StrategyConfig or None if key doesn't exist

        Raises:
            ValueError: If value fails validation
        """
        # Validate the value
        if key in TRADING_PARAMS:
            self._validate_value(key, value, TRADING_PARAMS[key])

        async with self._get_session() as session:
            stmt = (
                update(StrategyConfig)
                .where(StrategyConfig.key == key)
                .values(value=value, updated_at=func.now())
                .returning(StrategyConfig)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                logger.info("Config updated: %s = %s", key, value)
            return row

    async def bulk_update(self, updates: Dict[str, str]) -> List[StrategyConfig]:
        """
        Update multiple configuration values.

        Args:
            updates: Dict of key -> value pairs

        Returns:
            List of updated StrategyConfig entries
        """
        # Validate all values first
        for key, value in updates.items():
            if key in TRADING_PARAMS:
                self._validate_value(key, value, TRADING_PARAMS[key])

        async with self._get_session() as session:
            updated = []
            for key, value in updates.items():
                stmt = (
                    update(StrategyConfig)
                    .where(StrategyConfig.key == key)
                    .values(value=value, updated_at=func.now())
                    .returning(StrategyConfig)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row:
                    updated.append(row)
                    logger.info("Config updated: %s = %s", key, value)
            return updated

    async def get_categories(self) -> List[str]:
        """Get list of unique categories."""
        async with self._get_session() as session:
            stmt = select(func.distinct(StrategyConfig.category)).order_by(StrategyConfig.category)
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]

    async def seed_missing_configs(self) -> int:
        """
        Seed database with missing configuration entries from environment.

        Called on application startup to ensure all trading parameters exist in DB.

        Returns:
            Number of entries seeded
        """
        async with self._get_session() as session:
            seeded = 0
            for key, metadata in TRADING_PARAMS.items():
                # Check if key exists
                stmt = select(StrategyConfig).where(StrategyConfig.key == key)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing is None:
                    # Get value from settings
                    env_value = getattr(settings, key, None)
                    if env_value is None:
                        logger.warning("Config key %s not found in settings, skipping", key)
                        continue

                    # Convert to string
                    value = str(env_value)
                    if metadata["value_type"] == "bool":
                        value = value.lower()

                    # Insert
                    config = StrategyConfig(
                        key=key,
                        value=value,
                        value_type=metadata["value_type"],
                        category=metadata["category"],
                        description=metadata["description"],
                    )
                    session.add(config)
                    seeded += 1
                    logger.info("Seeded config: %s = %s", key, value)

            if seeded > 0:
                await session.flush()
            return seeded

    async def get_value(self, key: str) -> Any:
        """
        Get a configuration value with type conversion.

        DB value takes precedence over environment variable.

        Args:
            key: Configuration key

        Returns:
            Typed configuration value
        """
        # Try DB first
        config = await self.get(key)
        if config is not None:
            return self._convert_value(config.value, config.value_type)

        # Fall back to settings
        return getattr(settings, key, None)

    def _convert_value(self, value: str, value_type: str) -> Any:
        """Convert string value to appropriate type."""
        if value_type == "int":
            return int(value)
        elif value_type == "float":
            return float(value)
        elif value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        else:
            return value

    def _validate_value(self, key: str, value: str, metadata: Dict[str, Any]) -> None:
        """
        Validate a configuration value.

        Raises:
            ValueError: If validation fails
        """
        value_type = metadata["value_type"]

        try:
            if value_type == "int":
                int_val = int(value)
                if "min" in metadata and int_val < metadata["min"]:
                    raise ValueError(f"{key} must be >= {metadata['min']}")
                if "max" in metadata and int_val > metadata["max"]:
                    raise ValueError(f"{key} must be <= {metadata['max']}")

            elif value_type == "float":
                float_val = float(value)
                if "min" in metadata and float_val < metadata["min"]:
                    raise ValueError(f"{key} must be >= {metadata['min']}")
                if "max" in metadata and float_val > metadata["max"]:
                    raise ValueError(f"{key} must be <= {metadata['max']}")

            elif value_type == "bool":
                if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                    raise ValueError(f"{key} must be a boolean value")

            elif value_type == "str":
                if "options" in metadata and value not in metadata["options"]:
                    raise ValueError(f"{key} must be one of: {metadata['options']}")

        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Invalid value for {key}: {e}")

    @asynccontextmanager
    async def _get_session(self):
        """Get database session, using provided one or creating new."""
        if self.session is not None:
            yield self.session
        else:
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise


# Global instance for convenience
config_service = ConfigService()
