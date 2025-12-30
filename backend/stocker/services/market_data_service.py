import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
import pandas as pd
import numpy as np
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
from stocker.core.database import AsyncSessionLocal
from stocker.models.daily_bar import DailyBar
from stocker.services.market_data import get_market_data_provider
from stocker.core.config import settings
import logging

logger = logging.getLogger(__name__)


@dataclass
class DataQualityAlert:
    """Represents a data quality issue."""
    symbol: str
    date: date
    issue_type: str
    message: str
    severity: str  # "WARNING" or "ERROR"


class DataQualityValidator:
    """
    Validates market data per TDD spec:
    - No zero/negative prices
    - No gaps > 30% without confirmation
    - No missing bars in required lookback period
    """

    MAX_GAP_PERCENT = 0.30  # 30% gap threshold
    REQUIRED_LOOKBACK_DAYS = 200  # TDD: no missing bars in last 200 days

    def __init__(self):
        self.alerts: List[DataQualityAlert] = []

    def validate_bar(self, row: pd.Series, prev_close: Optional[float] = None) -> Tuple[bool, Optional[DataQualityAlert]]:
        """
        Validate a single bar.
        Returns (is_valid, alert_if_any).
        """
        symbol = str(row.get('symbol', 'UNKNOWN'))
        bar_date = row.get('date', date.today())

        # Check for zero/negative prices
        for field in ['open', 'high', 'low', 'close', 'adj_close']:
            value = row.get(field, 0)
            if value is None or value <= 0:
                alert = DataQualityAlert(
                    symbol=symbol,
                    date=bar_date,
                    issue_type="INVALID_PRICE",
                    message=f"{field} is zero or negative: {value}",
                    severity="ERROR"
                )
                self.alerts.append(alert)
                return False, alert

        # Check for negative volume
        volume = row.get('volume', 0)
        if volume is None or volume < 0:
            alert = DataQualityAlert(
                symbol=symbol,
                date=bar_date,
                issue_type="INVALID_VOLUME",
                message=f"Volume is negative: {volume}",
                severity="ERROR"
            )
            self.alerts.append(alert)
            return False, alert

        # Check for >30% gap from previous close
        if prev_close is not None and prev_close > 0:
            current_open = float(row.get('open', 0))
            gap_pct = abs(current_open - prev_close) / prev_close

            if gap_pct > self.MAX_GAP_PERCENT:
                alert = DataQualityAlert(
                    symbol=symbol,
                    date=bar_date,
                    issue_type="LARGE_GAP",
                    message=f"Gap of {gap_pct:.1%} from prev close {prev_close} to open {current_open}",
                    severity="WARNING"
                )
                self.alerts.append(alert)
                # Don't reject, but flag for review
                logger.warning(f"Large gap detected: {alert.message}")

        # OHLC sanity: High >= Low, High >= Open/Close, Low <= Open/Close
        o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
        if h < l:
            alert = DataQualityAlert(
                symbol=symbol,
                date=bar_date,
                issue_type="INVALID_OHLC",
                message=f"High ({h}) < Low ({l})",
                severity="ERROR"
            )
            self.alerts.append(alert)
            return False, alert

        if h < max(o, c) or l > min(o, c):
            alert = DataQualityAlert(
                symbol=symbol,
                date=bar_date,
                issue_type="INVALID_OHLC",
                message=f"OHLC inconsistent: O={o}, H={h}, L={l}, C={c}",
                severity="WARNING"
            )
            self.alerts.append(alert)
            # Allow but warn

        return True, None

    def validate_series_completeness(
        self,
        symbol: str,
        bars: pd.DataFrame,
        expected_trading_days: int = 200
    ) -> Optional[DataQualityAlert]:
        """
        Check if we have sufficient history for the symbol.
        TDD requires no missing bars in last 200 trading days.
        """
        if len(bars) < expected_trading_days:
            alert = DataQualityAlert(
                symbol=symbol,
                date=date.today(),
                issue_type="INSUFFICIENT_HISTORY",
                message=f"Only {len(bars)} bars available, need {expected_trading_days}",
                severity="WARNING"
            )
            self.alerts.append(alert)
            return alert

        # Check for gaps in dates (missing trading days)
        if 'date' in bars.columns:
            bars_sorted = bars.sort_values('date')
            dates = pd.to_datetime(bars_sorted['date'])
            gaps = dates.diff().dt.days

            # More than 5 calendar days between bars suggests missing data
            # (accounts for weekends + holidays)
            large_gaps = gaps[gaps > 5]
            if len(large_gaps) > 0:
                gap_dates = bars_sorted.iloc[large_gaps.index]['date'].tolist()
                alert = DataQualityAlert(
                    symbol=symbol,
                    date=date.today(),
                    issue_type="MISSING_BARS",
                    message=f"Potential missing bars around dates: {gap_dates[:3]}...",
                    severity="WARNING"
                )
                self.alerts.append(alert)
                return alert

        return None

    def get_alerts(self) -> List[DataQualityAlert]:
        """Return all accumulated alerts."""
        return self.alerts

    def clear_alerts(self) -> None:
        """Clear accumulated alerts."""
        self.alerts = []


