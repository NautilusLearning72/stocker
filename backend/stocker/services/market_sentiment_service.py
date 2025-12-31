import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.instrument_info import InstrumentInfo
from stocker.models.market_sentiment import MarketSentiment
from stocker.services.sentiment import get_sentiment_provider

logger = logging.getLogger(__name__)


class MarketSentimentService:
    """Service to fetch and store symbol-level market sentiment."""

    def __init__(self, provider_name: str = "gdelt"):
        self.provider = get_sentiment_provider(provider_name)
        self.provider_name = provider_name

    async def fetch_and_store_sentiment(
        self,
        symbols: list[str],
        as_of_date: date | None = None,
        window_days: int | None = None,
        period: str | None = None,
        only_missing: bool = False,
    ) -> int:
        if not symbols:
            return 0

        target_date = as_of_date or date.today()
        window = window_days or settings.SENTIMENT_LOOKBACK_DAYS
        period_value = period or settings.SENTIMENT_PERIOD
        symbols = self._normalize_symbols(symbols)

        if only_missing:
            async with AsyncSessionLocal() as session:
                existing = await self._load_existing_symbols(
                    session,
                    target_date,
                    self.provider_name,
                    period_value,
                    window,
                )
            symbols = [sym for sym in symbols if sym not in existing]

        if not symbols:
            return 0

        if settings.SENTIMENT_MAX_SYMBOLS and len(symbols) > settings.SENTIMENT_MAX_SYMBOLS:
            symbols = symbols[: settings.SENTIMENT_MAX_SYMBOLS]

        async with AsyncSessionLocal() as session:
            symbol_names = await self._load_symbol_names(session, symbols)

        records = await self.provider.fetch_market_sentiment(
            symbols=symbols,
            as_of_date=target_date,
            window_days=window,
            period=period_value,
            symbol_names=symbol_names,
        )

        if not records:
            logger.warning("No market sentiment returned from provider")
            return 0

        async with AsyncSessionLocal() as session:
            stmt = insert(MarketSentiment).values(records)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_market_sentiment_symbol_date_source_period",
                set_=self._build_update_map(stmt),
            )
            try:
                await session.execute(stmt)
                await session.commit()
                logger.info("Upserted %s market sentiment rows", len(records))
                return len(records)
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to store market sentiment: %s", exc)
                return 0

    async def _load_symbol_names(
        self, session, symbols: list[str]
    ) -> dict[str, str]:
        stmt = select(InstrumentInfo.symbol, InstrumentInfo.name).where(
            InstrumentInfo.symbol.in_(symbols)
        )
        result = await session.execute(stmt)
        return {row[0]: row[1] for row in result.all() if row[1]}

    async def _load_existing_symbols(
        self,
        session,
        target_date: date,
        source: str,
        period: str,
        window_days: int,
    ) -> set[str]:
        stmt = (
            select(MarketSentiment.symbol)
            .where(
                MarketSentiment.date == target_date,
                MarketSentiment.source == source,
                MarketSentiment.period == period,
                MarketSentiment.window_days == window_days,
                MarketSentiment.symbol.is_not(None),
            )
            .distinct()
        )
        result = await session.execute(stmt)
        return {row[0] for row in result.all() if row[0]}

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        seen = set()
        normalized: list[str] = []
        for sym in symbols:
            if sym is None:
                continue
            value = sym.strip().upper()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _build_update_map(self, stmt: Any) -> dict[str, Any]:
        excluded = stmt.excluded
        skip = {"id", "symbol", "date", "source", "period", "window_days", "created_at"}
        update_map = {
            column.name: getattr(excluded, column.name)
            for column in MarketSentiment.__table__.columns
            if column.name not in skip and column.name != "updated_at"
        }
        update_map["updated_at"] = excluded.created_at
        return update_map
