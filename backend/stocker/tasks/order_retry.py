"""
Retry pending orders when execution windows reopen.
"""
import asyncio
import logging
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from alpaca.trading.client import TradingClient
from sqlalchemy import select

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.core.redis import get_async_redis, StreamNames
from stocker.models.order import Order
from stocker.scheduler.celery_app import app

logger = logging.getLogger(__name__)
ET_TZ = ZoneInfo("America/New_York")


def _is_time_in_window(current: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _is_market_open_fallback(now_et: datetime) -> bool:
    if now_et.weekday() >= 5:
        return False
    open_time = time(9, 30)
    close_time = time(16, 0)
    current = now_et.time()
    return open_time <= current < close_time


def _get_market_context(trading_client: TradingClient) -> tuple[datetime, bool, str]:
    now_et = datetime.now(ET_TZ)
    try:
        clock = trading_client.get_clock()
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
    is_open = _is_market_open_fallback(now_et)
    status = "Market open (fallback)" if is_open else "Market closed (fallback)"
    return now_et, is_open, status


def _is_opg_window(now_et: datetime) -> bool:
    start = time(settings.OPG_WINDOW_START_HOUR, settings.OPG_WINDOW_START_MINUTE)
    end = time(settings.OPG_WINDOW_END_HOUR, settings.OPG_WINDOW_END_MINUTE)
    return _is_time_in_window(now_et.time(), start, end)


async def _retry_pending_orders_async() -> dict:
    trading_client = TradingClient(
        api_key=settings.ALPACA_API_KEY,
        secret_key=settings.ALPACA_SECRET_KEY,
        paper=(settings.BROKER_MODE == "paper"),
    )

    now_et, market_open, market_status = _get_market_context(trading_client)
    in_opg_window = _is_opg_window(now_et)

    execution_type = settings.ORDER_EXECUTION_TYPE
    if execution_type == "moo":
        allow_retry = in_opg_window
    elif execution_type == "market":
        allow_retry = market_open
    else:
        allow_retry = True

    if not allow_retry:
        logger.info(
            "Skipping pending order retry: execution window closed. "
            f"{market_status}"
        )
        return {
            "queued": 0,
            "pending": 0,
            "market_open": market_open,
            "opg_window": in_opg_window,
        }

    async with AsyncSessionLocal() as session:
        stmt = select(Order).where(Order.status == "PENDING")
        result = await session.execute(stmt)
        pending_orders = list(result.scalars().all())

    if not pending_orders:
        return {
            "queued": 0,
            "pending": 0,
            "market_open": market_open,
            "opg_window": in_opg_window,
        }

    redis = await get_async_redis()
    queued = 0
    for order in pending_orders:
        await redis.xadd(StreamNames.ORDERS, {
            "event_type": "order_retry",
            "order_id": str(order.order_id),
            "symbol": order.symbol,
            "side": order.side,
            "qty": str(order.qty),
            "type": order.type or "",
        })
        queued += 1

    await redis.close()
    logger.info(f"Requeued {queued} pending orders")

    return {
        "queued": queued,
        "pending": len(pending_orders),
        "market_open": market_open,
        "opg_window": in_opg_window,
    }


@app.task(name="stocker.tasks.order_retry.retry_pending_orders")
def retry_pending_orders() -> dict:
    """
    Celery task to requeue pending orders when execution windows are open.
    """
    return asyncio.run(_retry_pending_orders_async())
