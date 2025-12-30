import asyncio
import logging
from typing import Dict, Any
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
from stocker.models.daily_bar import DailyBar

logger = logging.getLogger(__name__)

class LedgerConsumer(BaseStreamConsumer):
    """
    Listens for 'fills'.
    Updates 'holdings' (Quantity, Avg Cost).
    Updates 'portfolio_state' (Cash, PnL).
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.FILLS,
            consumer_group="accountants"
        )
    
    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        fill_id = data.get("fill_id")
        order_internal_id = data.get("order_id")
        symbol = data.get("symbol")
        side = data.get("side")
        qty_str = data.get("qty")
        price_str = data.get("price")
        
        if not all([symbol, side, qty_str, price_str]):
            return
            
        qty = float(qty_str)
        price = float(price_str)
        
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
            
            if holding:
                # Update Avg Cost
                # New Avg Cost = ((Old Qty * Old Cost) + (Trade Qty * Trade Price)) / New Qty
                # ONLY if increasing position? Standard accounting varies. 
                # Simple Weighted Average:
                total_cost = (float(holding.qty) * float(holding.cost_basis)) + (signed_qty * price)
                new_qty = float(holding.qty) + signed_qty
                
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

        logger.info(f"Ledger updated for {side} {qty} {symbol}")

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
