import hashlib
import json
from datetime import date
from typing import List, Optional
import pandas as pd
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert
from stocker.core.database import AsyncSessionLocal
from stocker.models.daily_bar import DailyBar
from stocker.services.market_data import get_market_data_provider
from stocker.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MarketDataService:
    """
    Service to orchestrate fetching, validating, and storing market data.
    """

    def __init__(self, provider_name: str = "yfinance"):
        self.provider = get_market_data_provider(provider_name)
        self.provider_name = provider_name

    async def fetch_and_store_daily_bars(self, 
                                         symbols: List[str], 
                                         start_date: date, 
                                         end_date: date) -> int:
        """
        Fetch data from provider and upsert into database.
        Returns number of records processed.
        """
        logger.info(f"Fetching data for {len(symbols)} symbols from {start_date} to {end_date}")
        
        # 1. Fetch
        df = self.provider.fetch_daily_bars(symbols, start_date, end_date)
        if df.empty:
            logger.warning("No data returned from provider")
            return 0
        
        # 2. Transform & Validate
        records = []
        for _, row in df.iterrows():
            record = self._prepare_record(row)
            if record:
                records.append(record)
                
        if not records:
            return 0
            
        # 3. Store (Upsert)
        async with AsyncSessionLocal() as session:
            # We use Postgres bulk upsert (ON CONFLICT DO UPDATE)
            # Index is (symbol, date)
            stmt = insert(DailyBar).values(records)
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
                    "updated_at": stmt.excluded.created_at # roughly usable as update time
                }
            )
            
            try:
                result = await session.execute(stmt)
                await session.commit()
                logger.info(f"Upserted {len(records)} daily bars")
                return len(records)
            except Exception as e:
                logger.error(f"Failed to store market data: {e}")
                await session.rollback()
                return 0

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
