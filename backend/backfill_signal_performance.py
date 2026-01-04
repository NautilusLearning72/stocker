
import asyncio
import logging
from datetime import date
from decimal import Decimal
from typing import Optional, Dict

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from stocker.core.database import AsyncSessionLocal
from stocker.models import Fill, Signal, SignalPerformance, Order

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Replicate logic from LedgerConsumer
def direction_from_qty(qty: float) -> int:
    if qty > 0:
        return 1
    if qty < 0:
        return -1
    return 0

async def find_entry_signal(session, symbol: str, entry_date: date, direction: int) -> Optional[Signal]:
    stmt = select(Signal).where(
        Signal.symbol == symbol,
        Signal.date <= entry_date
    ).order_by(Signal.date.desc()).limit(1)
    
    result = await session.execute(stmt)
    signal = result.scalar_one_or_none()
    return signal

async def backfill():
    async with AsyncSessionLocal() as session:
        # 1. Clear existing SignalPerformance
        print("Clearing SignalPerformance table...")
        await session.execute(delete(SignalPerformance))
        await session.commit()
        
        # 2. Fetch all fills ordered by date, then id
        print("Fetching all fills...")
        stmt = select(Fill).order_by(Fill.date, Fill.id)
        result = await session.execute(stmt)
        fills = result.scalars().all()
        print(f"Found {len(fills)} fills to process")
        
        # Track simulated holdings: symbol -> qty
        simulated_holdings: Dict[str, float] = {}
        
        # Track open performance records: (symbol) -> entry_date (simplified, actually need DB ID or object)
        # But we can just query the DB like the consumer does, or keep state in memory? 
        # Querying DB is safer to replicate exact logic.
        
        for fill in fills:
            symbol = fill.symbol
            qty = float(fill.qty)
            price = float(fill.price)
            fill_date = fill.date.date() if hasattr(fill.date, 'date') else fill.date
            side = fill.side
            
            # Helper to get portfolio_id (needed for SignalPerformance)
            # Fetch order to get portfolio_id. If fail, default to 'main'
            stmt_order = select(Order).where(Order.order_id == fill.order_id)
            res_order = await session.execute(stmt_order)
            order = res_order.scalar_one_or_none()
            portfolio_id = order.portfolio_id if order else "main"
            
            signed_qty = qty if side == "BUY" else -qty
            
            old_qty = simulated_holdings.get(symbol, 0.0)
            new_qty = old_qty + signed_qty
            simulated_holdings[symbol] = new_qty
            
            old_direction = direction_from_qty(old_qty)
            new_direction = direction_from_qty(new_qty)
            
            print(f"Processing {symbol} {side} {qty} @ {price} | Qty: {old_qty:.2f} -> {new_qty:.2f} | Dir: {old_direction} -> {new_direction}")
            
            # --- Logic from LedgerConsumer._update_position_state ---
            
            # Track position close
            if new_direction == 0 and old_direction != 0:
                await close_signal_performance(
                    session, portfolio_id, symbol, old_direction, fill_date, price, "position_closed"
                )

            # Track position flip (long->short or short->long)
            if old_direction != 0 and new_direction != 0 and old_direction != new_direction:
                await close_signal_performance(
                    session, portfolio_id, symbol, old_direction, fill_date, price, "signal_flip"
                )

            # Track new position entry (new entry or flip)
            if (old_direction == 0 and new_direction != 0) or \
               (old_direction != 0 and new_direction != 0 and old_direction != new_direction):
                 # Find matching signal
                signal = await find_entry_signal(session, symbol, fill_date, new_direction)
                signal_date = signal.date if signal else fill_date
                
                await create_signal_performance(
                    session, portfolio_id, symbol, new_direction, fill_date, price, signal_date
                )
                
            await session.commit()
            
        print("Backfill complete.")

async def create_signal_performance(
    session, portfolio_id, symbol, direction, entry_date, entry_price, signal_date
):
    perf = SignalPerformance(
        portfolio_id=portfolio_id,
        symbol=symbol,
        direction=direction,
        signal_date=signal_date,
        entry_date=entry_date,
        entry_price=Decimal(str(entry_price)),
        exit_date=None,
        exit_price=None,
        holding_days=None,
        realized_return=None,
        is_winner=None,
        exit_reason=None
    )
    session.add(perf)
    print(f"  [+] Created open performance: {symbol} date={entry_date}")

async def close_signal_performance(
    session, portfolio_id, symbol, direction, exit_date, exit_price, exit_reason
):
    # Find open performance record
    stmt = select(SignalPerformance).where(
        SignalPerformance.portfolio_id == portfolio_id,
        SignalPerformance.symbol == symbol,
        SignalPerformance.direction == direction,
        SignalPerformance.exit_date.is_(None)
    ).order_by(SignalPerformance.entry_date.desc()).limit(1)

    result = await session.execute(stmt)
    perf = result.scalar_one_or_none()

    if not perf:
        print(f"  [!] No open SignalPerformance found for {symbol} to close.")
        return

    # Calculate metrics
    entry_price_float = float(perf.entry_price)
    holding_days = (exit_date - perf.entry_date).days

    price_return = (exit_price - entry_price_float) / entry_price_float
    realized_return = price_return * direction

    perf.exit_date = exit_date
    perf.exit_price = Decimal(str(exit_price))
    perf.holding_days = holding_days
    perf.realized_return = Decimal(str(realized_return))
    perf.is_winner = realized_return > 0
    perf.exit_reason = exit_reason
    
    print(f"  [-] Closed performance: {symbol} ret={realized_return:.2%}")

if __name__ == "__main__":
    asyncio.run(backfill())
