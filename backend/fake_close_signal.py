
import asyncio
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from stocker.core.database import AsyncSessionLocal
from stocker.models import SignalPerformance

async def fake_close():
    async with AsyncSessionLocal() as session:
        # Get one open signal
        stmt = select(SignalPerformance).where(
            SignalPerformance.exit_date.is_(None)
        ).limit(1)
        result = await session.execute(stmt)
        perf = result.scalar_one_or_none()
        
        if perf:
            print(f"Faking close for {perf.symbol}...")
            perf.exit_date = date.today()
            perf.exit_price = perf.entry_price * Decimal("1.05") # 5% profit
            perf.realized_return = Decimal("0.05")
            perf.is_winner = True
            perf.exit_reason = "manual_test"
            perf.holding_days = 5
            
            await session.commit()
            print("Done. Check UI.")
        else:
            print("No open signals found.")

if __name__ == "__main__":
    asyncio.run(fake_close())
