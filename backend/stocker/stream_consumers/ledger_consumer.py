import asyncio
import logging
from typing import Dict, Any
from datetime import date, datetime
from sqlalchemy.future import select
from sqlalchemy import delete

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.fill import Fill
from stocker.models.holding import Holding
from stocker.models.portfolio_state import PortfolioState
from stocker.models.order import Order

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

if __name__ == "__main__":
    consumer = LedgerConsumer()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(consumer.start())
    except KeyboardInterrupt:
        loop.run_until_complete(consumer.stop())
