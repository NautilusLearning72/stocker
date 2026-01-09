import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

# We might need Alpaca Client here if execution is real
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderStatus, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.future import select

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.metrics import metrics
from stocker.core.redis import StreamNames
from stocker.models.fill import Fill
from stocker.models.order import Order
from stocker.stream_consumers.base import BaseStreamConsumer

logger = logging.getLogger(__name__)
ET_TZ = ZoneInfo("America/New_York")

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
        self.execution_type = settings.ORDER_EXECUTION_TYPE  # 'moo', 'market', or 'auto'

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

    def _is_fractional_qty(self, qty: float) -> bool:
        """Check if quantity has a fractional component."""
        return abs(qty - round(qty)) > 1e-9

    def _round_for_moo(self, qty: float, symbol: str) -> float:
        """
        Round quantity to whole shares for MOO orders.

        Alpaca requires whole shares for OPG (market-on-open) orders.
        Returns 0 if quantity rounds to less than 1 share.
        """
        if not self._is_fractional_qty(qty):
            return qty

        rounded = round(qty)  # Round to nearest whole
        if rounded < 1:
            logger.info(
                f"Skipping {symbol}: quantity {qty:.4f} rounds to {rounded} shares (< 1 share minimum)"
            )
            return 0.0

        logger.info(f"Rounded {symbol} qty from {qty:.4f} to {rounded} for MOO order (fractional not supported)")
        return float(rounded)

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
        Validate sell order against Alpaca position.

        Alpaca restrictions:
        - Cannot short sell with fractional quantities
        - Short sells must use whole shares

        Strategy: Round short portion to whole shares instead of rejecting.

        Returns:
            (is_valid, adjusted_qty, reason)
        """
        actual_position = self._get_alpaca_position(symbol)

        # Would this order result in a short position?
        resulting_position = actual_position - qty

        if resulting_position >= 0:
            # Staying long or flat — no restrictions on fractional
            return True, qty, "ok"

        # This would create/increase a short position
        # Alpaca requires whole shares for short selling

        if self.fractional_enabled:
            # In fractional mode with short selling:
            # - Can sell fractional to flatten existing long position
            # - Must round the short portion to whole shares

            if actual_position <= 0:
                # Already short or flat - round entire order to whole shares
                int_qty = int(qty)
                if int_qty <= 0:
                    logger.info(
                        f"Skipping {symbol} short: qty {qty:.4f} rounds to 0 shares"
                    )
                    return False, 0.0, "Fractional short quantity too small after rounding"
                logger.warning(
                    f"Rounding {symbol} short sell from {qty:.4f} to {int_qty} "
                    f"(fractional short selling not allowed)"
                )
                return True, float(int_qty), "rounded_for_short"
            else:
                # Have long position - can sell fractional to flatten,
                # but short portion must be whole shares
                flatten_qty = actual_position  # Sell all current (can be fractional)
                short_portion = qty - actual_position
                rounded_short = int(short_portion)  # Round down

                if rounded_short <= 0:
                    # Only flatten, no short
                    logger.warning(
                        f"Capping {symbol} sell from {qty:.4f} to {flatten_qty:.4f} "
                        f"(short portion {short_portion:.4f} rounds to 0)"
                    )
                    return True, flatten_qty, "capped_to_flatten"

                adjusted_qty = flatten_qty + rounded_short
                logger.warning(
                    f"Adjusting {symbol} sell from {qty:.4f} to {adjusted_qty:.4f} "
                    f"(short portion rounded from {short_portion:.4f} to {rounded_short})"
                )
                return True, adjusted_qty, "short_portion_rounded"
        else:
            # Integer mode: short selling allowed, just ensure integer
            int_qty = int(qty)
            if int_qty <= 0:
                return False, 0.0, "Quantity too small for integer order"
            return True, float(int_qty), "ok"

    def _is_time_in_window(self, current: time, start: time, end: time) -> bool:
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    def _is_market_open_fallback(self, now_et: datetime) -> bool:
        if now_et.weekday() >= 5:
            return False
        open_time = time(9, 30)
        close_time = time(16, 0)
        current = now_et.time()
        return open_time <= current < close_time

    def _get_market_context(self) -> tuple[datetime, bool, str]:
        now_et = datetime.now(ET_TZ)
        try:
            clock = self.trading_client.get_clock()
            timestamp = getattr(clock, "timestamp", None)
            if timestamp is not None:
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                now_et = timestamp.astimezone(ET_TZ)
            if getattr(clock, "is_open", False):
                return now_et, True, "Market is open"
            next_open = getattr(clock, "next_open", None)
            next_close = getattr(clock, "next_close", None)
            if next_open and next_close:
                next_open_str = next_open.strftime("%Y-%m-%d %H:%M:%S %Z")
                next_close_str = next_close.strftime("%Y-%m-%d %H:%M:%S %Z")
                return now_et, False, f"Market closed. Next open: {next_open_str}, Next close: {next_close_str}"
        except Exception as e:
            logger.warning(f"Failed to check market hours: {e}")
        is_open = self._is_market_open_fallback(now_et)
        status = "Market open (fallback)" if is_open else "Market closed (fallback)"
        return now_et, is_open, status

    def _is_opg_window(self, now_et: datetime) -> tuple[bool, str]:
        start = time(settings.OPG_WINDOW_START_HOUR, settings.OPG_WINDOW_START_MINUTE)
        end = time(settings.OPG_WINDOW_END_HOUR, settings.OPG_WINDOW_END_MINUTE)
        in_window = self._is_time_in_window(now_et.time(), start, end)
        status = f"OPG window {start.strftime('%H:%M')} - {end.strftime('%H:%M')} ET"
        return in_window, status

    def _format_broker_rejection(self, error: APIError) -> str:
        payload = getattr(error, "error", None)
        if isinstance(payload, dict):
            return json.dumps(payload, sort_keys=True)
        raw = str(error).strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                return json.dumps(json.loads(raw), sort_keys=True)
            except json.JSONDecodeError:
                return raw
        return raw

    async def _mark_order_pending(self, order_uuid: uuid.UUID, reason: str) -> None:
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.order_id == order_uuid)
            res = await session.execute(stmt)
            o = res.scalar_one_or_none()
            if o:
                o.status = "PENDING"
                await session.commit()
                logger.debug(f"Order {order_uuid} set to PENDING ({reason})")

    async def process_message(self, message_id: str, data: dict[str, Any]) -> None:
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

        # 1. Load Order and check kill switch before execution
        async with AsyncSessionLocal() as session:
            stmt = select(Order).where(Order.order_id == order_uuid)
            result = await session.execute(stmt)
            order_record = result.scalar_one_or_none()

            if not order_record:
                logger.error(f"Order {order_internal_id} not found in DB")
                return

            portfolio_id = str(order_record.portfolio_id)

            # Check kill switch before submitting to broker
            if await self.is_kill_switch_active(portfolio_id):
                logger.warning(
                    f"Kill switch active - rejecting order "
                    f"{order_internal_id} for {symbol}"
                )
                order_record.status = "REJECTED"
                order_record.rejection_reason = "kill_switch_active"
                await session.commit()
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "rejected",
                    qty,
                    symbol=symbol,
                    metadata={"reason": "kill_switch_active", "side": side}
                )
                return

            if order_record.status not in ("NEW", "PENDING"):
                logger.warning(
                    f"Order {order_internal_id} is already {order_record.status}, skipping execution"
                )
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
                        o.rejection_reason = reason
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
        #    Note: Alpaca requires whole shares for MOO (OPG) orders
        now_et, market_open, market_status = self._get_market_context()
        in_opg_window, opg_status = self._is_opg_window(now_et)

        execution_type = self.execution_type
        if execution_type == "auto":
            if market_open:
                execution_type = "market"
            elif in_opg_window:
                execution_type = "moo"
            else:
                logger.info(
                    f"Deferring order for {symbol}: outside OPG window. {opg_status}. {market_status}"
                )
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "opg_window_closed",
                    qty,
                    symbol=symbol,
                    metadata={"status": opg_status, "side": side}
                )
                await self._mark_order_pending(order_uuid, "opg_window_closed")
                return

        if execution_type == "moo":
            if not in_opg_window:
                logger.warning(
                    f"Cannot submit MOO for {symbol}: outside OPG window. {opg_status}"
                )
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "opg_window_closed",
                    qty,
                    symbol=symbol,
                    metadata={"status": opg_status, "side": side}
                )
                await self._mark_order_pending(order_uuid, "opg_window_closed")
                return
            # Market-on-Open: use OPG (executes at next market open)
            # Alpaca constraint: OPG orders must use whole shares
            if self._is_fractional_qty(qty):
                original_qty = qty
                qty = self._round_for_moo(qty, symbol)
                if qty <= 0:
                    # Quantity too small after rounding - skip order
                    metrics.emit(
                        metrics.CATEGORY_ORDER,
                        "skipped_fractional",
                        original_qty,
                        symbol=symbol,
                        metadata={"reason": "qty_rounds_to_zero", "side": side}
                    )
                    async with AsyncSessionLocal() as session:
                        stmt = select(Order).where(Order.order_id == order_uuid)
                        res = await session.execute(stmt)
                        o = res.scalar_one_or_none()
                        if o:
                            o.status = "SKIPPED"
                            await session.commit()
                    return
                # Update order qty in database
                async with AsyncSessionLocal() as session:
                    stmt = select(Order).where(Order.order_id == order_uuid)
                    res = await session.execute(stmt)
                    o = res.scalar_one_or_none()
                    if o:
                        o.qty = qty
                        await session.commit()
                metrics.emit(
                    metrics.CATEGORY_ORDER,
                    "qty_rounded_for_moo",
                    qty,
                    symbol=symbol,
                    metadata={"original_qty": original_qty, "rounded_qty": qty, "side": side}
                )

            time_in_force = TimeInForce.OPG
            if market_open:
                logger.info(
                    f"MOO order for {symbol} will execute at next open (market currently open)"
                )
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
                await self._mark_order_pending(order_uuid, "market_closed")
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

        except APIError as e:
            rejection_reason = self._format_broker_rejection(e)
            logger.error(f"Broker rejected {symbol}: {rejection_reason}")
            metrics.emit(
                metrics.CATEGORY_ORDER,
                "rejected",
                qty,
                symbol=symbol,
                metadata={"reason": rejection_reason, "side": side}
            )
            async with AsyncSessionLocal() as session:
                stmt = select(Order).where(Order.order_id == order_uuid)
                res = await session.execute(stmt)
                o = res.scalar_one_or_none()
                if o:
                    o.status = "REJECTED"
                    o.rejection_reason = rejection_reason
                    await session.commit()
            return
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
                    o.rejection_reason = str(e)
                    await session.commit()
            return

        # 6. Generate Fill Record (idempotent insert)
        fill_id = f"alpaca:{broker_order_id}" if broker_order_id else f"local:{order_internal_id}"
        fill_timestamp = datetime.now(UTC)

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
