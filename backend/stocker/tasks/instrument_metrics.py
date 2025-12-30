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
    service = InstrumentMetricsService(provider_name=settings.FUNDAMENTALS_PROVIDER)
    as_of_date = date.today()
    universe_service = UniverseService()
    universe = asyncio.run(universe_service.get_all_symbols())

    processed = asyncio.run(
        service.fetch_and_store_metrics(universe, as_of_date=as_of_date)
    )

    if processed:
        logger.info(
            "Ingested %s instrument metrics rows for %s symbols",
            processed,
            len(universe),
        )
    else:
        logger.warning("No instrument metrics ingested")

    return {
        "status": "completed",
        "processed": processed,
        "date": str(as_of_date),
        "symbols": len(universe),
    }
