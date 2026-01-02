import asyncio
import logging
import uuid
from typing import Dict, Any
from datetime import datetime, timezone

from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import StreamNames
from stocker.core.metrics import metrics
from stocker.models.order import Order
from stocker.models.fill import Fill
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert

# We might need Alpaca Client here if execution is real
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.common.exceptions import APIError

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
        self.execution_type = settings.ORDER_EXECUTION_TYPE  # 'moo' or 'market'
        
        # Initialize Alpaca Trading Client
        self.trading_client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            paper=(settings.BROKER_MODE == "paper")
        )
        # Initialize Alpaca Data Client for market data (latest trades, etc.)
        self.data_client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY
        )
        self.fractional_enabled = settings.FRACTIONAL_SIZING_ENABLED

    def _get_alpaca_position(self, symbol: str) -> float:
        """
        Get actual position quantity from Alpaca.
        
        Returns 0.0 if no position exists.
        """
        try:
            position = self.trading_client.get_open_position(symbol)
            return float(position.qty)
        except APIError as e:
            # Position not found means we don't hold any
            if "position does not exist" in str(e).lower():
                return 0.0
            raise
        except Exception:
            return 0.0

    def _validate_sell_order(self, symbol: str, qty: float) -> tuple[bool, float, str]:
        """
        Validate sell order against actual Alpaca position.
        
        For fractional orders, Alpaca doesn't allow short selling.
        This checks the actual broker position and adjusts quantity if needed.
        
        Returns:
            (is_valid, adjusted_qty, reason)
        """
        actual_position = self._get_alpaca_position(symbol)
        
        if actual_position <= 0:
            return False, 0.0, f"No position to sell (Alpaca position: {actual_position})"
        
        if qty > actual_position:
            # Cap to actual position to avoid short selling
            if self.fractional_enabled:
                # Fractional orders cannot short sell at all
                logger.warning(
                    f"Capping {symbol} sell from {qty:.4f} to {actual_position:.4f} "
                    f"(fractional short selling not allowed)"
                )
                return True, actual_position, "capped_to_position"
            else:
                # Integer orders: round down to available
                capped_qty = float(int(actual_position))
                if capped_qty <= 0:
                    return False, 0.0, f"Position too small for integer sell ({actual_position})"
                logger.warning(
                    f"Capping {symbol} sell from {qty:.0f} to {capped_qty:.0f}"
                )
                return True, capped_qty, "capped_to_position"
        
        return True, qty, "ok"

    def _is_market_open(self) -> tuple[bool, str]:
        """
        Check if the market is currently open for trading.
        
        Returns:
            (is_open, status_message)
        """
        try:
            clock = self.trading_client.get_clock()
            if clock.is_open:
                return True, "Market is open"
            else:
                next_open = clock.next_open.strftime("%Y-%m-%d %H:%M:%S %Z")
                next_close = clock.next_close.strftime("%Y-%m-%d %H:%M:%S %Z")
                return False, f"Market closed. Next open: {next_open}, Next close: {next_close}"
        except Exception as e:
            logger.warning(f"Failed to check market hours: {e}")
            # Default to allowing order attempt if we can't check
            return True, "Unable to verify market hours"

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        order_internal_id = data.get("order_id")
        symbol = data.get("symbol")
        side = data.get("side")
        qty_str = data.get("qty")
        
        if not all([order_internal_id, symbol, side, qty_str]):
            return
            
        qty = float(qty_str)

        try:
            order_uuid = uuid.UUID(order_internal_id)
        except ValueError:
            logger.error(f"Invalid order id: {order_internal_id}")
            return
        
        # 1. Update Order Status to PENDING
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.order_id == order_uuid)
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

        # 2. For SELL orders, validate against actual Alpaca position
        #    Alpaca doesn't allow short selling with fractional shares
        if side == "SELL":
            is_valid, adjusted_qty, reason = self._validate_sell_order(symbol, qty)
            
            if not is_valid:
                logger.warning(
                    f"Sell order for {symbol} rejected: {reason}"
                )
                # Emit rejection metric
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "rejected",
                    qty,
                    symbol=symbol,
                    metadata={"reason": reason, "side": side}
                )
                async with AsyncSessionLocal() as session:
                    stmt = select(Order).where(Order.order_id == order_uuid)
                    res = await session.execute(stmt)
                    o = res.scalar_one_or_none()
                    if o:
                        o.status = "REJECTED"
                        await session.commit()
                return
            
            if adjusted_qty != qty:
                logger.info(f"Adjusted {symbol} sell qty from {qty:.4f} to {adjusted_qty:.4f}")
                # Emit adjustment metric
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "qty_adjusted",
                    adjusted_qty,
                    symbol=symbol,
                    metadata={
                        "original_qty": qty,
                        "adjusted_qty": adjusted_qty,
                        "reason": reason
                    }
                )
                # Persist the adjusted qty to the Order
                async with AsyncSessionLocal() as session:
                    stmt = select(Order).where(Order.order_id == order_uuid)
                    res = await session.execute(stmt)
                    o = res.scalar_one_or_none()
                    if o:
                        o.qty = adjusted_qty
                        await session.commit()
                        logger.debug(f"Updated Order {order_internal_id} qty to {adjusted_qty}")
                qty = adjusted_qty

        # 3. Determine TimeInForce based on execution type and market hours
        market_open, market_status = self._is_market_open()
        
        if self.execution_type == "moo":
            # Market-on-Open: always use OPG (executes at next market open)
            time_in_force = TimeInForce.OPG
            if market_open:
                logger.info(f"MOO order for {symbol} will execute at next open (market currently open)")
            else:
                logger.info(f"MOO order for {symbol} queued for next open. {market_status}")
        else:
            # Immediate market order: requires market to be open
            if not market_open:
                logger.warning(f"Cannot execute immediate market order for {symbol}: {market_status}")
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "market_closed",
                    qty,
                    symbol=symbol,
                    metadata={"status": market_status, "side": side}
                )
                async with AsyncSessionLocal() as session:
                    stmt = select(Order).where(Order.order_id == order_uuid)
                    res = await session.execute(stmt)
                    o = res.scalar_one_or_none()
                    if o:
                        o.status = "PENDING"  # Will need manual retry or scheduled task
                        await session.commit()
                return
            time_in_force = TimeInForce.DAY
            
        # 4. Execute with Broker
        broker_order_id = None
        execution_price = 0.0
        filled_qty = 0
        
        try:
            # Submit order with appropriate TimeInForce
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
                time_in_force=time_in_force
            )

            submitted_order = self.trading_client.submit_order(req)
            broker_order_id = str(submitted_order.id)
            order_type_desc = "MOO" if time_in_force == TimeInForce.OPG else "MARKET"
            logger.info(f"Submitted {order_type_desc} order {order_internal_id} to Alpaca: {broker_order_id}")

            # Immediately persist broker_order_id to Order
            async with AsyncSessionLocal() as session:
                stmt = select(Order).where(Order.order_id == order_uuid)
                res = await session.execute(stmt)
                o = res.scalar_one_or_none()
                if o:
                    o.broker_order_id = broker_order_id
                    o.status = "SUBMITTED"
                    o.type = "MOO" if time_in_force == TimeInForce.OPG else "MARKET"
                    await session.commit()
                    logger.debug(f"Order {order_internal_id} submitted to broker: {broker_order_id}")

            # 5. Handle fill based on order type
            if time_in_force == TimeInForce.OPG:
                # MOO orders won't fill until market open - don't wait
                # A separate process (or webhook) will handle fill updates
                logger.info(
                    f"MOO order {broker_order_id} queued for next open. "
                    f"Fill will be processed when market opens."
                )
                # Mark as ACCEPTED (queued) rather than waiting for fill
                async with AsyncSessionLocal() as session:
                    stmt = select(Order).where(Order.order_id == order_uuid)
                    res = await session.execute(stmt)
                    o = res.scalar_one_or_none()
                    if o:
                        o.status = "ACCEPTED"  # Queued for next open
                        await session.commit()
                
                # Emit metric for visibility
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "moo_queued",
                    qty,
                    symbol=symbol,
                    metadata={
                        "broker_order_id": broker_order_id,
                        "side": side,
                        "execution_type": "moo"
                    }
                )
                return  # Don't wait for fill - will be handled by fill sync task
            
            # For immediate market orders, poll for fill
            execution_price, filled_qty = await self._wait_for_fill(
                broker_order_id, symbol, qty
            )
            
        except Exception as e:
            logger.error(f"Broker execution failed for {symbol}: {e}")
            # Emit failure metric
            metrics.emit(
                metrics.CATEGORY_ORDER,
                "execution_failed",
                qty,
                symbol=symbol,
                metadata={"error": str(e), "side": side}
            )
            # Mark order failed
            async with AsyncSessionLocal() as session:
                stmt = select(Order).where(Order.order_id == order_uuid)
                res = await session.execute(stmt)
                o = res.scalar_one_or_none()
                if o:
                    o.status = "FAILED"
                    await session.commit()
            return

        # 6. Generate Fill Record (idempotent insert)
        fill_id = f"alpaca:{broker_order_id}" if broker_order_id else f"local:{order_internal_id}"
        fill_timestamp = datetime.now(timezone.utc)
        
        async with AsyncSessionLocal() as session:
            # Update Order to FILLED
            stmt = select(Order).where(Order.order_id == order_uuid)
            res = await session.execute(stmt)
            o = res.scalar_one_or_none()
            if o:
                o.status = "FILLED"
                o.broker_order_id = broker_order_id
                logger.info(f"Order {order_internal_id} marked FILLED in database")
            else:
                logger.error(f"Order {order_internal_id} not found when trying to mark FILLED")
            
            # Insert fill once; safe to retry without duplicates.
            fill_stmt = insert(Fill).values(
                fill_id=fill_id,
                order_id=order_uuid,
                date=fill_timestamp,
                symbol=symbol,
                side=side,
                qty=filled_qty,
                price=execution_price,
                commission=0.0,
                exchange="ALPACA"
            ).on_conflict_do_nothing(index_elements=["fill_id"])
            result = await session.execute(fill_stmt)
            await session.commit()
            if result.rowcount == 1:
                logger.info(f"Fill {fill_id} persisted: {side} {filled_qty} {symbol} @ {execution_price}")
            else:
                logger.info(f"Fill {fill_id} already exists, skipping insert")

        # Emit fill metric for dashboard visibility
        notional = filled_qty * execution_price
        metrics.emit(
            metrics.CATEGORY_ORDER,
            "filled",
            notional,
            symbol=symbol,
            metadata={
                "side": side,
                "qty": filled_qty,
                "price": execution_price,
                "broker_order_id": broker_order_id
            }
        )
            
        # 7. Publish 'fill_created'
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
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = self.data_client.get_stock_latest_trade(request)
        trade = trades[symbol]
        return float(trade.price), expected_qty


if __name__ == "__main__":
    async def main():
        consumer = BrokerConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
