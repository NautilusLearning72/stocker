import asyncio
import logging
from typing import Dict, Any, List
from datetime import date, datetime, timezone
from sqlalchemy import func
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.signal import Signal as SignalModel
from stocker.models.target_exposure import TargetExposure as TargetModel
from stocker.models.instrument_info import InstrumentInfo
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig, TargetExposure, Signal
from stocker.strategy.diversification import InstrumentMeta
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
            drawdown_scale_factor=settings.DRAWDOWN_SCALE_FACTOR,
            # Diversification settings
            diversification_enabled=settings.DIVERSIFICATION_ENABLED,
            sector_cap=settings.SECTOR_CAP,
            asset_class_cap=settings.ASSET_CLASS_CAP,
            correlation_throttle_enabled=settings.CORRELATION_THROTTLE_ENABLED,
            correlation_threshold=settings.CORRELATION_THRESHOLD,
            correlation_lookback=settings.CORRELATION_LOOKBACK,
            correlation_scale_factor=settings.CORRELATION_SCALE_FACTOR
        ))

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        # data: {event_type, strategy, symbol, date, target_weight, ...}
        event_type = data.get("event_type", "signal_generated")

        # IMPORTANT: Only run optimization on batch completion, NOT on every individual signal.
        # This prevents exponential order generation (N signals × N targets = N² orders)
        if event_type == "signal_generated":
            # Individual signal - just log and wait for batch completion
            logger.debug(f"Received signal for {data.get('symbol')}, waiting for batch completion")
            return

        if event_type != "signals_batch_complete":
            logger.warning(f"Unknown event type: {event_type}")
            return

        # Batch completion - now run optimization on all signals for this date
        target_date_str = data.get("date")
        if not target_date_str:
            return

        target_date = date.fromisoformat(target_date_str)
        logger.info(f"Batch complete for {target_date}, running portfolio optimization")
        effective_date = target_date
        
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
                
            # 2. Fetch ALL signals for latest date <= target_date
            stmt = select(func.max(SignalModel.date)).where(SignalModel.date <= target_date)
            result = await session.execute(stmt)
            latest_signal_date = result.scalar_one_or_none()

            if latest_signal_date:
                if latest_signal_date != target_date:
                    logger.info(
                        f"No signals for {target_date}, using latest available {latest_signal_date}"
                    )
                effective_date = latest_signal_date
                stmt = select(SignalModel).where(SignalModel.date == effective_date)
                result = await session.execute(stmt)
                signal_models = result.scalars().all()
            else:
                signal_models = []

            # 3. Fetch instrument metadata for diversification
            instrument_metadata: Dict[str, InstrumentMeta] = {}
            if settings.DIVERSIFICATION_ENABLED and signal_models:
                symbols = [s.symbol for s in signal_models]
                stmt = select(InstrumentInfo).where(InstrumentInfo.symbol.in_(symbols))
                result = await session.execute(stmt)
                for info in result.scalars().all():
                    instrument_metadata[info.symbol] = InstrumentMeta(
                        symbol=info.symbol,
                        sector=info.sector or "Unknown",
                        asset_class=info.asset_class or "US_EQUITY"
                    )

        if not signal_models:
            logger.warning(f"No signals found on or before {target_date}")
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
            
        # 4. Optimize (with diversification if enabled)
        targets = self.optimizer.compute_targets(
            signals=signals_obj,
            current_drawdown=current_drawdown,
            instrument_metadata=instrument_metadata if instrument_metadata else None
        )
        
        def targets_match(existing: TargetModel, target: TargetExposure) -> bool:
            epsilon = 1e-8
            existing_reason = (existing.reason or "").strip()
            target_reason = (target.reason or "").strip()
            if abs(float(existing.target_exposure) - float(target.target_exposure)) > epsilon:
                return False
            if bool(existing.is_capped) != bool(target.is_capped):
                return False
            return existing_reason == target_reason

        # 5. Save Targets to DB (only if changed)
        changed_targets = []
        async with AsyncSessionLocal() as session:
            from sqlalchemy.dialects.postgresql import insert

            existing_targets: Dict[str, TargetModel] = {}
            if targets:
                symbols = [t.symbol for t in targets]
                stmt = select(TargetModel).where(
                    TargetModel.portfolio_id == "main",
                    TargetModel.date == effective_date,
                    TargetModel.symbol.in_(symbols)
                )
                result = await session.execute(stmt)
                for existing in result.scalars().all():
                    existing_targets[existing.symbol] = existing

            for t in targets:
                existing = existing_targets.get(t.symbol)
                if existing and targets_match(existing, t):
                    continue
                changed_targets.append(t)
                stmt = insert(TargetModel).values({
                    "portfolio_id": "main", # Single portfolio for now
                    "date": effective_date,
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
                        "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)
                    }
                )
                await session.execute(stmt)
            if changed_targets:
                await session.commit()
            else:
                await session.rollback()
            
        # 5. Publish 'targets_generated' event
        # Only publish if this specific message triggered a change? 
        # Or publish all? 
        # Downstream OrderConsumer will diff against current holdings.
        # Simpler to publish "Portfolio Targets Ready" or generic event.
        # Let's publish individual target updates for granular reactions.
        if not changed_targets:
            logger.info(f"No target changes for {effective_date}, skipping publish")
            return

        for t in changed_targets:
            await self.redis.xadd(StreamNames.TARGETS, {
                "event_type": "target_updated",
                "portfolio_id": "main",
                "date": effective_date.isoformat(),
                "symbol": t.symbol,
                "target_exposure": str(t.target_exposure),
                "reason": t.reason or ""
            })
            
        logger.info(f"Published {len(changed_targets)} targets for {effective_date}")

if __name__ == "__main__":
    async def main():
        consumer = PortfolioConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
