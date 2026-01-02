import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.future import select

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames, get_redis
from stocker.models.daily_bar import DailyBar
from stocker.scheduler.celery_app import app
from stocker.services.market_data_service import MarketDataService
from stocker.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


async def _get_latest_market_date() -> date:
    """Query database for the latest market data date available."""
    async with AsyncSessionLocal() as session:
        stmt = select(func.max(DailyBar.date))
        result = await session.execute(stmt)
        latest_date = result.scalar()
        return latest_date if latest_date else date.today()


async def _ingest_market_data_async():
    """Async implementation of market data ingestion."""
    service = MarketDataService(provider_name="yfinance")

    # Fetch last 3 days to catch up any missing/corrections
    today = date.today()
    start_date = today - timedelta(days=3)

    universe_service = UniverseService()
    universe = await universe_service.get_symbols_for_strategy(settings.DEFAULT_STRATEGY_ID)

    # Run the async service call
    processed, alerts = await service.fetch_and_store_daily_bars(universe, start_date, today)

    # Determine actual latest market date from stored data (not today's date)
    # This handles weekends, holidays, and cases where market hasn't closed yet
    latest_market_date = await _get_latest_market_date()

    return universe, processed, alerts, latest_market_date


@app.task(name="stocker.tasks.market_data.ingest_market_data")
def ingest_market_data():
    """
    Scheduled task to ingest daily market data.
    Runs after market close.
    Implements TDD data quality validation.
    """
    # Run all async operations in a single event loop
    universe, processed, alerts, latest_market_date = asyncio.run(_ingest_market_data_async())

    # Log results
    if processed > 0:
        logger.info(f"Ingested {processed} daily bars for {len(universe)} symbols, latest date: {latest_market_date}")

        # Publish to market-bars stream for downstream consumers
        # Use actual latest market date (not today) to handle weekends/holidays
        try:
            r = get_redis()
            r.xadd(StreamNames.MARKET_BARS, {
                "event_type": "batch_complete",
                "date": str(latest_market_date),
                "symbols": ",".join(universe),
                "count": str(processed)
            })
        except Exception as e:
            logger.error(f"Failed to publish stream event: {e}")

    # Handle data quality alerts
    alert_count = len(alerts)
    error_alerts = [a for a in alerts if a.severity == "ERROR"]

    if error_alerts:
        logger.error(f"Data quality ERRORS detected: {len(error_alerts)}")
        # Publish alerts to Redis for monitor consumer
        try:
            r = get_redis()
            r.xadd(StreamNames.ALERTS, {
                "level": "ERROR",
                "title": "Data Quality Issues",
                "message": f"{len(error_alerts)} data quality errors during ingestion"
            })
        except Exception as e:
            logger.error(f"Failed to publish alert: {e}")

    return {
        "status": "completed",
        "processed": processed,
        "date": str(latest_market_date),
        "alerts": alert_count,
        "errors": len(error_alerts)
    }
