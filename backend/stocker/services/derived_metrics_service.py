from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.daily_bar import DailyBar
from stocker.models.instrument_metrics import InstrumentMetrics
from stocker.models.market_sentiment import MarketSentiment
from stocker.models.derived_metric_definition import DerivedMetricDefinition
from stocker.models.derived_metric_value import DerivedMetricValue
from stocker.strategy.derived_metrics_engine import DerivedMetricsEngine
from stocker.services.universe_service import UniverseService


METRIC_DEFINITIONS: list[dict[str, Any]] = [
    {
        "metric_key": "pe_ttm",
        "name": "P/E (TTM)",
        "category": "fundamental",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "pe_ttm",
        "description": "Trailing price-to-earnings ratio.",
    },
    {
        "metric_key": "pe_forward",
        "name": "P/E (Forward)",
        "category": "fundamental",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "pe_forward",
        "description": "Forward price-to-earnings ratio.",
    },
    {
        "metric_key": "peg_ratio",
        "name": "PEG Ratio",
        "category": "fundamental",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "peg_ratio",
    },
    {
        "metric_key": "ev_to_ebitda",
        "name": "EV/EBITDA",
        "category": "fundamental",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "ev_to_ebitda",
    },
    {
        "metric_key": "fcf_yield",
        "name": "Free Cash Flow Yield",
        "category": "fundamental",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "fcf_yield",
    },
    {
        "metric_key": "roe",
        "name": "Return on Equity",
        "category": "fundamental",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "roe",
    },
    {
        "metric_key": "roic",
        "name": "Return on Invested Capital",
        "category": "fundamental",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "roic",
    },
    {
        "metric_key": "debt_to_equity",
        "name": "Debt to Equity",
        "category": "fundamental",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "debt_to_equity",
    },
    {
        "metric_key": "beta",
        "name": "Beta",
        "category": "quant",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "beta",
    },
    {
        "metric_key": "book_to_market",
        "name": "Book-to-Market",
        "category": "quant",
        "unit": "ratio",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "price_to_book",
    },
    {
        "metric_key": "earnings_yield",
        "name": "Earnings Yield",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "pe_ttm",
    },
    {
        "metric_key": "cash_flow_yield",
        "name": "Cash Flow Yield",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "fcf_yield",
    },
    {
        "metric_key": "gross_profitability",
        "name": "Gross Profitability",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "source_table": "instrument_metrics",
        "source_field": "gross_margin",
    },
    {
        "metric_key": "leverage",
        "name": "Leverage",
        "category": "quant",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "instrument_metrics",
        "source_field": "debt_to_equity",
    },
    {
        "metric_key": "mom_1m",
        "name": "Momentum 1M",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 21,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "mom_3m",
        "name": "Momentum 3M",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 63,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "mom_6m",
        "name": "Momentum 6M",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 126,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "mom_12m",
        "name": "Momentum 12M",
        "category": "quant",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 252,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "vol_20d",
        "name": "Realized Volatility 20D",
        "category": "quant",
        "unit": "pct",
        "direction": "lower_is_better",
        "lookback_days": 20,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "atr_14",
        "name": "ATR 14",
        "category": "quant",
        "unit": "price",
        "direction": "lower_is_better",
        "lookback_days": 14,
        "source_table": "prices_daily",
        "source_field": "close",
    },
    {
        "metric_key": "sma_50",
        "name": "Price vs SMA 50",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 50,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "sma_200",
        "name": "Price vs SMA 200",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 200,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "ema_20",
        "name": "Price vs EMA 20",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 20,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "macd",
        "name": "MACD (normalized)",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 26,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "adx",
        "name": "ADX 14",
        "category": "technical",
        "unit": "index",
        "direction": "higher_is_better",
        "lookback_days": 14,
        "source_table": "prices_daily",
        "source_field": "close",
    },
    {
        "metric_key": "rsi_14",
        "name": "RSI 14",
        "category": "technical",
        "unit": "index",
        "direction": "higher_is_better",
        "lookback_days": 14,
        "source_table": "prices_daily",
        "source_field": "adj_close",
    },
    {
        "metric_key": "stoch_k",
        "name": "Stochastic %K",
        "category": "technical",
        "unit": "index",
        "direction": "higher_is_better",
        "lookback_days": 14,
        "source_table": "prices_daily",
        "source_field": "close",
    },
    {
        "metric_key": "stoch_d",
        "name": "Stochastic %D",
        "category": "technical",
        "unit": "index",
        "direction": "higher_is_better",
        "lookback_days": 14,
        "source_table": "prices_daily",
        "source_field": "close",
    },
    {
        "metric_key": "vwap_20",
        "name": "Price vs VWAP 20",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 20,
        "source_table": "prices_daily",
        "source_field": "close",
    },
    {
        "metric_key": "obv",
        "name": "OBV 20D Change",
        "category": "technical",
        "unit": "pct",
        "direction": "higher_is_better",
        "lookback_days": 20,
        "source_table": "prices_daily",
        "source_field": "volume",
    },
    {
        "metric_key": "sentiment_score",
        "name": "Sentiment Score",
        "category": "sentiment",
        "unit": "score",
        "direction": "higher_is_better",
        "source_table": "market_sentiment",
        "source_field": "sentiment_score",
    },
    {
        "metric_key": "sentiment_mom",
        "name": "Sentiment Momentum",
        "category": "sentiment",
        "unit": "score",
        "direction": "higher_is_better",
        "source_table": "market_sentiment",
        "source_field": "sentiment_score",
    },
    {
        "metric_key": "sentiment_vol",
        "name": "Sentiment Volatility",
        "category": "sentiment",
        "unit": "score",
        "direction": "lower_is_better",
        "source_table": "market_sentiment",
        "source_field": "sentiment_score",
    },
    {
        "metric_key": "quality_x_momentum",
        "name": "Quality x Momentum",
        "category": "cross_domain",
        "unit": "score",
        "direction": "higher_is_better",
        "source_table": "computed",
        "source_field": "roic,mom_6m",
    },
    {
        "metric_key": "sentiment_adjusted_beta",
        "name": "Sentiment-Adjusted Beta",
        "category": "cross_domain",
        "unit": "ratio",
        "direction": "lower_is_better",
        "source_table": "computed",
        "source_field": "beta,sentiment_score",
    },
    {
        "metric_key": "risk_adjusted_value",
        "name": "Risk-Adjusted Value",
        "category": "cross_domain",
        "unit": "score",
        "direction": "higher_is_better",
        "source_table": "computed",
        "source_field": "earnings_yield,vol_20d",
    },
]


