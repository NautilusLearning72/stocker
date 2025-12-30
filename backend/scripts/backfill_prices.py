#!/usr/bin/env python3
"""
Backfill historical price data for the trading universe.

Usage:
    python scripts/backfill_prices.py [--days 200]
"""

import asyncio
import logging
import os
import sys
from datetime import date, timedelta
from argparse import ArgumentParser

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from stocker.core.config import settings
from stocker.services.market_data_service import MarketDataService
from stocker.services.universe_service import UniverseService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def backfill_prices(days: int = 200):
    """Backfill historical price data."""
    logger.info(f"Starting backfill for {days} days of historical data")

    # Get trading universe
    universe_service = UniverseService()
    universe = await universe_service.get_symbols_for_strategy(
        settings.DEFAULT_STRATEGY_ID
    )

    logger.info(f"Universe: {universe}")

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    logger.info(f"Fetching data from {start_date} to {end_date}")

    # Initialize market data service with yfinance
    service = MarketDataService(provider_name="yfinance")

    # Fetch and store data
    try:
        processed, alerts = await service.fetch_and_store_daily_bars(
            symbols=universe,
            start_date=start_date,
            end_date=end_date
        )

        logger.info(f"Successfully processed {processed} bars")

        # Report alerts
        if alerts:
            warnings = [a for a in alerts if a.severity == "WARNING"]
            errors = [a for a in alerts if a.severity == "ERROR"]

            if warnings:
                logger.warning(f"Data quality warnings: {len(warnings)}")
                for alert in warnings[:5]:  # Show first 5
                    logger.warning(f"  {alert.symbol} ({alert.date}): {alert.message}")

            if errors:
                logger.error(f"Data quality errors: {len(errors)}")
                for alert in errors[:5]:  # Show first 5
                    logger.error(f"  {alert.symbol} ({alert.date}): {alert.message}")

        return processed

    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        return 0


def main():
    parser = ArgumentParser(description="Backfill historical price data")
    parser.add_argument(
        "--days",
        type=int,
        default=200,
        help="Number of days to backfill (default: 200)"
    )
    args = parser.parse_args()

    result = asyncio.run(backfill_prices(days=args.days))

    if result > 0:
        logger.info(f"✓ Backfill completed successfully: {result} bars")
        sys.exit(0)
    else:
        logger.error("✗ Backfill failed or no data processed")
        sys.exit(1)


if __name__ == "__main__":
    main()
