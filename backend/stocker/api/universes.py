from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.config import settings
from stocker.core.database import get_db
from stocker.models.instrument_universe import InstrumentUniverse
from stocker.models.strategy_universe import StrategyUniverse
from stocker.models.instrument_universe_member import InstrumentUniverseMember
from stocker.models.instrument_metrics import InstrumentMetrics
from stocker.services.universe_service import UniverseService

router = APIRouter()


# Schemas

class UniverseBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    is_global: bool = False


class UniverseCreate(UniverseBase):
    pass


class UniverseUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    is_global: Optional[bool] = None


class UniverseMemberAdd(BaseModel):
    symbols: list[str]


class UniverseResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_global: bool
    is_deleted: bool

    class Config:
        from_attributes = True


class UniverseDetail(UniverseResponse):
    members: list[str] = []


class StrategyUniverseResponse(BaseModel):
    strategy_id: str
    universe_id: Optional[int]
    symbols: list[str]


class StrategyUniverseAssign(BaseModel):
    universe_id: int


class MetricStatus(BaseModel):
    symbol: str
    as_of_date: Optional[str] = None


# Endpoints


@router.get("/metrics", response_model=list[MetricStatus])
async def get_metrics_status(
    universe_id: Optional[int] = Query(default=None),
    symbols: Optional[list[str]] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    target_symbols: list[str]
    if universe_id is not None:
        target_symbols = await service.get_symbols_for_universe(universe_id)
    elif symbols:
        target_symbols = symbols
    else:
        target_symbols = await service.get_all_symbols()

    if not target_symbols:
        return []

    stmt = (
        select(InstrumentMetrics.symbol, func.max(InstrumentMetrics.as_of_date))
        .where(InstrumentMetrics.symbol.in_(target_symbols))
        .group_by(InstrumentMetrics.symbol)
    )
    result = await db.execute(stmt)
    rows = {row[0]: row[1] for row in result.all()}

    return [
        MetricStatus(
            symbol=symbol,
            as_of_date=str(rows.get(symbol)) if rows.get(symbol) else None,
        )
        for symbol in target_symbols
    ]


@router.post("", response_model=UniverseResponse, status_code=status.HTTP_201_CREATED)
async def create_universe(
    payload: UniverseCreate,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    universe = await service.create_universe(
        name=payload.name,
        description=payload.description,
        is_global=payload.is_global,
    )
    return universe


@router.get("", response_model=list[UniverseResponse])
async def list_universes(
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    universes = await service.list_universes(include_deleted=include_deleted)
    return universes


@router.get("/{universe_id}", response_model=UniverseDetail)
async def get_universe(
    universe_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    universe = await service.get_universe(universe_id)
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    members_stmt = (
        select(InstrumentUniverseMember.symbol)
        .where(
            InstrumentUniverseMember.universe_id == universe_id,
            InstrumentUniverseMember.is_deleted.is_(False),
        )
        .order_by(InstrumentUniverseMember.symbol.asc())
    )
    result = await db.execute(members_stmt)
    members = [row[0] for row in result.all()]
    return UniverseDetail(
        id=universe.id,
        name=universe.name,
        description=universe.description,
        is_global=universe.is_global,
        is_deleted=universe.is_deleted,
        members=members,
    )


@router.patch("/{universe_id}", response_model=UniverseResponse)
async def update_universe(
    universe_id: int,
    payload: UniverseUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    updated = await service.update_universe(
        universe_id=universe_id,
        name=payload.name,
        description=payload.description,
        is_global=payload.is_global,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Universe not found or not updated")
    universe = await service.get_universe(universe_id, include_deleted=True)
    return universe


@router.delete("/{universe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_universe(
    universe_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    deleted = await service.delete_universe(universe_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Universe not found")
    return None


@router.post("/{universe_id}/members", status_code=status.HTTP_200_OK)
async def add_universe_members(
    universe_id: int,
    payload: UniverseMemberAdd,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    count = await service.add_members(universe_id, payload.symbols)
    return {"added": count}


@router.delete("/{universe_id}/members/{symbol}", status_code=status.HTTP_200_OK)
async def remove_universe_member(
    universe_id: int,
    symbol: str,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    removed = await service.remove_member(universe_id, symbol)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"removed": removed}


@router.post("/strategies/{strategy_id}/universe", status_code=status.HTTP_200_OK)
async def set_strategy_universe(
    strategy_id: str,
    payload: StrategyUniverseAssign = Body(...),
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    universe = await service.get_universe(payload.universe_id)
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")
    await service.map_strategy_to_universe(strategy_id, payload.universe_id)
    return {"strategy_id": strategy_id, "universe_id": payload.universe_id}


@router.get("/strategies/{strategy_id}/universe", response_model=StrategyUniverseResponse)
async def get_strategy_universe(
    strategy_id: str,
    db: AsyncSession = Depends(get_db),
):
    service = UniverseService(session=db)
    symbols = await service.get_symbols_for_strategy(strategy_id)

    mapping = await db.execute(
        select(StrategyUniverse).where(StrategyUniverse.strategy_id == strategy_id)
    )
    row = mapping.scalar_one_or_none()
    universe_id = row.universe_id if row else None

    return StrategyUniverseResponse(
        strategy_id=strategy_id,
        universe_id=universe_id,
        symbols=symbols,
    )
