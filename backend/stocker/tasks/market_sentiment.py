from datetime import date
import asyncio
import logging

from stocker.core.config import settings
from stocker.scheduler.celery_app import app
from stocker.services.market_sentiment_service import MarketSentimentService
from stocker.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


@app.task(name="stocker.tasks.market_sentiment.ingest_market_sentiment")
def ingest_market_sentiment() -> dict[str, object]:
    """Scheduled task to ingest symbol-level market sentiment."""
    processed, symbol_count, as_of_date = asyncio.run(_ingest_market_sentiment_async())

    if processed:
        logger.info(
            "Ingested %s sentiment rows for %s symbols",
            processed,
            symbol_count,
        )
    else:
        logger.warning("No market sentiment ingested")

    return {
        "status": "completed",
        "processed": processed,
        "date": str(as_of_date),
        "symbols": symbol_count,
    }


async def _ingest_market_sentiment_async() -> tuple[int, int, date]:
    service = MarketSentimentService(provider_name=settings.SENTIMENT_PROVIDER)
    as_of_date = date.today()
    universe_service = UniverseService()
    universe = await universe_service.get_global_symbols()

    processed = await service.fetch_and_store_sentiment(
        universe,
        as_of_date=as_of_date,
        window_days=settings.SENTIMENT_LOOKBACK_DAYS,
        period=settings.SENTIMENT_PERIOD,
        only_missing=settings.SENTIMENT_ONLY_MISSING,
    )

    return processed, len(universe), as_of_date
