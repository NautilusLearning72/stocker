import asyncio
import logging
from typing import Dict, Any, List
from datetime import date, datetime
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.signal import Signal as SignalModel
from stocker.models.target_exposure import TargetExposure as TargetModel
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig, TargetExposure, Signal
from stocker.models.portfolio_state import PortfolioState

logger = logging.getLogger(__name__)

class PortfolioConsumer(BaseStreamConsumer):
    """
    Listens for 'signals'.
    Aggregates signals for the day (waiting for all/some logic?).
    Runs PortfolioOptimizer.
    Publishes 'targets'.
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.SIGNALS,
            consumer_group="portfolio-managers"
        )
        self.optimizer = PortfolioOptimizer(RiskConfig(
            single_instrument_cap=settings.SINGLE_INSTRUMENT_CAP,
            gross_exposure_cap=settings.GROSS_EXPOSURE_CAP,
            drawdown_threshold=settings.DRAWDOWN_THRESHOLD,
            drawdown_scale_factor=settings.DRAWDOWN_SCALE_FACTOR
        ))

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        # data: {event_type, strategy, symbol, date, target_weight, ...}
        
        # NOTE: Portfolio Optimization typically happens once per day after ALL signals are ready.
        # But this is a stream consumer processing one by one.
        # Approach:
        # 1. Simple: Just optimize this single signal against empty portfolio (naive).
        # 2. Better: Checks if we have signals for all universe for this date.
        # 3. Hybrid: We re-optimize the WHOLE portfolio every time a new signal arrives for the date.
        #    This is "eventual consistency". As signals arrive, target weights adjust.
        #    Wait, PortfolioOptimizer needs ALL signals to calculate Gross Exposure properly if we want to CAP it.
        #    If we process one by one, we don't know the others.
        
        # Decision: We will fetch ALL valid signals for the message's DATE from DB, 
        # then run optimization on the full set, then publish targets for ALL.
        
        target_date_str = data.get("date")
        if not target_date_str:
            return
            
        target_date = date.fromisoformat(target_date_str)
        
        # 1. Fetch current portfolio state (drawdown)
        # We need the LATEST known state. If processing today's signals, we want yesterday's Close state.
        # Or even better, a "Realtime" estimate. For now, use last DB entry.
        current_drawdown = 0.0
        async with AsyncSessionLocal() as session:
            stmt = select(PortfolioState).order_by(PortfolioState.date.desc()).limit(1)
            result = await session.execute(stmt)
            state = result.scalar_one_or_none()
            if state:
                current_drawdown = float(state.drawdown)
                
            # 2. Fetch ALL signals for this date
            stmt = select(SignalModel).where(SignalModel.date == target_date)
            result = await session.execute(stmt)
            signal_models = result.scalars().all()
            
        if not signal_models:
            logger.warning(f"No signals found for {target_date}??")
            return
            
        # Convert DB models to Strategy objects
        signals_obj = []
        for s in signal_models:
            signals_obj.append(Signal(
                symbol=s.symbol,
                date=s.date,
                metrics={"ewma_vol": float(s.ewma_vol), "lookback_return": float(s.lookback_return)},
                raw_weight=float(s.target_weight),
                direction=int(s.direction),
                strategy_version=s.strategy_version
            ))
            
        # 3. Optimize
        targets = self.optimizer.compute_targets(signals_obj, current_drawdown)
        
        # 4. Save Targets to DB
        async with AsyncSessionLocal() as session:
            from sqlalchemy.dialects.postgresql import insert
            
            for t in targets:
                stmt = insert(TargetModel).values({
                    "portfolio_id": "main", # Single portfolio for now
                    "date": target_date,
                    "symbol": t.symbol,
                    "target_exposure": t.target_exposure,
                    "scaling_factor": 1.0, # TODO: Track this in optimizer output
                    "is_capped": t.is_capped,
                    "reason": t.reason
                })
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_target_exposures_port_sym_date",
                    set_={
                        "target_exposure": stmt.excluded.target_exposure,
                        "is_capped": stmt.excluded.is_capped,
                        "reason": stmt.excluded.reason,
                        "updated_at": datetime.utcnow()
                    }
                )
                await session.execute(stmt)
            await session.commit()
            
        # 5. Publish 'targets_generated' event
        # Only publish if this specific message triggered a change? 
        # Or publish all? 
        # Downstream OrderConsumer will diff against current holdings.
        # Simpler to publish "Portfolio Targets Ready" or generic event.
        # Let's publish individual target updates for granular reactions.
        
        for t in targets:
            await self.redis.xadd(StreamNames.TARGETS, {
                "event_type": "target_updated",
                "portfolio_id": "main",
                "date": target_date_str,
                "symbol": t.symbol,
                "target_exposure": str(t.target_exposure),
                "reason": t.reason or ""
            })
            
        logger.info(f"Published {len(targets)} targets for {target_date}")

if __name__ == "__main__":
    async def main():
        consumer = PortfolioConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
