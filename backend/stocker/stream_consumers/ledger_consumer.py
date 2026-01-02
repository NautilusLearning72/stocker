import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.future import select
from sqlalchemy import delete, func

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.fill import Fill
from stocker.models.holding import Holding
from stocker.models.portfolio_state import PortfolioState
from stocker.models.order import Order
from stocker.models.position_state import PositionState
from stocker.models.daily_bar import DailyBar
from sqlalchemy.dialects.postgresql import insert as pg_insert

logger = logging.getLogger(__name__)

class LedgerConsumer(BaseStreamConsumer):
    """
    Listens for 'fills'.
    Updates 'holdings' (Quantity, Avg Cost).
    Updates 'portfolio_state' (Cash, PnL).
    
    Idempotency: Tracks processed fills in Redis to prevent double-counting.
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.FILLS,
            consumer_group="accountants"
        )
        self._processed_fills_key = "ledger:processed_fills"
        self._processed_fills_ttl_sec = 60 * 60 * 24 * 7

    async def _is_fill_processed(self, fill_id: str) -> bool:
        """Check if fill has already been processed."""
        if not self.redis or not fill_id:
            return False
        return await self.redis.sismember(self._processed_fills_key, fill_id)

    async def _mark_fill_processed(self, fill_id: str) -> None:
        """Mark fill as processed to prevent duplicate processing."""
        if self.redis and fill_id:
            await self.redis.sadd(self._processed_fills_key, fill_id)
            await self.redis.expire(self._processed_fills_key, self._processed_fills_ttl_sec)

    def _direction_from_qty(self, qty: float) -> int:
        if qty > 0:
            return 1
        if qty < 0:
            return -1
        return 0

    async def _update_position_state(
        self,
        session,
        portfolio_id: str,
        symbol: str,
        fill_date: date,
        trade_price: float,
        old_qty: float,
        new_qty: float,
        cost_basis: Optional[float],
    ) -> None:
        old_direction = self._direction_from_qty(old_qty)
        new_direction = self._direction_from_qty(new_qty)

        stmt = select(PositionState).where(
            PositionState.portfolio_id == portfolio_id,
            PositionState.symbol == symbol,
        )
        result = await session.execute(stmt)
        position = result.scalar_one_or_none()

        if new_direction == 0:
            if not position:
                return
            position.direction = 0
            position.entry_date = None
            position.entry_price = None
            position.peak_price = None
            position.trough_price = None
            position.entry_atr = None
            position.pending_direction = None
            position.signal_flip_date = None
            position.consecutive_flip_days = 0
            return

        is_new_entry = old_direction == 0
        is_flip = old_direction != 0 and new_direction != old_direction

        if not position:
            position = PositionState(
                portfolio_id=portfolio_id,
                symbol=symbol,
                direction=new_direction,
                entry_date=fill_date,
                entry_price=trade_price,
                peak_price=trade_price,
                trough_price=trade_price,
                entry_atr=None,
                pending_direction=None,
                signal_flip_date=None,
                consecutive_flip_days=0,
            )
            session.add(position)
            return

        if is_new_entry or is_flip:
            position.direction = new_direction
            position.entry_date = fill_date
            position.entry_price = trade_price
            position.peak_price = trade_price
            position.trough_price = trade_price
            position.entry_atr = None
            position.pending_direction = None
            position.signal_flip_date = None
            position.consecutive_flip_days = 0
            return

        position.direction = new_direction
        if cost_basis is not None:
            position.entry_price = cost_basis

        if new_direction == 1:
            if position.peak_price is None or trade_price > float(position.peak_price):
                position.peak_price = trade_price
        else:
            if position.trough_price is None or trade_price < float(position.trough_price):
                position.trough_price = trade_price
    
    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        fill_id = data.get("fill_id")
        order_internal_id = data.get("order_id")
        symbol = data.get("symbol")
        side = data.get("side")
        qty_str = data.get("qty")
        price_str = data.get("price")
        
        if not all([symbol, side, qty_str, price_str]):
            logger.warning(f"Incomplete fill data received: {data}")
            return

        # Idempotency check: skip if already processed
        if fill_id and await self._is_fill_processed(fill_id):
            logger.debug(f"Fill {fill_id} already processed, skipping")
            return
            
        qty = float(qty_str)
        price = float(price_str)
        
        fill_date = date.today()
        # Verify fill exists in database (source of truth)
        async with AsyncSessionLocal() as session:
            if fill_id:
                fill_stmt = select(Fill).where(Fill.fill_id == fill_id)
                fill_result = await session.execute(fill_stmt)
                db_fill = fill_result.scalar_one_or_none()
                
                if db_fill:
                    # Use database values as source of truth
                    qty = float(db_fill.qty)
                    price = float(db_fill.price)
                    symbol = db_fill.symbol
                    side = db_fill.side
                    fill_date = db_fill.date.date()
                    logger.debug(f"Verified fill {fill_id} from database: {side} {qty} {symbol} @ {price}")
                else:
                    logger.warning(f"Fill {fill_id} not found in database, using stream data")
        
        # Determine Portfolio ID from Order
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.order_id == order_internal_id)
            result = await session.execute(stmt)
            order = result.scalar_one_or_none()
            
            portfolio_id = order.portfolio_id if order else "main"
            
            # 1. Update Holdings
            stmt = select(Holding).where(
                Holding.portfolio_id == portfolio_id,
                Holding.symbol == symbol
            )
            result = await session.execute(stmt)
            holding = result.scalar_one_or_none()
            
            signed_qty = qty if side == "BUY" else -qty
            trade_value = qty * price
            old_qty = float(holding.qty) if holding else 0.0
            new_qty = old_qty + signed_qty
            current_cost_basis: Optional[float] = None
            
            if holding:
                # Update Avg Cost
                # New Avg Cost = ((Old Qty * Old Cost) + (Trade Qty * Trade Price)) / New Qty
                # ONLY if increasing position? Standard accounting varies. 
                # Simple Weighted Average:
                total_cost = (float(holding.qty) * float(holding.cost_basis)) + (signed_qty * price)
                
                if new_qty == 0:
                     # Closed position
                     await session.delete(holding)
                else:
                     # Update
                     holding.qty = new_qty
                     # If closing (reducing), cost basis usually stays same (FIFO/LIFO logic complex)
                     # Simplified: Re-calc average cost on entry, keep same on exit?
                     if (side == "BUY" and holding.qty > 0) or (side == "SELL" and holding.qty < 0):
                         # Adding to position
                         holding.cost_basis = total_cost / new_qty
                     # Else reducing, cost basis preserved
                     current_cost_basis = float(holding.cost_basis)
            else:
                 # New Position
                 new_holding = Holding(
                     portfolio_id=portfolio_id,
                     date=date.today(),
                     symbol=symbol,
                     qty=signed_qty,
                     cost_basis=price,
                     market_value=trade_value # Approx
                 )
                 session.add(new_holding)
                 current_cost_basis = price

            # 1b. Update PositionState for exit rules
            await self._update_position_state(
                session=session,
                portfolio_id=portfolio_id,
                symbol=symbol,
                fill_date=fill_date,
                trade_price=price,
                old_qty=old_qty,
                new_qty=new_qty,
                cost_basis=current_cost_basis,
            )
            
            # 2. Update Cash
            # Fetch latest state
            stmt = select(PortfolioState).where(
                PortfolioState.portfolio_id == portfolio_id
            ).order_by(PortfolioState.date.desc()).limit(1)
            result = await session.execute(stmt)
            state = result.scalar_one_or_none()
            
            if state:
                # Deduct cost (BUY) or Add proceeds (SELL)
                cash_change = -trade_value if side == "BUY" else trade_value
                # Subtract commission? (Simulate 0 for now)

                state.cash = float(state.cash) + cash_change
                state.updated_at = datetime.utcnow()

            await session.commit()

        # Mark fill as processed for idempotency
        if fill_id:
            await self._mark_fill_processed(fill_id)

        logger.info(f"Ledger updated for {side} {qty} {symbol} @ {price} (fill_id={fill_id})")

        # 3. Recalculate NAV and publish to portfolio-state stream for MonitorConsumer
        await self._publish_portfolio_state(portfolio_id)

    async def _publish_portfolio_state(self, portfolio_id: str) -> None:
        """Recalculate portfolio metrics and publish to portfolio-state stream."""
        async with AsyncSessionLocal() as session:
            # Get current holdings
            stmt = select(Holding).where(Holding.portfolio_id == portfolio_id)
            result = await session.execute(stmt)
            holdings = result.scalars().all()

            # Get latest prices for holdings to calculate market values
            total_market_value = Decimal("0")
            for holding in holdings:
                # Get latest price for symbol
                price_stmt = select(DailyBar.adj_close).where(
                    DailyBar.symbol == holding.symbol
                ).order_by(DailyBar.date.desc()).limit(1)
                price_result = await session.execute(price_stmt)
                latest_price = price_result.scalar()

                if latest_price:
                    market_value = Decimal(str(holding.qty)) * Decimal(str(latest_price))
                    total_market_value += market_value
                    # Update holding market value
                    holding.market_value = float(market_value)

            # Get current portfolio state
            state_stmt = select(PortfolioState).where(
                PortfolioState.portfolio_id == portfolio_id
            ).order_by(PortfolioState.date.desc()).limit(1)
            state_result = await session.execute(state_stmt)
            state = state_result.scalar_one_or_none()

            if not state:
                logger.warning(f"No portfolio state found for {portfolio_id}")
                return

            # Calculate NAV = cash + market value of holdings
            cash = Decimal(str(state.cash))
            nav = cash + total_market_value

            # Calculate unrealized PnL
            total_cost_basis = sum(
                Decimal(str(h.qty)) * Decimal(str(h.cost_basis))
                for h in holdings
            )
            unrealized_pnl = total_market_value - total_cost_basis

            # Calculate drawdown from high water mark
            hwm = Decimal(str(state.high_water_mark))
            if nav > hwm:
                hwm = nav
                state.high_water_mark = float(hwm)

            drawdown = float((hwm - nav) / hwm) if hwm > 0 else 0.0

            # Calculate gross/net exposure
            gross_exposure = Decimal("0")
            net_exposure = Decimal("0")
            for holding in holdings:
                mv = Decimal(str(holding.market_value or 0))
                gross_exposure += abs(mv)
                net_exposure += mv

            if nav > 0:
                gross_exposure_pct = float(gross_exposure / nav)
                net_exposure_pct = float(net_exposure / nav)
            else:
                gross_exposure_pct = 0.0
                net_exposure_pct = 0.0

            # Update state in DB
            state.nav = float(nav)
            state.unrealized_pnl = float(unrealized_pnl)
            state.drawdown = float(drawdown)
            state.gross_exposure = gross_exposure_pct
            state.net_exposure = net_exposure_pct
            state.updated_at = datetime.utcnow()

            await session.commit()

            # Publish to portfolio-state stream for MonitorConsumer
            if self.redis:
                await self.redis.xadd(StreamNames.PORTFOLIO_STATE, {
                    "event_type": "state_update",
                    "portfolio_id": portfolio_id,
                    "date": str(date.today()),
                    "nav": str(nav),
                    "cash": str(cash),
                    "drawdown": str(drawdown),
                    "gross_exposure": str(gross_exposure_pct),
                    "net_exposure": str(net_exposure_pct),
                    "unrealized_pnl": str(unrealized_pnl),
                    "high_water_mark": str(hwm)
                })
                logger.info(f"Published portfolio state: NAV={nav}, drawdown={drawdown:.2%}")
            else:
                logger.warning("Redis not connected, cannot publish portfolio state")

if __name__ == "__main__":
    async def main():
        consumer = LedgerConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
