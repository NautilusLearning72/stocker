import asyncio
import logging
import os
import sys
from datetime import date, timedelta
import random

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from stocker.core.config import settings
from stocker.core.redis import get_redis, StreamNames
from stocker.models.daily_bar import DailyBar
from stocker.models.holding import Holding
from stocker.models.portfolio_state import PortfolioState
from stocker.core.database import AsyncSessionLocal
from sqlalchemy.future import select
from sqlalchemy import text
from unittest.mock import MagicMock, patch

# Mock alpaca before imports if possible, or context manager


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_e2e")

async def seed_data(symbol: str):
    """Seed DB with enough data to generate a signal."""
    logger.info(f"Seeding data for {symbol}...")
    async with AsyncSessionLocal() as session:
        # 1. Clear All Tables (Clean Slate)
        await session.execute(text("DELETE FROM fills"))
        await session.execute(text("DELETE FROM orders"))
        await session.execute(text("DELETE FROM target_exposures"))
        await session.execute(text("DELETE FROM signals"))
        await session.execute(text("DELETE FROM holdings"))
        await session.execute(text("DELETE FROM portfolio_state"))
        
        # 2. Seed Portfolio State
        session.add(PortfolioState(
            portfolio_id="main",
            date=date.today(),
            nav=100000.0,
            cash=100000.0,
            gross_exposure=0.0,
            net_exposure=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            drawdown=0.0,
            high_water_mark=100000.0
        ))
        
        # 3. Seed Market Data (130 days of uptrend)
        await session.execute(text(f"DELETE FROM prices_daily WHERE symbol = '{symbol}'"))
        
        base_price = 100.0
        today = date.today()
        start_date = today - timedelta(days=200)
        
        days_generated = 0
        current_date = start_date
        records = []
        
        while current_date <= today:
            # Add some trend and volatility
            change = random.normalvariate(0.001, 0.01) # Pos drift
            base_price *= (1 + change)
            
            records.append(DailyBar(
                symbol=symbol,
                date=current_date,
                open=base_price,
                high=base_price * 1.01,
                low=base_price * 0.99,
                close=base_price,
                adj_close=base_price,
                volume=1000000,
                source="seed",
                source_hash="seed"
            ))
            current_date += timedelta(days=1)
            days_generated += 1
            
        session.add_all(records)
        await session.commit()
        logger.info(f"Seeded {days_generated} bars for {symbol}")