class DerivedMetricsService:
    """Fetch inputs, compute derived metrics, and store normalized values."""

    _MAX_QUERY_PARAMS = 30000
    _DEFAULT_COLUMN_OVERHEAD = 2

    def __init__(
        self,
        lookback_days: int | None = None,
        sentiment_lookback_days: int | None = None,
        calc_version: str | None = None,
    ) -> None:
        self.engine = DerivedMetricsEngine()
        self.lookback_days = lookback_days or settings.DERIVED_METRICS_LOOKBACK_DAYS
        self.sentiment_lookback_days = (
            sentiment_lookback_days or settings.DERIVED_METRICS_SENTIMENT_LOOKBACK_DAYS
        )
        self.calc_version = calc_version or settings.DERIVED_METRICS_CALC_VERSION

    async def compute_and_store(
        self,
        symbols: list[str] | None = None,
        as_of_date: date | None = None,
    ) -> int:
        target_date = as_of_date or date.today()
        universe = symbols or await self._resolve_universe()
        if not universe:
            return 0

        start_date = target_date - timedelta(days=self.lookback_days)
        sentiment_start = target_date - timedelta(days=self.sentiment_lookback_days)

        async with AsyncSessionLocal() as session:
            bars = await self._fetch_daily_bars(session, universe, start_date, target_date)
            instrument_metrics = await self._fetch_instrument_metrics(session, universe, target_date)
            sentiment_series = await self._fetch_sentiment_series(session, universe, sentiment_start, target_date)

            await self._ensure_metric_definitions(session)
            definition_map = await self._load_metric_definitions(session)

            results = []
            for symbol in universe:
                bars_df = bars.get(symbol)
                if bars_df is None or bars_df.empty:
                    continue
                instrument = instrument_metrics.get(symbol)
                sentiment = sentiment_series.get(symbol)
                result = self.engine.compute_for_symbol(symbol, bars_df, instrument, sentiment)
                if result.metrics:
                    results.append(result)

            if not results:
                return 0

            normalized_rows = self._normalize_results(results, definition_map)
            if not normalized_rows:
                return 0

            rows = []
            for row in normalized_rows:
                definition = definition_map.get(row["metric_key"])
                if not definition:
                    continue
                rows.append(
                    {
                        "symbol": row["symbol"],
                        "as_of_date": target_date,
                        "metric_id": definition.id,
                        "value": row["value"],
                        "zscore": row["zscore"],
                        "percentile": row["percentile"],
                        "rank": row["rank"],
                        "source": definition.source_table or "computed",
                        "calc_version": self.calc_version,
                    }
                )

            if not rows:
                return 0

            for chunk in self._chunk_rows(rows):
                stmt = insert(DerivedMetricValue).values(chunk)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_derived_metric_values_symbol_date_metric",
                    set_={
                        "value": stmt.excluded.value,
                        "zscore": stmt.excluded.zscore,
                        "percentile": stmt.excluded.percentile,
                        "rank": stmt.excluded.rank,
                        "source": stmt.excluded.source,
                        "calc_version": stmt.excluded.calc_version,
                        "updated_at": func.now(),
                    },
                )
                await session.execute(stmt)
            await session.commit()

        return len(rows)

    async def _resolve_universe(self) -> list[str]:
        universe_service = UniverseService()
        if settings.DERIVED_METRICS_USE_GLOBAL_UNIVERSE:
            return await universe_service.get_global_symbols()
        return await universe_service.get_all_symbols()

    async def _fetch_daily_bars(
        self,
        session,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        stmt = select(DailyBar).where(
            DailyBar.symbol.in_(symbols),
            DailyBar.date >= start_date,
            DailyBar.date <= end_date,
        ).order_by(DailyBar.symbol.asc(), DailyBar.date.asc())
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return {}

        data = [
            {
                "symbol": row.symbol,
                "date": row.date,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "adj_close": float(row.adj_close),
                "volume": float(row.volume),
            }
            for row in rows
        ]
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        grouped = {}
        for symbol, group in df.groupby("symbol"):
            g = group.sort_values("date").set_index("date")
            grouped[symbol] = g
        return grouped

    async def _fetch_instrument_metrics(
        self,
        session,
        symbols: list[str],
        target_date: date,
    ) -> dict[str, dict[str, float]]:
        stmt = select(InstrumentMetrics).where(
            InstrumentMetrics.symbol.in_(symbols),
            InstrumentMetrics.as_of_date <= target_date,
        ).order_by(InstrumentMetrics.symbol.asc(), InstrumentMetrics.as_of_date.desc())
        result = await session.execute(stmt)
        rows = result.scalars().all()
        metrics_by_symbol: dict[str, InstrumentMetrics] = {}
        for row in rows:
            symbol = row.symbol
            existing = metrics_by_symbol.get(symbol)
            if existing is None:
                metrics_by_symbol[symbol] = row
                continue
            if existing.as_of_date == row.as_of_date:
                if existing.period_type != "TTM" and row.period_type == "TTM":
                    metrics_by_symbol[symbol] = row

        return {
            symbol: self._instrument_row_to_dict(record)
            for symbol, record in metrics_by_symbol.items()
        }

    async def _fetch_sentiment_series(
        self,
        session,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.Series]:
        stmt = select(MarketSentiment).where(
            MarketSentiment.symbol.in_(symbols),
            MarketSentiment.date >= start_date,
            MarketSentiment.date <= end_date,
        ).order_by(MarketSentiment.symbol.asc(), MarketSentiment.date.asc())
        result = await session.execute(stmt)
        rows = result.scalars().all()
        if not rows:
            return {}

        data = [
            {
                "symbol": row.symbol,
                "date": row.date,
                "sentiment_score": float(row.sentiment_score),
            }
            for row in rows
            if row.symbol
        ]
        df = pd.DataFrame(data)
        if df.empty:
            return {}
        df["date"] = pd.to_datetime(df["date"])
        series_map: dict[str, pd.Series] = {}
        for symbol, group in df.groupby("symbol"):
            series_map[symbol] = group.sort_values("date").set_index("date")["sentiment_score"]
        return series_map

    async def _ensure_metric_definitions(self, session) -> None:
        stmt = insert(DerivedMetricDefinition).values(
            [
                {
                    "metric_key": definition["metric_key"],
                    "name": definition["name"],
                    "category": definition["category"],
                    "unit": definition.get("unit"),
                    "direction": definition["direction"],
                    "lookback_days": definition.get("lookback_days"),
                    "description": definition.get("description"),
                    "tags": definition.get("tags"),
                    "source_table": definition.get("source_table"),
                    "source_field": definition.get("source_field"),
                    "version": definition.get("version", "v1"),
                    "is_active": definition.get("is_active", True),
                }
                for definition in METRIC_DEFINITIONS
            ]
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_derived_metric_definitions_key",
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "unit": stmt.excluded.unit,
                "direction": stmt.excluded.direction,
                "lookback_days": stmt.excluded.lookback_days,
                "description": stmt.excluded.description,
                "tags": stmt.excluded.tags,
                "source_table": stmt.excluded.source_table,
                "source_field": stmt.excluded.source_field,
                "version": stmt.excluded.version,
                "is_active": stmt.excluded.is_active,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)
        await session.commit()

    async def _load_metric_definitions(self, session) -> dict[str, DerivedMetricDefinition]:
        stmt = select(DerivedMetricDefinition).where(DerivedMetricDefinition.is_active.is_(True))
        result = await session.execute(stmt)
        definitions = result.scalars().all()
        return {definition.metric_key: definition for definition in definitions}

    def _normalize_results(
        self,
        results: list[Any],
        definition_map: dict[str, DerivedMetricDefinition],
    ) -> list[dict[str, Any]]:
        records = []
        for result in results:
            for metric_key, value in result.metrics.items():
                if metric_key not in definition_map or value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError):
                    continue
                if pd.isna(numeric):
                    continue
                records.append(
                    {
                        "symbol": result.symbol,
                        "metric_key": metric_key,
                        "value": numeric,
                    }
                )

        if not records:
            return []

        df = pd.DataFrame(records)
        normalized_rows: list[dict[str, Any]] = []

        for metric_key, group in df.groupby("metric_key"):
            definition = definition_map[metric_key]
            values = group["value"].astype(float)
            mean = values.mean()
            std = values.std(ddof=0)
            if std == 0 or pd.isna(std):
                zscores = pd.Series([0.0] * len(values), index=group.index)
            else:
                zscores = (values - mean) / std

            ascending = definition.direction == "lower_is_better"
            ranks = values.rank(ascending=ascending, method="min")
            if len(values) == 1:
                percentiles = pd.Series([1.0] * len(values), index=group.index)
            else:
                percentiles = 1 - (ranks - 1) / (len(values) - 1)

            group = group.copy()
            group["zscore"] = zscores.values
            group["percentile"] = percentiles.values
            group["rank"] = ranks.astype(int).values

            for row in group.itertuples(index=False):
                normalized_rows.append(
                    {
                        "symbol": row.symbol,
                        "metric_key": metric_key,
                        "value": row.value,
                        "zscore": row.zscore,
                        "percentile": row.percentile,
                        "rank": int(row.rank),
                    }
                )

        return normalized_rows

    def _instrument_row_to_dict(self, row: InstrumentMetrics) -> dict[str, float | None]:
        return {
            "pe_ttm": self._to_float(row.pe_ttm),
            "pe_forward": self._to_float(row.pe_forward),
            "peg_ratio": self._to_float(row.peg_ratio),
            "ev_to_ebitda": self._to_float(row.ev_to_ebitda),
            "fcf_yield": self._to_float(row.fcf_yield),
            "roe": self._to_float(row.roe),
            "roic": self._to_float(row.roic),
            "debt_to_equity": self._to_float(row.debt_to_equity),
            "beta": self._to_float(row.beta),
            "price_to_book": self._to_float(row.price_to_book),
            "gross_margin": self._to_float(row.gross_margin),
        }

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _chunk_rows(self, rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        if not rows:
            return []
        row_size = max(1, len(rows[0]) + self._DEFAULT_COLUMN_OVERHEAD)
        batch_size = max(1, min(1000, self._MAX_QUERY_PARAMS // row_size))
        return [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
