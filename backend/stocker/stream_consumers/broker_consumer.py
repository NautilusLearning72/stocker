import asyncio
import logging
import uuid
from typing import Dict, Any
from datetime import datetime, date

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.models.order import Order
from stocker.models.fill import Fill
from sqlalchemy.future import select

# We might need Alpaca Client here if execution is real
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

logger = logging.getLogger(__name__)

class BrokerConsumer(BaseStreamConsumer):
    """
    Listens for 'orders'.
    Executes trades (or papers trades) via Broker API (Alpaca).
    Publishes 'fills'.
    """
    
    def __init__(self):
        super().__init__(
            redis_url=settings.REDIS_URL,
            stream_name=StreamNames.ORDERS,
            consumer_group="brokers"
        )
        self.mode = settings.BROKER_MODE # 'paper' or 'live'
        
        # Initialize Alpaca Trading Client
        self.trading_client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=(settings.BROKER_MODE == "paper")
        )

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        order_internal_id = data.get("order_id")
        symbol = data.get("symbol")
        side = data.get("side")
        qty_str = data.get("qty")
        
        if not all([order_internal_id, symbol, side, qty_str]):
            return
            
        qty = float(qty_str)
        
        # 1. Update Order Status to PENDING
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.order_id == order_internal_id)
            result = await session.execute(stmt)
            order_record = result.scalar_one_or_none()
            
            if not order_record:
                logger.error(f"Order {order_internal_id} not found in DB")
                return
                
            if order_record.status != "NEW":
                logger.warning(f"Order {order_internal_id} is already {order_record.status}, skipping execution")
                return
                
            order_record.status = "PENDING_EXECUTION"
            await session.commit()
            
        # 2. Execute with Broker
        broker_order_id = None
        execution_price = 0.0
        filled_qty = 0
        
        try:
            # We assume Market Order for simplicity
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            
            submitted_order = self.trading_client.submit_order(req)
            broker_order_id = str(submitted_order.id)
            logger.info(f"Submitted order {order_internal_id} to Alpaca: {broker_order_id}")
            
            # 3. Wait for Fill (Simplified Synchrounous Simulation)
            # In a real event system, we would listen to a SEPARATE stream of "Broker Events" (Alpaca Webhook)
            # But for this simple Consumer, we might just mark it submitted.
            # HOWEVER, for the loop to complete in this "Backtest-like" or "Simple Live" architecture,
            # we need to generate fills to update holdings.
            
            # If we are in Paper/Live, we rely on Alpaca Webhooks or Polling to get the fill.
            # BUT, the implementation plan implies this consumer "Publishes 'fills'".
            # So let's assume immediate fill (optimistic) OR polling.
            # For robustness, let's just log submission. 
            # AND separate logic (maybe same consumer or different process) checks for fills.
            
            # CRITICAL SHORTCUT: For this version, let's assume "Instant Fill" at current price 
            # IF simple mode, otherwise we are blocked waiting for real fill.
            
            # Let's Implement "Optimistic Fill" for now to allow end-to-end flow testing
            # UNTIL we implement the Webhook Listener.
            # Fetch quote for fill price
            trade = self.trading_client.get_latest_trade(symbol)
            execution_price = float(trade.price)
            filled_qty = qty
            
        except Exception as e:
            logger.error(f"Broker execution failed: {e}")
            # Mark order failed
            async with AsyncSessionLocal() as session:
                stmt = select(Order).where(Order.order_id == order_internal_id)
                res = await session.execute(stmt)
                o = res.scalar_one_or_none()
                if o:
                    o.status = "FAILED"
                    await session.commit()
            return

        # 4. Generate Fill Record (Optimistic)
        fill_id = str(uuid.uuid4())
        
        async with AsyncSessionLocal() as session:
            # Update Order
            stmt = select(Order).where(Order.order_id == order_internal_id)
            res = await session.execute(stmt)
            o = res.scalar_one_or_none()
            if o:
                o.status = "FILLED"
                o.broker_order_id = broker_order_id
            
            # Create Fill
            new_fill = Fill(
                fill_id=fill_id,
                order_id=order_internal_id,
                date=date.today(),
                symbol=symbol,
                side=side,
                qty=filled_qty,
                price=execution_price,
                commission=0.0, # Alpaca free
                exchange="ALPACA"
            )
            session.add(new_fill)
            await session.commit()
            
        # 5. Publish 'fill_created'
        await self.redis.xadd(StreamNames.FILLS, {
            "event_type": "fill_created",
            "fill_id": fill_id,
            "order_id": order_internal_id,
            "symbol": symbol,
            "side": side,
            "qty": str(filled_qty),
            "price": str(execution_price)
        })
        logger.info(f"Filled {side} {filled_qty} {symbol} @ {execution_price}")

if __name__ == "__main__":
    async def main():
        consumer = BrokerConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
