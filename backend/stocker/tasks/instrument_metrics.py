from datetime import date
import asyncio
import logging

from stocker.core.config import settings
from stocker.scheduler.celery_app import app
from stocker.services.instrument_metrics_service import InstrumentMetricsService
from stocker.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


@app.task(name="stocker.tasks.instrument_metrics.ingest_instrument_metrics")
def ingest_instrument_metrics() -> dict[str, object]:
    """Scheduled task to ingest investor-facing instrument metrics."""
    processed, symbol_count, as_of_date = asyncio.run(_ingest_instrument_metrics_async())

    if processed:
        logger.info(
            "Ingested %s instrument metrics rows for %s symbols",
            processed,
            symbol_count,
        )
    else:
        logger.warning("No instrument metrics ingested")

    return {
        "status": "completed",
        "processed": processed,
        "date": str(as_of_date),
        "symbols": symbol_count,
    }


async def _ingest_instrument_metrics_async() -> tuple[int, int, date]:
    service = InstrumentMetricsService(provider_name=settings.FUNDAMENTALS_PROVIDER)
    as_of_date = date.today()
    universe_service = UniverseService()
    universe = await universe_service.get_all_symbols()

    processed = await service.fetch_and_store_metrics(universe, as_of_date=as_of_date)

    return processed, len(universe), as_of_date
