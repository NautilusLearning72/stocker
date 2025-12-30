import logging
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.daily_bar import DailyBar
from stocker.models.trading_universe import TradingUniverse

logger = logging.getLogger(__name__)


class TradingUniverseService:
    """Builds and retrieves the dynamic trading universe (legacy/suggestions)."""

    def __init__(self, source: str | None = None):
        self.source = source or settings.UNIVERSE_SOURCE

    async def refresh_universe(self, as_of_date: date | None = None) -> int:
        target_date = as_of_date or date.today()
        start_date = target_date - timedelta(days=settings.UNIVERSE_LOOKBACK_DAYS)
        universe_size = settings.UNIVERSE_SIZE

        async with AsyncSessionLocal() as session:
            if self.source == "alpaca_most_actives":
                records = self._build_from_alpaca(target_date, universe_size)
            else:
                rows = await self._fetch_from_prices(
                    session,
                    start_date,
                    target_date,
                    universe_size,
                )
                records = self._build_from_prices(rows, target_date)

            if not records:
                logger.warning(
                    "No universe records available for %s (source=%s)",
                    target_date,
                    self.source,
                )
                return 0

            insert_stmt = insert(TradingUniverse).values(records)
            insert_stmt = insert_stmt.on_conflict_do_update(
                constraint="uq_trading_universe_date_symbol_source",
                set_=self._build_update_map(insert_stmt),
            )

            try:
                await session.execute(insert_stmt)
                await session.commit()
                logger.info(
                    "Refreshed trading universe with %s symbols for %s",
                    len(records),
                    target_date,
                )
                return len(records)
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to refresh trading universe: %s", exc)
                return 0

    async def get_universe_symbols(self, as_of_date: date | None = None) -> list[str]:
        if not settings.USE_DYNAMIC_UNIVERSE:
            return settings.TRADING_UNIVERSE

        target_date = as_of_date or date.today()
        async with AsyncSessionLocal() as session:
            latest_stmt = (
                select(func.max(TradingUniverse.as_of_date))
                .where(TradingUniverse.as_of_date <= target_date)
                .where(TradingUniverse.source == self.source)
            )
            result = await session.execute(latest_stmt)
            latest_date = result.scalar_one_or_none()

            if latest_date is None:
                logger.warning(
                    "Dynamic universe unavailable; falling back to static list"
                )
                return settings.TRADING_UNIVERSE

            symbols_stmt = (
                select(TradingUniverse.symbol)
                .where(TradingUniverse.as_of_date == latest_date)
                .where(TradingUniverse.source == self.source)
                .order_by(TradingUniverse.rank.asc())
            )
            result = await session.execute(symbols_stmt)
            symbols = [row[0] for row in result.all()]
            if not symbols:
                logger.warning(
                    "Dynamic universe is empty for %s; falling back to static list",
                    latest_date,
                )
                return settings.TRADING_UNIVERSE
            return symbols

    async def _fetch_from_prices(
        self,
        session: AsyncSessionLocal,
        start_date: date,
        end_date: date,
        universe_size: int,
    ) -> list[tuple[str, float]]:
        avg_dollar_volume = func.avg(DailyBar.close * DailyBar.volume)
        stmt = (
            select(
                DailyBar.symbol,
                avg_dollar_volume.label("avg_dollar_volume"),
            )
            .where(
                DailyBar.date >= start_date,
                DailyBar.date <= end_date,
            )
            .group_by(DailyBar.symbol)
            .order_by(desc(avg_dollar_volume))
            .limit(universe_size)
        )

        result = await session.execute(stmt)
        return result.all()

    def _build_from_prices(
        self,
        rows: Iterable[tuple[str, float]],
        target_date: date,
    ) -> list[dict[str, Any]]:
        records = [
            {
                "as_of_date": target_date,
                "symbol": symbol,
                "rank": idx + 1,
                "avg_dollar_volume": avg_volume,
                "source": self.source,
                "lookback_days": settings.UNIVERSE_LOOKBACK_DAYS,
            }
            for idx, (symbol, avg_volume) in enumerate(rows)
        ]
        return records

    def _build_from_alpaca(self, target_date: date, universe_size: int) -> list[dict[str, Any]]:
        if not settings.ALPACA_API_KEY or not settings.ALPACA_SECRET_KEY:
            logger.error("Alpaca credentials not set; cannot fetch most actives")
            return []

        try:
            from alpaca.data.enums import MostActivesBy
            from alpaca.data.historical import ScreenerClient
            from alpaca.data.requests import MostActivesRequest
        except Exception as exc:
            logger.error("Alpaca screener unavailable: %s", exc)
            return []

        max_top = settings.UNIVERSE_SCREENER_MAX
        top = min(universe_size, max_top)
        if universe_size > max_top:
            logger.warning(
                "Alpaca most-actives supports max %s; requested %s. Capping.",
                max_top,
                universe_size,
            )

        screener = ScreenerClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
        )
        by_value = settings.UNIVERSE_SCREENER_BY.lower()
        by = MostActivesBy.TRADES if by_value == "trades" else MostActivesBy.VOLUME

        try:
            response = screener.get_most_actives(
                MostActivesRequest(top=top, by=by)
            )
        except Exception as exc:
            logger.error("Alpaca most-actives fetch failed: %s", exc)
            return []
        actives = self._extract_actives(response)
        if not actives:
            return []

        symbols = [active["symbol"] for active in actives]
        snapshot_map = self._fetch_snapshots(symbols)

        records: list[dict[str, Any]] = []
        for idx, active in enumerate(actives):
            symbol = active["symbol"]
            dollar_volume = self._snapshot_dollar_volume(snapshot_map.get(symbol))
            records.append(
                {
                    "as_of_date": target_date,
                    "symbol": symbol,
                    "rank": idx + 1,
                    "avg_dollar_volume": dollar_volume,
                    "source": self.source,
                    "lookback_days": 1,
                }
            )
        return records

    def _extract_actives(self, response: Any) -> list[dict[str, Any]]:
        if isinstance(response, dict):
            raw = response.get("most_actives") or response.get("mostActives") or []
        else:
            raw = getattr(response, "most_actives", [])

        actives: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                symbol = item.get("symbol")
                volume = item.get("volume")
                trade_count = item.get("trade_count") or item.get("tradeCount")
            else:
                symbol = getattr(item, "symbol", None)
                volume = getattr(item, "volume", None)
                trade_count = getattr(item, "trade_count", None)

            if not symbol:
                continue
            actives.append(
                {
                    "symbol": symbol,
                    "volume": volume,
                    "trade_count": trade_count,
                }
            )
        return actives

    def _fetch_snapshots(self, symbols: list[str]) -> dict[str, Any]:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockSnapshotRequest
        except Exception as exc:
            logger.warning("Alpaca snapshot unavailable: %s", exc)
            return {}

        if not symbols:
            return {}

        client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
        )
        try:
            return client.get_stock_snapshot(
                StockSnapshotRequest(symbol_or_symbols=symbols)
            )
        except Exception as exc:
            logger.warning("Failed to fetch Alpaca snapshots: %s", exc)
            return {}

    def _snapshot_dollar_volume(self, snapshot: Any) -> float | None:
        if snapshot is None:
            return None

        if isinstance(snapshot, dict):
            bar = (
                snapshot.get("daily_bar")
                or snapshot.get("dailyBar")
                or snapshot.get("previous_daily_bar")
                or snapshot.get("previousDailyBar")
            )
            if isinstance(bar, dict):
                try:
                    close = float(bar.get("close"))
                    volume = float(bar.get("volume"))
                except (TypeError, ValueError):
                    return None
            else:
                return None
        else:
            bar = getattr(snapshot, "daily_bar", None) or getattr(
                snapshot, "previous_daily_bar", None
            )
            if bar is None:
                return None

            try:
                close = float(bar.close)
                volume = float(bar.volume)
            except (TypeError, ValueError):
                return None

        if volume <= 0 or close <= 0:
            return None
        return close * volume

    def _build_update_map(self, stmt: Any) -> dict[str, Any]:
        excluded = stmt.excluded
        skip = {"id", "as_of_date", "symbol", "source", "created_at"}
        update_map = {
            column.name: getattr(excluded, column.name)
            for column in TradingUniverse.__table__.columns
            if column.name not in skip and column.name != "updated_at"
        }
        update_map["updated_at"] = excluded.created_at
        return update_map