class MarketDataService:
    """
    Service to orchestrate fetching, validating, and storing market data.
    Implements TDD data quality rules.
    """

    def __init__(self, provider_name: str = "yfinance"):
        self.provider = get_market_data_provider(provider_name)
        self.provider_name = provider_name
        self.validator = DataQualityValidator()

    async def fetch_and_store_daily_bars(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date
    ) -> Tuple[int, List[DataQualityAlert]]:
        """
        Fetch data from provider, validate, and upsert into database.
        Returns (number of records processed, list of data quality alerts).
        """
        logger.info(f"Fetching data for {len(symbols)} symbols from {start_date} to {end_date}")
        self.validator.clear_alerts()

        # 1. Fetch
        df = self.provider.fetch_daily_bars(symbols, start_date, end_date)
        if df.empty:
            logger.warning("No data returned from provider")
            return 0, []

        # 2. Transform & Validate with quality checks
        records = []
        prev_closes: dict[str, float] = {}

        # Sort by symbol and date for gap detection
        df_sorted = df.sort_values(['symbol', 'date'])

        for _, row in df_sorted.iterrows():
            symbol = str(row['symbol'])

            # Get previous close for gap detection
            prev_close = prev_closes.get(symbol)

            # Validate the bar
            is_valid, alert = self.validator.validate_bar(row, prev_close)

            if is_valid:
                record = self._prepare_record(row)
                if record:
                    records.append(record)
                    # Update prev_close for next iteration
                    prev_closes[symbol] = float(row['close'])
            else:
                logger.warning(f"Rejected invalid bar: {symbol} {row.get('date')}: {alert.message if alert else 'unknown'}")

        if not records:
            return 0, self.validator.get_alerts()

        # 3. Store (Upsert) in batches to avoid parameter limit
        # SQLAlchemy has a limit of ~32k parameters
        # Each record has ~12 fields, so batch size of 1000 = 12k parameters
        BATCH_SIZE = 1000
        total_inserted = 0

        async with AsyncSessionLocal() as session:
            try:
                for i in range(0, len(records), BATCH_SIZE):
                    batch = records[i:i + BATCH_SIZE]

                    # We use Postgres bulk upsert (ON CONFLICT DO UPDATE)
                    # Index is (symbol, date)
                    stmt = insert(DailyBar).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_prices_daily_symbol_date",
                        set_={
                            "open": stmt.excluded.open,
                            "high": stmt.excluded.high,
                            "low": stmt.excluded.low,
                            "close": stmt.excluded.close,
                            "adj_close": stmt.excluded.adj_close,
                            "volume": stmt.excluded.volume,
                            "source": stmt.excluded.source,
                            "source_hash": stmt.excluded.source_hash,
                            "updated_at": stmt.excluded.created_at  # roughly usable as update time
                        }
                    )

                    await session.execute(stmt)
                    total_inserted += len(batch)
                    logger.info(f"Upserted batch {i // BATCH_SIZE + 1}: {len(batch)} bars (total: {total_inserted}/{len(records)})")

                await session.commit()
                logger.info(f"Successfully upserted {total_inserted} daily bars")

                # Log any data quality alerts
                alerts = self.validator.get_alerts()
                if alerts:
                    logger.warning(f"Data quality alerts: {len(alerts)} issues detected")
                    for alert in alerts:
                        logger.warning(f"  [{alert.severity}] {alert.symbol}: {alert.issue_type} - {alert.message}")

                return total_inserted, alerts
            except Exception as e:
                logger.error(f"Failed to store market data: {e}")
                await session.rollback()
                return 0, self.validator.get_alerts()

    async def validate_symbol_history(self, symbol: str, required_days: int = 200) -> List[DataQualityAlert]:
        """
        Validate that a symbol has sufficient history in the database.
        Returns list of alerts if issues found.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(DailyBar).where(
                DailyBar.symbol == symbol
            ).order_by(DailyBar.date.desc()).limit(required_days)

            result = await session.execute(stmt)
            bars = result.scalars().all()

            if len(bars) < required_days:
                alert = DataQualityAlert(
                    symbol=symbol,
                    date=date.today(),
                    issue_type="INSUFFICIENT_HISTORY",
                    message=f"Only {len(bars)} bars in DB, need {required_days}",
                    severity="WARNING"
                )
                return [alert]

        return []

    def _prepare_record(self, row: pd.Series) -> Optional[dict]:
        """Convert DataFrame row to dictionary for DB insert."""
        try:
            # Create content hash for audit
            # We strictly cast to string to ensure consistent hashing
            raw_content = f"{row['symbol']}|{row['date']}|{row['close']}|{row['volume']}"
            content_hash = hashlib.sha256(raw_content.encode()).hexdigest()
            
            return {
                "symbol": str(row['symbol']),
                "date": row['date'],
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "adj_close": float(row['adj_close']),
                "volume": int(row['volume']),
                "source": self.provider_name,
                "source_hash": content_hash
            }
        except Exception as e:
            logger.warning(f"Skipping invalid row: {row}: {e}")
            return None
