import asyncio
import logging
import uuid
from typing import Dict, Any
from datetime import date
from sqlalchemy.future import select

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.target_exposure import TargetExposure
from stocker.models.holding import Holding
from stocker.models.portfolio_state import PortfolioState
from stocker.models.order import Order

logger = logging.getLogger(__name__)

class OrderConsumer(BaseStreamConsumer):
    """
    Listens for 'targets' stream.
    Diffs target vs current holding.
    Generates 'orders' if difference > minimum_notional.
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.TARGETS,
            consumer_group="order-managers"
        )
        self.min_notional = settings.MIN_NOTIONAL_USD

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        portfolio_id = data.get("portfolio_id")
        symbol = data.get("symbol")
        target_exposure_str = data.get("target_exposure")
        date_str = data.get("date")
        
        if not all([portfolio_id, symbol, target_exposure_str, date_str]):
            return
            
        target_exposure = float(target_exposure_str)
        target_date = date.fromisoformat(date_str)
        
        async with AsyncSessionLocal() as session:
            # 1. Get Current Portfolio Value (NAV)
            # Use latest known NAV
            stmt = select(PortfolioState).where(
                PortfolioState.portfolio_id == portfolio_id
            ).order_by(PortfolioState.date.desc()).limit(1)
            result = await session.execute(stmt)
            state = result.scalar_one_or_none()
            
            nav = float(state.nav) if state else 100000.0 # Default/Seed capital? 
            
            # 2. Get Current Holding
            # We need the holding for *today* (or latest)
            stmt = select(Holding).where(
                Holding.portfolio_id == portfolio_id,
                Holding.symbol == symbol
            ).order_by(Holding.date.desc()).limit(1)
            result = await session.execute(stmt)
            holding = result.scalar_one_or_none()
            
            current_qty = float(holding.qty) if holding else 0.0
            
            # Estimate current price? We need price to convert exposure % to Qty
            # We can use DailyBar (latest available)
            # Ideally OrderConsumer checks real-time price, but for now we use yesterday's close or similar
            from stocker.models.daily_bar import DailyBar
            stmt = select(DailyBar).where(
                DailyBar.symbol == symbol
            ).order_by(DailyBar.date.desc()).limit(1)
            result = await session.execute(stmt)
            bar = result.scalar_one_or_none()
            
            if not bar:
                logger.warning(f"No price found for {symbol}, cannot calculate order qty")
                return
                
            price = float(bar.adj_close)
            
            # 3. Calculate Target Qty
            # Target Isional = Target % * NAV
            target_notional = target_exposure * nav
            target_qty = target_notional / price
            
            # 4. Calculate Difference
            diff_qty = target_qty - current_qty
            diff_notional = diff_qty * price
            
            side = "BUY" if diff_qty > 0 else "SELL"
            qty_to_trade = int(abs(diff_qty)) # Integers only for now? 
            # Or handle fractional if broker supports. Alpaca supports fractional.
            # Let's stick to integer for simplicity unless fractional is standard?
            # Alpaca supports fractional but safer to start with integers for "legacy" feel or simplicity
            # Actually, standard logic often rounds down/nearest.
            
            if abs(diff_notional) < self.min_notional:
                logger.info(f"Order for {symbol} too small (${diff_notional:.2f} < ${self.min_notional}), skipping")
                return
                
            if qty_to_trade == 0:
                return

            # 5. Create Order
            # Check if pending order exists? (Complexity: Omitted for now)
            
            order_id = str(uuid.uuid4())
            new_order = Order(
                order_id=order_id,
                portfolio_id=portfolio_id,
                date=target_date,
                symbol=symbol,
                side=side,
                qty=qty_to_trade,
                type="MARKET", # Default to market on close/open
                status="NEW" 
            )
            session.add(new_order)
            await session.commit()
            
            # 6. Publish 'order_created'
            await self.redis.xadd(StreamNames.ORDERS, {
                "event_type": "order_created",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": str(qty_to_trade),
                "type": "MARKET"
            })
            logger.info(f"Created {side} {qty_to_trade} {symbol} (Target: {target_exposure:.1%})")

if __name__ == "__main__":
    async def main():
        consumer = OrderConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
