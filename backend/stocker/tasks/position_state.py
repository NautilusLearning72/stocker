import asyncio
import logging
from datetime import date, datetime

from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from stocker.scheduler.celery_app import app
from stocker.core.database import AsyncSessionLocal
from stocker.models.holding import Holding
from stocker.models.position_state import PositionState

logger = logging.getLogger(__name__)


async def _sync_position_states_async(portfolio_id: str) -> dict:
    async with AsyncSessionLocal() as session:
        stmt = select(Holding).where(Holding.portfolio_id == portfolio_id)
        result = await session.execute(stmt)
        holdings = result.scalars().all()

        holdings_by_symbol = {}
        for holding in holdings:
            existing = holdings_by_symbol.get(holding.symbol)
            if not existing or holding.date > existing.date:
                holdings_by_symbol[holding.symbol] = holding

        active_symbols = {
            symbol
            for symbol, holding in holdings_by_symbol.items()
            if float(holding.qty) != 0
        }

        # Clear stale position states with no active holding
        stmt = select(PositionState).where(
            PositionState.portfolio_id == portfolio_id
        )
        result = await session.execute(stmt)
        positions = result.scalars().all()
        for position in positions:
            if position.symbol in active_symbols or position.direction == 0:
                continue
            position.direction = 0
            position.entry_date = None
            position.entry_price = None
            position.peak_price = None
            position.trough_price = None
            position.entry_atr = None
            position.pending_direction = None
            position.signal_flip_date = None
            position.consecutive_flip_days = 0

        synced = 0
        for holding in holdings_by_symbol.values():
            qty = float(holding.qty)
            if qty == 0:
                continue

            direction = 1 if qty > 0 else -1
            entry_date = holding.date or date.today()
            entry_price = float(holding.cost_basis)

            stmt = pg_insert(PositionState).values({
                "portfolio_id": portfolio_id,
                "symbol": holding.symbol,
                "direction": direction,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "peak_price": entry_price,
                "trough_price": entry_price,
                "entry_atr": None,
                "pending_direction": None,
                "signal_flip_date": None,
                "consecutive_flip_days": 0,
                "updated_at": datetime.utcnow(),
            })
            stmt = stmt.on_conflict_do_update(
                constraint="uq_position_states_port_sym",
                set_={
                    "direction": stmt.excluded.direction,
                    "entry_date": stmt.excluded.entry_date,
                    "entry_price": stmt.excluded.entry_price,
                    "peak_price": stmt.excluded.peak_price,
                    "trough_price": stmt.excluded.trough_price,
                    "entry_atr": stmt.excluded.entry_atr,
                    "pending_direction": None,
                    "signal_flip_date": None,
                    "consecutive_flip_days": 0,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            synced += 1

        await session.commit()

    return {"status": "ok", "synced": synced}


@app.task(name="stocker.tasks.position_state.sync_position_states")
def sync_position_states(portfolio_id: str = "main") -> dict:
    return asyncio.run(_sync_position_states_async(portfolio_id))
