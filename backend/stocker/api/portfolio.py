"""
Portfolio API Router.
"""
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from decimal import Decimal

from stocker.core.database import get_db
from stocker.models.portfolio_state import PortfolioState
from stocker.models.holding import Holding

router = APIRouter()

# ---------- Pydantic Schemas ----------

class PortfolioStateSchema(BaseModel):
    portfolio_id: str
    date: date
    nav: Decimal
    cash: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    drawdown: Decimal
    high_water_mark: Decimal

    class Config:
        from_attributes = True


class HoldingSchema(BaseModel):
    portfolio_id: str
    date: date
    symbol: str
    qty: Decimal
    cost_basis: Decimal
    market_value: Decimal

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@router.get("/state", response_model=Optional[PortfolioStateSchema])
async def get_portfolio_state(
    portfolio_id: str = "main",
    as_of: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get the latest (or as-of-date) portfolio state."""
    query = select(PortfolioState).where(PortfolioState.portfolio_id == portfolio_id)
    if as_of:
        query = query.where(PortfolioState.date <= as_of)
    query = query.order_by(desc(PortfolioState.date)).limit(1)

    result = await db.execute(query)
    state = result.scalar_one_or_none()
    return state


@router.get("/holdings", response_model=list[HoldingSchema])
async def get_holdings(
    portfolio_id: str = "main",
    as_of: Optional[date] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get the latest holdings for a portfolio."""
    # Find the most recent date with holdings
    if as_of is None:
        date_query = select(Holding.date).where(
            Holding.portfolio_id == portfolio_id
        ).order_by(desc(Holding.date)).limit(1)
        result = await db.execute(date_query)
        latest_date = result.scalar_one_or_none()
        if not latest_date:
            return []
        as_of = latest_date
    
    query = select(Holding).where(
        Holding.portfolio_id == portfolio_id,
        Holding.date == as_of
    )
    result = await db.execute(query)
    holdings = result.scalars().all()
    return holdings
