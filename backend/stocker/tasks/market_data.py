from stocker.scheduler.celery_app import app
from stocker.services.market_data_service import MarketDataService
from stocker.core.redis import get_redis, StreamNames
from stocker.core.config import settings
from stocker.services.universe_service import UniverseService
from datetime import date, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)


@app.task(name="stocker.tasks.market_data.ingest_market_data")
def ingest_market_data():
    """
    Scheduled task to ingest daily market data.
    Runs after market close.
    Implements TDD data quality validation.
    """
    service = MarketDataService(provider_name="yfinance")

    # Fetch last 3 days to catch up any missing/corrections
    today = date.today()
    start_date = today - timedelta(days=3)

    universe_service = UniverseService()
    universe = asyncio.run(
        universe_service.get_symbols_for_strategy(settings.DEFAULT_STRATEGY_ID)
    )

    # Run the async service call
    processed, alerts = asyncio.run(
        service.fetch_and_store_daily_bars(universe, start_date, today)
    )

    # Log results
    if processed > 0:
        logger.info(f"Ingested {processed} daily bars for {len(universe)} symbols")

        # Publish to market-bars stream for downstream consumers
        try:
            r = get_redis()
            r.xadd(StreamNames.MARKET_BARS, {
                "event_type": "batch_complete",
                "date": str(today),
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
        "date": str(today),
        "alerts": alert_count,
        "errors": len(error_alerts)
    }
