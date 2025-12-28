"""
Signals API Router.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from decimal import Decimal

from stocker.core.database import get_db
from stocker.models.signal import Signal

router = APIRouter()

# ---------- Pydantic Schemas ----------

class SignalSchema(BaseModel):
    strategy_version: str
    symbol: str
    date: date
    lookback_return: Optional[Decimal]
    ewma_vol: Optional[Decimal]
    direction: Optional[int]
    target_weight: Optional[Decimal]

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@router.get("", response_model=list[SignalSchema])
async def get_signals(
    as_of: Optional[date] = None,
    symbol: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get trading signals, optionally filtered by date and symbol."""
    query = select(Signal)
    
    if as_of:
        query = query.where(Signal.date == as_of)
    if symbol:
        query = query.where(Signal.symbol == symbol)
    
    query = query.order_by(desc(Signal.date), Signal.symbol).limit(limit)
    
    result = await db.execute(query)
    signals = result.scalars().all()
    return signals


@router.get("/latest", response_model=list[SignalSchema])
async def get_latest_signals(
    db: AsyncSession = Depends(get_db)
):
    """Get the most recent set of signals (for the latest date)."""
    # Find the latest date
    date_query = select(Signal.date).order_by(desc(Signal.date)).limit(1)
    result = await db.execute(date_query)
    latest_date = result.scalar_one_or_none()
    
    if not latest_date:
        return []
    
    query = select(Signal).where(Signal.date == latest_date).order_by(Signal.symbol)
    result = await db.execute(query)
    signals = result.scalars().all()
    return signals
