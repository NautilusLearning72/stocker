"""
Exit rule consumer.

Listens to market-bars events and evaluates exit rules for active positions.
Generates exit signals when trailing stops, ATR exits, or persistence filters trigger.
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.core.metrics import metrics
from stocker.models.daily_bar import DailyBar
from stocker.models.position_state import PositionState
from stocker.models.signal import Signal as SignalModel
from stocker.strategy.exit_rules import (
    ExitRuleEngine,
    ExitConfig,
    PositionStateData,
)

logger = logging.getLogger(__name__)


class ExitConsumer(BaseStreamConsumer):
    """
    Evaluates exit rules when new price data arrives.

    Workflow:
    1. Listen for market-bars batch_complete events
    2. Load active positions from PositionState
    3. Fetch recent prices for each position
    4. Evaluate exit rules (trailing stop, ATR exit, persistence)
    5. If exit triggered, publish to targets stream with target_exposure=0
    6. Update PositionState with new peak/trough prices
    """

    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.MARKET_BARS,
            consumer_group="exit-evaluators",
        )
        self.exit_engine = ExitRuleEngine(
            ExitConfig(
                enabled=settings.EXIT_RULES_ENABLED,
                trailing_stop_atr=settings.TRAILING_STOP_ATR,
                atr_exit_multiple=settings.ATR_EXIT_MULTIPLE,
                atr_period=settings.ATR_PERIOD,
                persistence_days=settings.PERSISTENCE_DAYS,
            )
        )
        self.portfolio_id = "default"

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process market-bars events to evaluate exit rules."""
        event_type = data.get("event_type")

        if event_type != "batch_complete":
            return

        if not settings.EXIT_RULES_ENABLED:
            logger.debug("Exit rules disabled, skipping evaluation")
            return

        date_str = data.get("date")
        if not date_str:
            return

        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            logger.error(f"Invalid date format: {date_str}")
            return

        logger.info(f"Evaluating exit rules for {target_date}")

        async with AsyncSessionLocal() as session:
            # Load active positions
            stmt = select(PositionState).where(
                PositionState.portfolio_id == self.portfolio_id,
                PositionState.direction != 0,
            )
            result = await session.execute(stmt)
            positions = result.scalars().all()

            if not positions:
                logger.debug("No active positions to evaluate")
                return

            logger.info(f"Evaluating {len(positions)} active positions")

            # Get latest signals for persistence filter
            symbols = [p.symbol for p in positions]
            stmt = select(SignalModel).where(
                SignalModel.symbol.in_(symbols),
                SignalModel.date == target_date,
            )
            result = await session.execute(stmt)
            signals = {s.symbol: s for s in result.scalars().all()}

            exit_count = 0
            update_count = 0

            for position in positions:
                try:
                    exited, updated = await self._evaluate_position(
                        session, position, signals.get(position.symbol), target_date
                    )
                    if exited:
                        exit_count += 1
                    if updated:
                        update_count += 1
                except Exception as e:
                    logger.error(f"Error evaluating {position.symbol}: {e}")

            await session.commit()

            logger.info(
                f"Exit evaluation complete: {exit_count} exits, "
                f"{update_count} updated"
            )

            metrics.emit(
                metrics.CATEGORY_RISK,
                "exit_evaluation",
                exit_count,
                metadata={
                    "positions_evaluated": len(positions),
                    "exits_triggered": exit_count,
                    "date": date_str,
                },
            )

    async def _evaluate_position(
        self,
        session,
        position: PositionState,
        signal: Optional[SignalModel],
        target_date: date,
    ) -> tuple[bool, bool]:
        """Evaluate exit rules for a single position."""
        lookback_start = target_date - timedelta(days=30)
        stmt = select(DailyBar).where(
            DailyBar.symbol == position.symbol,
            DailyBar.date >= lookback_start,
            DailyBar.date <= target_date,
        ).order_by(DailyBar.date)
        result = await session.execute(stmt)
        bars = result.scalars().all()

        if len(bars) < 5:
            logger.warning(f"Insufficient data for {position.symbol}")
            return False, False

        prices = pd.DataFrame([
            {
                "date": b.date,
                "high": float(b.high) if b.high else float(b.adj_close),
                "low": float(b.low) if b.low else float(b.adj_close),
                "adj_close": float(b.adj_close),
            }
            for b in bars
        ])
        prices.set_index("date", inplace=True)

        new_direction = (
            int(signal.direction) if signal else int(position.direction)
        )

        pos_data = PositionStateData(
            symbol=position.symbol,
            direction=int(position.direction),
            entry_date=position.entry_date,
            entry_price=(
                float(position.entry_price) if position.entry_price else None
            ),
            peak_price=(
                float(position.peak_price) if position.peak_price else None
            ),
            trough_price=(
                float(position.trough_price) if position.trough_price else None
            ),
            pending_direction=(
                int(position.pending_direction)
                if position.pending_direction is not None
                else None
            ),
            signal_flip_date=position.signal_flip_date,
            consecutive_flip_days=position.consecutive_flip_days or 0,
            entry_atr=(
                float(position.entry_atr) if position.entry_atr else None
            ),
        )

        should_exit, final_direction, reason = self.exit_engine.evaluate(
            position=pos_data,
            prices=prices,
            new_signal_direction=new_direction,
            current_date=target_date,
        )

        current_price = float(prices["adj_close"].iloc[-1])
        atr = self.exit_engine.compute_atr(prices)

        updated_state = self.exit_engine.update_position_state(
            position=pos_data,
            current_price=current_price,
            new_direction=final_direction,
            current_date=target_date,
            atr=atr,
        )

        state_changed = await self._update_position_state(
            session, position, updated_state, new_direction, target_date
        )

        if should_exit:
            logger.info(f"EXIT: {position.symbol} - {reason}")
            await self._publish_exit_target(
                position.symbol, target_date, reason or "Exit triggered"
            )
            return True, state_changed

        return False, state_changed

    async def _update_position_state(
        self,
        session,
        position: PositionState,
        updated: PositionStateData,
        new_signal_direction: int,
        current_date: date,
    ) -> bool:
        """Update PositionState in database."""
        changed = False

        if updated.peak_price != (
            float(position.peak_price) if position.peak_price else None
        ):
            position.peak_price = (
                Decimal(str(updated.peak_price)) if updated.peak_price else None
            )
            changed = True

        if updated.trough_price != (
            float(position.trough_price) if position.trough_price else None
        ):
            position.trough_price = (
                Decimal(str(updated.trough_price))
                if updated.trough_price
                else None
            )
            changed = True

        if new_signal_direction != int(position.direction):
            if position.pending_direction != new_signal_direction:
                position.pending_direction = new_signal_direction
                position.signal_flip_date = current_date
                position.consecutive_flip_days = 1
                changed = True
            else:
                position.consecutive_flip_days = (
                    position.consecutive_flip_days or 0
                ) + 1
                changed = True
        else:
            if position.pending_direction is not None:
                position.pending_direction = None
                position.signal_flip_date = None
                position.consecutive_flip_days = 0
                changed = True

        if updated.direction == 0 and position.direction != 0:
            position.direction = 0
            position.entry_date = None
            position.entry_price = None
            position.peak_price = None
            position.trough_price = None
            position.entry_atr = None
            changed = True

        return changed

    async def _publish_exit_target(
        self, symbol: str, target_date: date, reason: str
    ) -> None:
        """Publish exit signal to targets stream."""
        if not self.redis:
            return

        await self.redis.xadd(
            StreamNames.TARGETS,
            {
                "event_type": "exit_triggered",
                "portfolio_id": self.portfolio_id,
                "symbol": symbol,
                "target_exposure": "0.0",
                "date": target_date.isoformat(),
                "reason": reason,
                "is_exit": "true",
            },
        )

        metrics.emit(
            metrics.CATEGORY_SIGNAL,
            "exit_signal",
            1,
            symbol=symbol,
            metadata={"reason": reason},
        )


async def main():
    """Run the exit consumer."""
    consumer = ExitConsumer()
    try:
        await consumer.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
