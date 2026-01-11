import asyncio
import logging
from datetime import date
from typing import Dict, Any

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.redis import StreamNames
from stocker.services.derived_metrics_service import DerivedMetricsService
from stocker.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


class DerivedMetricsConsumer(BaseStreamConsumer):
    """
    Listens for market-bars batch events.
    Computes derived metrics for the latest market date.
    """

    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.MARKET_BARS,
            consumer_group="derived-metrics",
        )
        self.service = DerivedMetricsService()

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        event_type = data.get("event_type")
        if event_type != "batch_complete":
            return

        date_str = data.get("date")
        symbols_str = data.get("symbols", "")
        if not date_str:
            logger.warning("Derived metrics batch missing date")
            return

        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            logger.error(f"Invalid date format for derived metrics: {date_str}")
            return

        if settings.DERIVED_METRICS_USE_GLOBAL_UNIVERSE:
            symbols = await UniverseService().get_global_symbols()
        else:
            symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]

        if not symbols:
            logger.warning("No symbols available for derived metrics computation")
            return

        processed = await self.service.compute_and_store(symbols=symbols, as_of_date=target_date)
        logger.info("Derived metrics computed for %s symbols on %s", len(symbols), target_date)

        if self.redis:
            await self.redis.xadd(
                StreamNames.DERIVED_METRICS,
                {
                    "event_type": "derived_metrics_complete",
                    "date": target_date.isoformat(),
                    "symbols": str(len(symbols)),
                    "processed": str(processed),
                },
            )


if __name__ == "__main__":
    async def main():
        consumer = DerivedMetricsConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()

    asyncio.run(main())
