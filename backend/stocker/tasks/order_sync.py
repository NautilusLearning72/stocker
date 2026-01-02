"""
Order synchronization tasks.

Syncs pending MOO (Market-on-Open) order fills from Alpaca
after market open.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import List

from stocker.scheduler.celery_app import app
from stocker.core.database import AsyncSessionLocal
from stocker.core.config import settings
from stocker.core.redis import get_async_redis, StreamNames
from stocker.models.order import Order
from stocker.models.fill import Fill
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderStatus

logger = logging.getLogger(__name__)


async def _sync_moo_fills_async() -> dict:
    """
    Sync fills for ACCEPTED (MOO) orders from Alpaca.
    
    Called after market open to fetch actual fill prices
    for orders submitted the previous evening.
    """
    trading_client = TradingClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
        paper=(settings.BROKER_MODE == "paper")
    )
    
    synced_count = 0
    failed_count = 0
    
    async with AsyncSessionLocal() as session:
        # Find all ACCEPTED orders (MOO orders waiting for fill)
        stmt = select(Order).where(Order.status == "ACCEPTED")
        result = await session.execute(stmt)
        pending_orders: List[Order] = list(result.scalars().all())
        
        if not pending_orders:
            logger.info("No pending MOO orders to sync")
            return {"synced": 0, "failed": 0, "pending": 0}
        
        logger.info(f"Syncing {len(pending_orders)} pending MOO orders")
        
        redis = await get_async_redis()
        
        for order in pending_orders:
            if not order.broker_order_id:
                logger.warning(
                    f"Order {order.order_id} has no broker_order_id, skipping"
                )
                continue
            
            try:
                # Fetch order status from Alpaca
                alpaca_order = trading_client.get_order_by_id(order.broker_order_id)
                
                if alpaca_order.status == OrderStatus.FILLED:
                    # Order filled - create fill record
                    fill_price = float(alpaca_order.filled_avg_price)
                    filled_qty = float(alpaca_order.filled_qty)
                    fill_id = f"alpaca:{order.broker_order_id}"
                    fill_timestamp = datetime.now(timezone.utc)
                    
                    # Update order status
                    order.status = "FILLED"
                    
                    # Insert fill record (idempotent)
                    fill_stmt = insert(Fill).values(
                        fill_id=fill_id,
                        order_id=order.order_id,
                        date=fill_timestamp,
                        symbol=order.symbol,
                        side=order.side,
                        qty=filled_qty,
                        price=fill_price,
                        commission=0.0,
                        exchange="ALPACA"
                    ).on_conflict_do_nothing(index_elements=["fill_id"])
                    await session.execute(fill_stmt)
                    
                    logger.info(
                        f"MOO order {order.order_id} filled: "
                        f"{order.side} {filled_qty} {order.symbol} @ {fill_price}"
                    )
                    
                    # Publish fill event to Redis stream
                    await redis.xadd(StreamNames.FILLS, {
                        "event_type": "fill_created",
                        "fill_id": fill_id,
                        "order_id": str(order.order_id),
                        "symbol": order.symbol,
                        "side": order.side,
                        "qty": str(filled_qty),
                        "price": str(fill_price)
                    })
                    
                    synced_count += 1
                    
                elif alpaca_order.status in [
                    OrderStatus.CANCELED,
                    OrderStatus.EXPIRED,
                    OrderStatus.REJECTED
                ]:
                    # Order failed
                    order.status = str(alpaca_order.status).upper()
                    logger.warning(
                        f"MOO order {order.order_id} {alpaca_order.status}: "
                        f"{order.symbol}"
                    )
                    failed_count += 1
                    
                elif alpaca_order.status == OrderStatus.PARTIALLY_FILLED:
                    # Partial fill - update with what we have
                    fill_price = float(alpaca_order.filled_avg_price)
                    filled_qty = float(alpaca_order.filled_qty)
                    logger.info(
                        f"MOO order {order.order_id} partially filled: "
                        f"{filled_qty}/{order.qty} {order.symbol}"
                    )
                    # Keep as ACCEPTED, will sync again later
                    
                else:
                    # Still pending (NEW, ACCEPTED, PENDING_NEW)
                    logger.debug(
                        f"Order {order.order_id} still pending: {alpaca_order.status}"
                    )
                    
            except Exception as e:
                logger.error(
                    f"Error syncing order {order.order_id}: {e}"
                )
                failed_count += 1
        
        await session.commit()
        await redis.close()
    
    remaining = len(pending_orders) - synced_count - failed_count
    logger.info(
        f"MOO sync complete: {synced_count} filled, "
        f"{failed_count} failed, {remaining} still pending"
    )
    
    return {
        "synced": synced_count,
        "failed": failed_count,
        "pending": remaining
    }


@app.task(name="stocker.tasks.order_sync.sync_moo_fills")
def sync_moo_fills() -> dict:
    """
    Celery task to sync MOO order fills.
    
    Scheduled to run shortly after market open (9:35 AM ET)
    and periodically during the first hour to catch all fills.
    """
    return asyncio.run(_sync_moo_fills_async())
