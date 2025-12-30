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

            # 3. Poll for actual fill from Alpaca
            # Market orders typically fill immediately, but we should verify
            execution_price, filled_qty = await self._wait_for_fill(
                broker_order_id, symbol, qty
            )
            
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

    async def _wait_for_fill(
        self,
        broker_order_id: str,
        symbol: str,
        expected_qty: float,
        max_wait_seconds: int = 30,
        poll_interval: float = 0.5
    ) -> tuple[float, float]:
        """
        Poll Alpaca for order fill status.

        Returns (fill_price, filled_qty).
        Raises Exception if order not filled within timeout.
        """
        import time
        from alpaca.trading.enums import OrderStatus

        start_time = time.time()

        while (time.time() - start_time) < max_wait_seconds:
            try:
                # Get order status from Alpaca
                alpaca_order = self.trading_client.get_order_by_id(broker_order_id)

                if alpaca_order.status == OrderStatus.FILLED:
                    # Use actual fill price from Alpaca
                    fill_price = float(alpaca_order.filled_avg_price)
                    filled_qty = float(alpaca_order.filled_qty)
                    logger.info(
                        f"Order {broker_order_id} filled: {filled_qty} @ {fill_price} "
                        f"(waited {time.time() - start_time:.1f}s)"
                    )
                    return fill_price, filled_qty

                elif alpaca_order.status in [
                    OrderStatus.CANCELED,
                    OrderStatus.EXPIRED,
                    OrderStatus.REJECTED
                ]:
                    raise Exception(
                        f"Order {broker_order_id} {alpaca_order.status}: "
                        f"{alpaca_order.status}"
                    )

                elif alpaca_order.status == OrderStatus.PARTIALLY_FILLED:
                    # For partial fills, we could handle differently
                    # For now, keep waiting for full fill
                    logger.info(
                        f"Order {broker_order_id} partially filled: "
                        f"{alpaca_order.filled_qty}/{expected_qty}"
                    )

                # Order still pending, wait and retry
                await asyncio.sleep(poll_interval)

            except Exception as e:
                if "order not found" in str(e).lower():
                    # Order might not be immediately visible, retry
                    await asyncio.sleep(poll_interval)
                    continue
                raise

        # Timeout - fall back to latest trade price with warning
        logger.warning(
            f"Order {broker_order_id} fill timeout after {max_wait_seconds}s, "
            f"using latest trade price as fallback"
        )
        trade = self.trading_client.get_latest_trade(symbol)
        return float(trade.price), expected_qty


if __name__ == "__main__":
    async def main():
        consumer = BrokerConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
