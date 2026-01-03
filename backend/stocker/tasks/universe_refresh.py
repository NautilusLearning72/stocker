"""
Universe refresh task.

Refreshes the dynamic trading universe based on liquidity rankings.
Scheduled to run daily at UNIVERSE_REFRESH_HOUR.
"""
import asyncio
import logging
from datetime import date

from stocker.scheduler.celery_app import app
from stocker.services.trading_universe_service import TradingUniverseService
from stocker.core.config import settings

logger = logging.getLogger(__name__)


async def _refresh_universe_async(as_of_date: date) -> dict:
    """Async implementation of universe refresh."""
    service = TradingUniverseService()

    symbols = await service.refresh_universe(
        as_of_date=as_of_date,
        size=settings.UNIVERSE_SIZE,
        source=settings.UNIVERSE_SOURCE,
        lookback_days=settings.UNIVERSE_LOOKBACK_DAYS
    )

    return {
        "status": "ok",
        "as_of_date": str(as_of_date),
        "symbols": len(symbols),
        "source": settings.UNIVERSE_SOURCE,
        "size": settings.UNIVERSE_SIZE
    }


@app.task(name="stocker.tasks.universe_refresh.refresh_dynamic_universe")
def refresh_dynamic_universe() -> dict:
    """
    Refresh the dynamic trading universe.

    Fetches top N symbols by liquidity and stores in trading_universe table.
    Only runs when USE_DYNAMIC_UNIVERSE=true.
    """
    if not settings.USE_DYNAMIC_UNIVERSE:
        logger.info("Dynamic universe disabled, skipping refresh")
        return {"status": "skipped", "reason": "USE_DYNAMIC_UNIVERSE=false"}

    logger.info(f"Refreshing dynamic universe (size={settings.UNIVERSE_SIZE})")
    result = asyncio.run(_refresh_universe_async(date.today()))
    logger.info(f"Universe refresh complete: {result}")

    return result
