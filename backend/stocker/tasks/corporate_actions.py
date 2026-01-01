from datetime import date, timedelta
import asyncio
import logging

from stocker.core.config import settings
from stocker.scheduler.celery_app import app
from stocker.services.corporate_actions_service import CorporateActionsService
from stocker.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


@app.task(name="stocker.tasks.corporate_actions.ingest_corporate_actions")
def ingest_corporate_actions() -> dict[str, object]:
    """Scheduled task to ingest corporate actions."""
    processed, symbol_count, start_date, end_date = asyncio.run(_ingest_actions_async())

    if processed:
        logger.info(
            "Ingested %s corporate actions for %s symbols",
            processed,
            symbol_count,
        )
    else:
        logger.warning("No corporate actions ingested")

    return {
        "status": "completed",
        "processed": processed,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "symbols": symbol_count,
    }


async def _ingest_actions_async() -> tuple[int, int, date, date]:
    service = CorporateActionsService(provider_name=settings.CORP_ACTIONS_PROVIDER)
    universe_service = UniverseService()
    universe = await universe_service.get_global_symbols()

    end_date = date.today()
    start_date = end_date - timedelta(days=settings.CORP_ACTIONS_LOOKBACK_DAYS)

    processed = await service.fetch_and_store_actions(universe, start_date, end_date)
    return processed, len(universe), start_date, end_date
