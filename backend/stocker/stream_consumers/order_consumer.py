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
from stocker.core.metrics import metrics
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
        self.fractional_enabled = settings.FRACTIONAL_SIZING_ENABLED
        self.fractional_decimals = settings.FRACTIONAL_DECIMALS

    def _calculate_trade_qty(self, diff_qty: float) -> float:
        """
        Calculate trade quantity with fractional support.

        Returns rounded quantity based on settings.
        """
        abs_qty = abs(diff_qty)

        if self.fractional_enabled:
            # Round to configured decimals
            return round(abs_qty, self.fractional_decimals)
        else:
            # Integer sizing only
            return float(int(abs_qty))

    def _calculate_min_notional(self, nav: float, avg_volume: float = 0.0) -> float:
        """
        Calculate dynamic minimum notional based on mode.

        Args:
            nav: Portfolio net asset value
            avg_volume: Average daily volume in dollars (for liquidity mode)

        Returns:
            Minimum notional threshold in USD
        """
        mode = settings.MIN_NOTIONAL_MODE
        base = settings.MIN_NOTIONAL_USD

        if mode == "fixed":
            return base
        elif mode == "nav_scaled":
            # Scale by NAV: 5 bps of NAV
            nav_scaled = nav * settings.MIN_NOTIONAL_NAV_BPS / 10000
            return max(base, nav_scaled)
        elif mode == "liquidity_scaled" and avg_volume > 0:
            # Scale by liquidity: 0.1% of average daily volume
            liquidity_scaled = avg_volume * 0.001
            return max(base, liquidity_scaled)

        return base

    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        portfolio_id = data.get("portfolio_id")
        symbol = data.get("symbol")
        target_exposure_str = data.get("target_exposure")
        date_str = data.get("date")
        
        if not all([portfolio_id, symbol, target_exposure_str, date_str]):
            return
        
        # Check kill switch before generating any orders
        if await self.is_kill_switch_active(portfolio_id):
            logger.warning(f"Kill switch active - skipping order generation for {symbol}")
            metrics.order_skipped(symbol, "kill_switch_active", 0)
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
            # Target Notional = Target % * NAV
            target_notional = target_exposure * nav
            target_qty = target_notional / price

            # 4. Calculate Difference
            diff_qty = target_qty - current_qty
            diff_notional = diff_qty * price

            side = "BUY" if diff_qty > 0 else "SELL"
            qty_to_trade = self._calculate_trade_qty(diff_qty)

            # Calculate dynamic min notional
            avg_volume = float(bar.volume * bar.adj_close) if bar.volume else 0.0
            min_notional = self._calculate_min_notional(nav, avg_volume)

            if abs(diff_notional) < min_notional:
                logger.debug(f"Order for {symbol} too small (${diff_notional:.2f} < ${min_notional:.2f}), skipping")
                metrics.order_skipped(symbol, "below_min_notional", abs(diff_notional))
                return

            if qty_to_trade == 0:
                return

            # Prevent short selling: Don't sell what we don't have
            # (Unless short selling is explicitly enabled in settings)
            allow_short = settings.ALLOW_SHORT_SELLING
            if side == "SELL" and current_qty <= 0 and not allow_short:
                logger.info(f"Skipping short sell for {symbol} (current_qty={current_qty}, short selling disabled)")
                metrics.order_skipped(symbol, "short_selling_disabled", abs(diff_notional))
                return

            # Cap sell quantity to current holdings (can't sell more than we own)
            if side == "SELL" and not allow_short and qty_to_trade > current_qty:
                original_qty = qty_to_trade
                qty_to_trade = self._calculate_trade_qty(current_qty) if self.fractional_enabled else float(int(current_qty))
                logger.info(f"Capping {symbol} sell qty from {original_qty:.4f} to {qty_to_trade:.4f} (can't sell more than owned)")
                if qty_to_trade == 0:
                    return

            # 5. Check for existing order on the same date (idempotency)
            existing_order_stmt = select(Order).where(
                Order.portfolio_id == portfolio_id,
                Order.symbol == symbol,
                Order.date == target_date,
            ).order_by(Order.created_at.desc()).limit(1)
            existing_result = await session.execute(existing_order_stmt)
            existing_order = existing_result.scalar_one_or_none()

            if existing_order:
                logger.info(f"Order already exists for {symbol} on {target_date} (status={existing_order.status}), skipping")
                return

            # Emit sizing metric
            metrics.order_sizing(
                symbol=symbol,
                target_qty=abs(target_qty),
                actual_qty=qty_to_trade,
                fractional=self.fractional_enabled,
                min_notional=min_notional
            )

            # 6. Create Order
            order_id = str(uuid.uuid4())
            notional_value = qty_to_trade * price
            new_order = Order(
                order_id=order_id,
                portfolio_id=portfolio_id,
                date=target_date,
                symbol=symbol,
                side=side,
                qty=qty_to_trade,
                type="MARKET",  # Default to market on close/open
                status="NEW"
            )
            session.add(new_order)
            await session.commit()

            # Emit order created metric
            metrics.order_created(symbol, side, qty_to_trade, notional_value)

            # 7. Publish 'order_created'
            await self.redis.xadd(StreamNames.ORDERS, {
                "event_type": "order_created",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "qty": str(qty_to_trade),
                "type": "MARKET"
            })
            logger.info(f"Created {side} {qty_to_trade:.4f} {symbol} (Target: {target_exposure:.1%}, ${notional_value:.2f})")

if __name__ == "__main__":
    async def main():
        consumer = OrderConsumer()
        try:
            await consumer.start()
        except KeyboardInterrupt:
            await consumer.stop()
    
    asyncio.run(main())
