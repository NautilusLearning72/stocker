import asyncio
import logging
from typing import Dict, Any
from datetime import date, datetime
import pandas as pd
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.daily_bar import DailyBar
from stocker.models.signal import Signal as SignalModel
from stocker.strategy.signal_strategy import SignalStrategy, SignalConfig

logger = logging.getLogger(__name__)

class SignalConsumer(BaseStreamConsumer):
    """
    Listens for market-bars events.
    Fetches historical data for the symbol.
    Runs SignalStrategy.
    Publishes signals to 'signals' stream.
    Persists signals to DB.
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.MARKET_BARS,
            consumer_group="signal-processors"
        )
        self.strategy = SignalStrategy(SignalConfig(
            strategy_name="vol_target_trend_v1",
            lookback_days=settings.LOOKBACK_DAYS,
            ewma_lambda=settings.EWMA_LAMBDA,
            target_vol=settings.TARGET_VOL
        ))

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        # data expected: { "symbol": "SPY", "date": "2023-10-27", ... }
        symbol = data.get("symbol")
        date_str = data.get("date")
        
        if not symbol or not date_str:
            logger.warning(f"Invalid message data: {data}")
            return
            
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            logger.error(f"Invalid date format: {date_str}")
            return

        logger.info(f"Processing signal for {symbol} on {target_date}")

        # 1. Fetch History from DB
        # We need lookback_days + 1 records ending at target_date
        # Ideally we fetch a bit more to be safe
        needed_days = self.strategy.config.lookback_days + 50 
        
        async with AsyncSessionLocal() as session:
             # Fetch bars
             stmt = select(DailyBar).where(
                 DailyBar.symbol == symbol,
                 DailyBar.date <= target_date
             ).order_by(DailyBar.date.desc()).limit(needed_days)
             
             result = await session.execute(stmt)
             bars = result.scalars().all()
             
        if not bars:
            logger.warning(f"No history found for {symbol}")
            return
            
        # Convert to DataFrame
        # SignalStrategy expects 'adj_close' and DatetimeIndex
        df = pd.DataFrame([
            {"date": b.date, "adj_close": float(b.adj_close)} 
            for b in bars
        ])
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True) # Ensure ascending order
        
        # 2. Compute Signal
        try:
            signal = self.strategy.compute_signal(symbol, df)
        except ValueError as e:
            # Not enough data typically
            logger.info(f"Skipping {symbol}: {e}")
            return

        # 3. Store in DB
        async with AsyncSessionLocal() as session:
            # Idempotency: Try insert, ignore if exists? 
            # Or Upsert. Let's Upsert.
            from sqlalchemy.dialects.postgresql import insert
            
            stmt = insert(SignalModel).values({
                "strategy_version": signal.strategy_version,
                "symbol": signal.symbol,
                "date": signal.date,
                "lookback_return": signal.metrics["lookback_return"],
                "ewma_vol": signal.metrics["ewma_vol"],
                "direction": signal.direction,
                "target_weight": signal.raw_weight
            })
            stmt = stmt.on_conflict_do_update(
                constraint="uq_signals_strat_sym_date",
                set_={
                    "lookback_return": stmt.excluded.lookback_return,
                    "ewma_vol": stmt.excluded.ewma_vol,
                    "direction": stmt.excluded.direction,
                    "target_weight": stmt.excluded.target_weight,
                    "updated_at": datetime.utcnow()
                }
            )
            await session.execute(stmt)
            await session.commit()
            
        # 4. Push to Redis Stream
        event_data = {
            "event_type": "signal_generated",
            "strategy": signal.strategy_version,
            "symbol": signal.symbol,
            "date": signal.date.isoformat(),
            "direction": str(signal.direction),
            "target_weight": str(signal.raw_weight),
            # Flatten metrics for Redis (it prefers simple key-values or strings)
            "metric_lookback_return": str(signal.metrics["lookback_return"]),
            "metric_ewma_vol": str(signal.metrics["ewma_vol"])
        }
        
        await self.redis.xadd(StreamNames.SIGNALS, event_data)
        logger.info(f"Published signal for {symbol}")

if __name__ == "__main__":
    consumer = SignalConsumer()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(consumer.start())
    except KeyboardInterrupt:
        loop.run_until_complete(consumer.stop())
