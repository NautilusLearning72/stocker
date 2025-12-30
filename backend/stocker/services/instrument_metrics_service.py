import logging
from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from stocker.core.database import AsyncSessionLocal
from stocker.models.instrument_metrics import InstrumentMetrics
from stocker.models.instrument_info import InstrumentInfo
from stocker.services.fundamentals import get_fundamentals_provider

logger = logging.getLogger(__name__)


class InstrumentMetricsService:
    """Service to fetch and store investor-facing fundamentals and valuation metrics."""

    def __init__(self, provider_name: str = "yfinance"):
        self.provider = get_fundamentals_provider(provider_name)
        self.provider_name = provider_name

    async def fetch_and_store_metrics(
        self,
        symbols: list[str],
        as_of_date: date | None = None,
    ) -> int:
        if not symbols:
            return 0

        target_date = as_of_date or date.today()
        metrics_records, info_records = self.provider.fetch_instrument_metrics(symbols, target_date)

        if not metrics_records and not info_records:
            logger.warning("No instrument metrics returned from provider")
            return 0

        async with AsyncSessionLocal() as session:
            if info_records:
                await self._upsert_instrument_info(session, info_records)

            stmt = insert(InstrumentMetrics).values(metrics_records)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_instrument_metrics_symbol_date_period_source",
                set_=self._build_update_map(stmt),
            )

            try:
                await session.execute(stmt)
                await session.commit()
                logger.info("Upserted %s instrument metrics rows", len(metrics_records))
                return len(metrics_records)
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to store instrument metrics: %s", exc)
                return 0

    def _build_update_map(self, stmt: Any) -> dict[str, Any]:
        excluded = stmt.excluded
        skip = {"id", "symbol", "as_of_date", "period_type", "source", "created_at"}
        update_map = {
            column.name: getattr(excluded, column.name)
            for column in InstrumentMetrics.__table__.columns
            if column.name not in skip and column.name != "updated_at"
        }
        update_map["updated_at"] = excluded.created_at
        return update_map

    async def _upsert_instrument_info(self, session, records: list[dict[str, Any]]) -> None:
        stmt = insert(InstrumentInfo).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol"],
            set_={
                "name": stmt.excluded.name,
                "asset_class": stmt.excluded.asset_class,
                "sector": stmt.excluded.sector,
                "industry": stmt.excluded.industry,
                "exchange": stmt.excluded.exchange,
                "currency": stmt.excluded.currency,
                "active": stmt.excluded.active,
                "updated_at": stmt.excluded.created_at,
            },
        )
        await session.execute(stmt)