async def run_consumers_simulated(symbol: str):
    """
    Manually invoke consumer logic in order (Integration Test).
    We skip actual Redis Stream waiting to verify logic FAST.
    If this works, the Redis part is just plumbing.
    """
    from stocker.stream_consumers.signal_consumer import SignalConsumer
    from stocker.stream_consumers.portfolio_consumer import PortfolioConsumer
    from stocker.stream_consumers.order_consumer import OrderConsumer
    from stocker.stream_consumers.broker_consumer import BrokerConsumer
    from stocker.stream_consumers.ledger_consumer import LedgerConsumer
    
    # 1. TRIGGER: SignalConsumer
    # Simulating receiving a 'market-bars' event
    logger.info("--- Step 1: SignalConsumer ---")
    sig_consumer = SignalConsumer()
    # Mock Redis for verify script? Or use real redis? 
    # Real redis is running. Let's use real redis for publishing, 
    # but manually CALL process_message to avoid waiting/looping.
    
    # Need to start redis client in consumer
    sig_consumer.redis = get_redis() # This gets sync or async? 
    # BaseStreamConsumer.start() inits redis.
    from redis.asyncio import Redis
    sig_consumer.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    await sig_consumer.process_message("msg1", {
        "symbol": symbol,
        "date": date.today().isoformat()
    })
    
    # 2. TRIGGER: PortfolioConsumer
    logger.info("--- Step 2: PortfolioConsumer ---")
    port_consumer = PortfolioConsumer()
    port_consumer.redis = sig_consumer.redis
    
    # It listens to 'signals' stream. 
    # Since we aren't consuming from stream, we manually trigger with expected payload.
    # We assume SignalConsumer worked and put data in DB.
    await port_consumer.process_message("msg2", {
        "event_type": "signal_generated",
        "strategy": "vol_target_trend_v1",
        "symbol": symbol, 
        "date": date.today().isoformat()
    })
    
    # 3. TRIGGER: OrderConsumer
    logger.info("--- Step 3: OrderConsumer ---")
    ord_consumer = OrderConsumer()
    ord_consumer.redis = sig_consumer.redis
    
    # Fetch what Target was generated? 
    # We can guess logic or fetch from DB. 
    # Let's fetch the target from DB to be accurate.
    from stocker.models.target_exposure import TargetExposure
    async with AsyncSessionLocal() as session:
        stmt = select(TargetExposure).where(
            TargetExposure.symbol == symbol, 
            TargetExposure.date == date.today()
        )
        res = await session.execute(stmt)
        target = res.scalar_one_or_none()
        
    if not target:
        logger.error("Step 2 Failed: No target generated")
        return

    await ord_consumer.process_message("msg3", {
        "event_type": "target_updated",
        "portfolio_id": "main",
        "date": date.today().isoformat(),
        "symbol": symbol,
        "target_exposure": str(target.target_exposure)
    })
    
    # 4. TRIGGER: BrokerConsumer
    logger.info("--- Step 4: BrokerConsumer ---")
    
    # Mock Alpaca Client
    with patch("stocker.stream_consumers.broker_consumer.TradingClient") as MockClient:
         mock_instance = MockClient.return_value
         # Mock submit_order return
         mock_order = MagicMock()
         mock_order.id = "mock_broker_id"
         mock_instance.submit_order.return_value = mock_order
         
         # Mock get_latest_trade return
         mock_trade = MagicMock()
         mock_trade.price = 150.0 # Mock price
         mock_instance.get_latest_trade.return_value = mock_trade
         
         bro_consumer = BrokerConsumer()
         bro_consumer.redis = sig_consumer.redis
         
         # Fetch Order
         from stocker.models.order import Order
         async with AsyncSessionLocal() as session:
             stmt = select(Order).where(
                 Order.symbol == symbol,
                 Order.date == date.today()
             )
             res = await session.execute(stmt)
             order = res.scalar_one_or_none()
             
         if not order:
             logger.error("Step 3 Failed: No order generated")
             return
             
         await bro_consumer.process_message("msg4", {
             "event_type": "order_created",
             "order_id": str(order.order_id),
             "symbol": symbol,
             "side": order.side,
             "qty": str(order.qty)
         })

    
    # 5. TRIGGER: LedgerConsumer
    logger.info("--- Step 5: LedgerConsumer ---")
    led_consumer = LedgerConsumer()
    led_consumer.redis = sig_consumer.redis
    
    # Fetch Fill
    from stocker.models.fill import Fill
    async with AsyncSessionLocal() as session:
        stmt = select(Fill).where(
            Fill.order_id == order.order_id
        )
        res = await session.execute(stmt)
        fill = res.scalar_one_or_none()
        
    if not fill:
        logger.error("Step 4 Failed: No fill generated")
        return
        
    await led_consumer.process_message("msg5", {
        "event_type": "fill_created",
        "fill_id": fill.fill_id,
        "order_id": fill.order_id,
        "symbol": symbol,
        "side": fill.side,
        "qty": str(fill.qty),
        "price": str(fill.price)
    })
    
    # 6. VERIFY FINAL STATE
    logger.info("--- Step 6: Verification ---")
    async with AsyncSessionLocal() as session:
        stmt = select(Holding).where(Holding.symbol == symbol)
        res = await session.execute(stmt)
        holding = res.scalar_one_or_none()
        
        if holding:
            logger.info(f"✅ SUCCESS! Holding created: {holding.qty} shares @ ${holding.cost_basis:.2f}")
        else:
            logger.error("❌ FAILED! No holding found.")

    await sig_consumer.redis.close()

if __name__ == "__main__":
    symbol = "TEST_E2E"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(seed_data(symbol))
        loop.run_until_complete(run_consumers_simulated(symbol))
    finally:
        loop.close()
