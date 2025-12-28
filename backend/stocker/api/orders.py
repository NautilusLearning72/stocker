"""
Orders API Router.
"""
from datetime import date
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import joinedload
from pydantic import BaseModel
from decimal import Decimal

from stocker.core.database import get_db
from stocker.models.order import Order
from stocker.models.fill import Fill

router = APIRouter()

# ---------- Pydantic Schemas ----------

class FillSchema(BaseModel):
    fill_id: str
    date: Optional[date]
    qty: Decimal
    price: Decimal

    class Config:
        from_attributes = True


class OrderSchema(BaseModel):
    order_id: UUID
    portfolio_id: str
    date: date
    symbol: str
    side: Optional[str]
    qty: Decimal
    type: Optional[str]
    status: Optional[str]
    broker_order_id: Optional[str]
    fills: list[FillSchema] = []

    class Config:
        from_attributes = True


# ---------- Endpoints ----------

@router.get("", response_model=list[OrderSchema])
async def get_orders(
    portfolio_id: str = "default",
    as_of: Optional[date] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db)
):
    """Get orders, optionally filtered by date and status."""
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.portfolio_id == portfolio_id
    )
    
    if as_of:
        query = query.where(Order.date == as_of)
    if status:
        query = query.where(Order.status == status)
    
    query = query.order_by(desc(Order.date)).limit(limit)
    
    result = await db.execute(query)
    orders = result.unique().scalars().all()
    return orders


@router.get("/{order_id}", response_model=Optional[OrderSchema])
async def get_order(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific order by its ID."""
    query = select(Order).options(joinedload(Order.fills)).where(
        Order.order_id == order_id
    )
    result = await db.execute(query)
    order = result.unique().scalar_one_or_none()
    return order
