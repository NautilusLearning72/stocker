import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import func
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.signal import Signal as SignalModel
from stocker.models.target_exposure import TargetExposure as TargetModel
from stocker.models.instrument_info import InstrumentInfo
from stocker.models.market_sentiment import MarketSentiment
from stocker.models.instrument_metrics import InstrumentMetrics
from stocker.models.market_breadth import MarketBreadth
from stocker.models.daily_bar import DailyBar
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig, TargetExposure, Signal
from stocker.strategy.diversification import InstrumentMeta
from stocker.models.portfolio_state import PortfolioState
from stocker.models.holding import Holding

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
            correlation_scale_factor=settings.CORRELATION_SCALE_FACTOR,
            # Signal enhancement settings
            enhancement_enabled=settings.ENHANCEMENT_ENABLED,
            conviction_enabled=settings.CONVICTION_ENABLED,
            sentiment_enabled=settings.SENTIMENT_ENABLED,
            regime_enabled=settings.REGIME_ENABLED,
            quality_enabled=settings.QUALITY_ENABLED
        ))

    async def _fetch_sentiment_data(
        self, session, symbols: List[str], target_date: date
    ) -> Dict[str, float]:
        """Fetch latest sentiment scores for symbols."""
        sentiment_data: Dict[str, float] = {}
        
        # Get most recent sentiment for each symbol on or before target_date
        stmt = select(MarketSentiment).where(
            MarketSentiment.symbol.in_(symbols),
            MarketSentiment.date <= target_date
        ).order_by(MarketSentiment.date.desc())
        result = await session.execute(stmt)
        
        seen_symbols = set()
        for row in result.scalars().all():
            if row.symbol not in seen_symbols:
                sentiment_data[row.symbol] = float(row.sentiment_score)
                seen_symbols.add(row.symbol)
        
        if sentiment_data:
            logger.info(f"Fetched sentiment for {len(sentiment_data)} symbols")
        else:
            logger.info("No sentiment data available for enhancement")
        
        return sentiment_data

    async def _fetch_instrument_metrics(
        self, session, symbols: List[str], target_date: date
    ) -> Dict[str, dict]:
        """Fetch latest instrument metrics (market_cap, beta, volume)."""
        metrics_data: Dict[str, dict] = {}
        
        # Get most recent metrics for each symbol
        stmt = select(InstrumentMetrics).where(
            InstrumentMetrics.symbol.in_(symbols),
            InstrumentMetrics.as_of_date <= target_date
        ).order_by(InstrumentMetrics.as_of_date.desc())
        result = await session.execute(stmt)
        
        seen_symbols = set()
        for row in result.scalars().all():
            if row.symbol not in seen_symbols:
                metrics_data[row.symbol] = {
                    "market_cap": float(row.market_cap) if row.market_cap else None,
                    "beta": float(row.beta) if row.beta else None,
                }
                seen_symbols.add(row.symbol)
        
        # Fetch average volume from daily bars (last 20 days)
        lookback_start = target_date - timedelta(days=30)
        stmt = select(
            DailyBar.symbol,
            func.avg(DailyBar.volume).label("avg_volume")
        ).where(
            DailyBar.symbol.in_(symbols),
            DailyBar.date >= lookback_start,
            DailyBar.date <= target_date
        ).group_by(DailyBar.symbol)
        result = await session.execute(stmt)
        
        for row in result.all():
            if row.symbol in metrics_data:
                metrics_data[row.symbol]["avg_volume"] = float(row.avg_volume) if row.avg_volume else None
            else:
                metrics_data[row.symbol] = {"avg_volume": float(row.avg_volume) if row.avg_volume else None}
        
        if metrics_data:
            logger.info(f"Fetched instrument metrics for {len(metrics_data)} symbols")
        else:
            logger.info("No instrument metrics available for enhancement")
        
        return metrics_data

    async def _fetch_market_breadth(
        self, session, target_date: date
    ) -> Optional[float]:
        """Fetch market breadth (% stocks above 200-day MA)."""
        stmt = select(MarketBreadth).where(
            MarketBreadth.date <= target_date,
            MarketBreadth.metric == "pct_above_200d_ma"
        ).order_by(MarketBreadth.date.desc()).limit(1)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        
        if row:
            breadth = float(row.value)
            logger.info(f"Market breadth: {breadth:.1%}")
            return breadth
        
        logger.info("No market breadth data available for enhancement")
        return None

    async def _fetch_vix_level(
        self, session, target_date: date
    ) -> Optional[float]:
        """Fetch VIX level from daily bars."""
        # VIX is typically stored as ^VIX or VIX
        stmt = select(DailyBar).where(
            DailyBar.symbol.in_(["^VIX", "VIX", "$VIX"]),
            DailyBar.date <= target_date
        ).order_by(DailyBar.date.desc()).limit(1)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        
        if row:
            vix = float(row.adj_close)
            logger.info(f"VIX level: {vix:.2f}")
            return vix
        
        logger.info("No VIX data available for enhancement")
        return None

    async def _fetch_historical_returns(
        self, session, symbols: List[str], target_date: date, lookback: int = 60
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical returns for correlation calculation.
        
        Args:
            session: Database session
            symbols: List of symbols to fetch
            target_date: End date for returns
            lookback: Number of trading days to fetch
            
        Returns:
            DataFrame with symbols as columns, dates as index, daily returns as values
        """
        if not symbols:
            return None
            
        # Fetch ~lookback trading days of data (buffer for weekends/holidays)
        start_date = target_date - timedelta(days=int(lookback * 1.5))
        
        stmt = select(
            DailyBar.symbol,
            DailyBar.date,
            DailyBar.adj_close
        ).where(
            DailyBar.symbol.in_(symbols),
            DailyBar.date >= start_date,
            DailyBar.date <= target_date
        ).order_by(DailyBar.date)
        
        result = await session.execute(stmt)
        rows = result.all()
        
        if not rows:
            logger.info("No historical price data for correlation")
            return None
        
        # Build DataFrame: pivot to get symbols as columns
        data = {"date": [], "symbol": [], "adj_close": []}
        for row in rows:
            data["date"].append(row.date)
            data["symbol"].append(row.symbol)
            data["adj_close"].append(float(row.adj_close))
        
        df = pd.DataFrame(data)
        prices = df.pivot(index="date", columns="symbol", values="adj_close")
        
        # Calculate daily returns
        returns = prices.pct_change().dropna()
        
        if returns.empty or len(returns) < 20:
            logger.info(
                f"Insufficient return data for correlation "
                f"({len(returns)} days, need 20+)"
            )
            return None
        
        logger.info(
            f"Fetched {len(returns)} days of returns for "
            f"{len(returns.columns)} symbols"
        )
        return returns

    async def _fetch_current_positions(
        self, session, portfolio_id: str, target_date: date
    ) -> Dict[str, float]:
        """
        Fetch current position weights for correlation throttling.
        
        Args:
            session: Database session
            portfolio_id: Portfolio identifier
            target_date: Date to get positions for
            
        Returns:
            Dict mapping symbol to position weight (as fraction of NAV)
        """
        positions: Dict[str, float] = {}
        
        # Get latest holdings on or before target_date
        stmt = select(func.max(Holding.date)).where(
            Holding.portfolio_id == portfolio_id,
            Holding.date <= target_date
        )
        result = await session.execute(stmt)
        latest_date = result.scalar_one_or_none()
        
        if not latest_date:
            logger.info("No existing holdings for correlation throttle")
            return positions
        
        stmt = select(Holding).where(
            Holding.portfolio_id == portfolio_id,
            Holding.date == latest_date
        )
        result = await session.execute(stmt)
        holdings = result.scalars().all()
        
        if not holdings:
            return positions
        
        # Calculate total portfolio value
        total_value = sum(float(h.market_value) for h in holdings)
        if total_value <= 0:
            return positions
        
        # Convert to weights
        for h in holdings:
            weight = float(h.market_value) / total_value
            positions[h.symbol] = weight
        
        logger.info(
            f"Fetched {len(positions)} current positions for correlation"
        )
        return positions

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

            # 4. Fetch enhancement data if enabled
            sentiment_data: Dict[str, float] = {}
            instrument_metrics: Dict[str, dict] = {}
            market_breadth: Optional[float] = None
            vix_level: Optional[float] = None
            
            if settings.ENHANCEMENT_ENABLED and signal_models:
                symbols = [s.symbol for s in signal_models]
                logger.info(f"Fetching enhancement data for {len(symbols)} symbols")
                
                sentiment_data = await self._fetch_sentiment_data(session, symbols, effective_date)
                instrument_metrics = await self._fetch_instrument_metrics(session, symbols, effective_date)
                market_breadth = await self._fetch_market_breadth(session, effective_date)
                vix_level = await self._fetch_vix_level(session, effective_date)

            # 4b. Fetch correlation data if enabled
            historical_returns: Optional[pd.DataFrame] = None
            current_positions: Dict[str, float] = {}
            
            if settings.CORRELATION_THROTTLE_ENABLED and signal_models:
                symbols = [s.symbol for s in signal_models]
                portfolio_id = "default"  # TODO: support multiple portfolios
                
                historical_returns = await self._fetch_historical_returns(
                    session, symbols, effective_date,
                    lookback=settings.CORRELATION_LOOKBACK
                )
                current_positions = await self._fetch_current_positions(
                    session, portfolio_id, effective_date
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
            
        # 5. Optimize (with diversification and enhancement if enabled)
        targets = self.optimizer.compute_targets(
            signals=signals_obj,
            current_drawdown=current_drawdown,
            instrument_metadata=instrument_metadata if instrument_metadata else None,
            returns=historical_returns,
            current_positions=current_positions if current_positions else None,
            sentiment_data=sentiment_data if sentiment_data else None,
            instrument_metrics=instrument_metrics if instrument_metrics else None,
            market_breadth=market_breadth,
            vix_level=vix_level
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
