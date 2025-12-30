from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.database import get_db
from stocker.models.instrument_info import InstrumentInfo

router = APIRouter()


class InstrumentInfoResponse(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[InstrumentInfoResponse])
async def get_instruments(
    symbols: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    if not symbols:
        return []

    stmt = (
        select(InstrumentInfo)
        .where(InstrumentInfo.symbol.in_(symbols))
        .order_by(InstrumentInfo.symbol.asc())
    )
    result = await db.execute(stmt)
    instruments = result.scalars().all()

    # Ensure symbols with no info still return at least symbol
    found = {inst.symbol for inst in instruments}
    missing = [s for s in symbols if s not in found]
    for sym in missing:
        instruments.append(
            InstrumentInfo(
                symbol=sym,
                name=None,
                sector=None,
                industry=None,
                exchange=None,
                currency=None,
            )
        )
    return instruments
