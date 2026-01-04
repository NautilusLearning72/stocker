
import asyncio
from sqlalchemy import select, func
from stocker.core.database import AsyncSessionLocal
from stocker.models import Signal, SignalPerformance, PortfolioState

async def check_db():
    async with AsyncSessionLocal() as session:
        # Check Signals
        try:
            result = await session.execute(select(func.count(Signal.id)))
            signal_count = result.scalar()
            print(f"Total Signals: {signal_count}")
        except Exception as e:
            print(f"Error checking Signals: {e}")

        # Check SignalPerformance
        try:
            result = await session.execute(select(func.count(SignalPerformance.id)))
            perf_count = result.scalar()
            print(f"Total SignalPerformance records: {perf_count}")
            
            # Check closed SignalPerformance
            result = await session.execute(select(func.count(SignalPerformance.id)).where(SignalPerformance.exit_date.isnot(None)))
            closed_perf_count = result.scalar()
            print(f"Closed SignalPerformance records: {closed_perf_count}")
        except Exception as e:
            print(f"Error checking SignalPerformance: {e}")

        # Check PortfolioState
        try:
            result = await session.execute(select(func.count(PortfolioState.id)))
            state_count = result.scalar()
            print(f"Total PortfolioState records: {state_count}")
            
            # Check Portfolio IDs
            result = await session.execute(select(PortfolioState.portfolio_id).distinct())
            portfolio_ids = result.scalars().all()
            print(f"Portfolio IDs: {portfolio_ids}")
        except Exception as e:
             print(f"Error checking PortfolioState: {e}")

        # Check Fills
        try:
             from stocker.models.fill import Fill
             result = await session.execute(select(func.count(Fill.fill_id)))
             fill_count = result.scalar()
             print(f"Total Fill records: {fill_count}")
        except Exception as e:
            print(f"Error checking Fills: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
