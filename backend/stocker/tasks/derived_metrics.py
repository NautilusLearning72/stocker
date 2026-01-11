import asyncio
import logging
from datetime import date
from typing import Optional

from stocker.scheduler.celery_app import app
from stocker.services.derived_metrics_service import DerivedMetricsService
from stocker.services.derived_metric_score_service import DerivedMetricScoreService

logger = logging.getLogger(__name__)


async def _ingest_derived_metrics_async(target_date: Optional[date]) -> int:
    service = DerivedMetricsService()
    return await service.compute_and_store(as_of_date=target_date)


@app.task(name="stocker.tasks.derived_metrics.ingest_derived_metrics")
def ingest_derived_metrics(as_of_date: str | None = None) -> dict[str, object]:
    """Scheduled task to compute derived metrics for the global universe."""
    target_date = date.fromisoformat(as_of_date) if as_of_date else None
    processed = asyncio.run(_ingest_derived_metrics_async(target_date))
    logger.info("Derived metrics ingested for %s", as_of_date or "latest")
    return {"status": "completed", "processed": processed, "date": str(as_of_date or date.today())}


async def _compute_metric_scores_async(target_date: Optional[date]) -> int:
    service = DerivedMetricScoreService()
    return await service.compute_scores(as_of_date=target_date)


@app.task(name="stocker.tasks.derived_metrics.compute_metric_scores")
def compute_metric_scores(as_of_date: str | None = None) -> dict[str, object]:
    """Scheduled task to compute consolidated metric scores."""
    target_date = date.fromisoformat(as_of_date) if as_of_date else None
    processed = asyncio.run(_compute_metric_scores_async(target_date))
    logger.info("Derived metric scores computed for %s", as_of_date or "latest")
    return {"status": "completed", "processed": processed, "date": str(as_of_date or date.today())}
