import logging
from contextlib import asynccontextmanager
from typing import Iterable, List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from stocker.core.config import settings
from stocker.core.database import AsyncSessionLocal
from stocker.models.instrument_info import InstrumentInfo
from stocker.models.instrument_universe import InstrumentUniverse
from stocker.models.instrument_universe_member import InstrumentUniverseMember
from stocker.models.strategy_universe import StrategyUniverse

logger = logging.getLogger(__name__)


class UniverseService:
    """Manage instrument universes and strategy mappings."""

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def create_universe(
        self,
        name: str,
        description: str | None = None,
        is_global: bool = False,
    ) -> InstrumentUniverse:
        async with self._get_session() as session:
            universe = InstrumentUniverse(
                name=name,
                description=description,
                is_global=is_global,
                is_deleted=False,
            )
            session.add(universe)
            await session.flush()
            await session.refresh(universe)
            return universe

    async def list_universes(self, include_deleted: bool = False) -> list[InstrumentUniverse]:
        async with self._get_session() as session:
            stmt = select(InstrumentUniverse)
            if not include_deleted:
                stmt = stmt.where(InstrumentUniverse.is_deleted.is_(False))
            result = await session.execute(stmt.order_by(InstrumentUniverse.id.asc()))
            return result.scalars().all()

    async def get_universe(
        self,
        universe_id: int,
        include_deleted: bool = False,
    ) -> Optional[InstrumentUniverse]:
        async with self._get_session() as session:
            stmt = select(InstrumentUniverse).where(InstrumentUniverse.id == universe_id)
            if not include_deleted:
                stmt = stmt.where(InstrumentUniverse.is_deleted.is_(False))
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_universe(
        self,
        universe_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_global: Optional[bool] = None,
    ) -> int:
        async with self._get_session() as session:
            values = {}
            if name is not None:
                values["name"] = name
            if description is not None:
                values["description"] = description
            if is_global is not None:
                values["is_global"] = is_global
            if not values:
                return 0
            values["updated_at"] = func.now()
            stmt = (
                update(InstrumentUniverse)
                .where(InstrumentUniverse.id == universe_id, InstrumentUniverse.is_deleted.is_(False))
                .values(**values)
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def delete_universe(self, universe_id: int) -> int:
        async with self._get_session() as session:
            stmt = (
                update(InstrumentUniverse)
                .where(InstrumentUniverse.id == universe_id)
                .values(is_deleted=True, updated_at=func.now())
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def add_members(self, universe_id: int, symbols: Iterable[str]) -> int:
        normalized = self._normalize_symbols(symbols)
        if not normalized:
            return 0

        async with self._get_session() as session:
            # Ensure instrument_info exists
            await self._ensure_instrument_info(session, normalized)

            stmt = insert(InstrumentUniverseMember).values(
                [
                    {
                        "universe_id": universe_id,
                        "symbol": symbol,
                        "is_deleted": False,
                    }
                    for symbol in normalized
                ]
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_universe_symbol",
                set_={
                    "is_deleted": False,
                    "updated_at": func.now(),
                },
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def remove_member(self, universe_id: int, symbol: str) -> int:
        async with self._get_session() as session:
            stmt = (
                update(InstrumentUniverseMember)
                .where(
                    InstrumentUniverseMember.universe_id == universe_id,
                    InstrumentUniverseMember.symbol == symbol,
                )
                .values(is_deleted=True, updated_at=func.now())
            )
            result = await session.execute(stmt)
            return result.rowcount or 0

    async def map_strategy_to_universe(self, strategy_id: str, universe_id: int) -> None:
        async with self._get_session() as session:
            stmt = insert(StrategyUniverse).values(
                strategy_id=strategy_id,
                universe_id=universe_id,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_strategy_universe_strategy",
                set_={
                    "universe_id": stmt.excluded.universe_id,
                    "updated_at": func.now(),
                },
            )
            await session.execute(stmt)

    async def get_symbols_for_strategy(self, strategy_id: Optional[str]) -> list[str]:
        async with self._get_session() as session:
            sid = strategy_id or settings.DEFAULT_STRATEGY_ID
            mapping_stmt = select(StrategyUniverse.universe_id).where(
                StrategyUniverse.strategy_id == sid
            )
            result = await session.execute(mapping_stmt)
            universe_id = result.scalar_one_or_none()

            if universe_id is None:
                logger.warning("No universe mapping for strategy %s; using static fallback", sid)
                return settings.TRADING_UNIVERSE

            symbols_stmt = (
                select(InstrumentUniverseMember.symbol)
                .join(InstrumentUniverse, InstrumentUniverse.id == InstrumentUniverseMember.universe_id)
                .where(
                    InstrumentUniverseMember.universe_id == universe_id,
                    InstrumentUniverseMember.is_deleted.is_(False),
                    InstrumentUniverse.is_deleted.is_(False),
                )
                .order_by(InstrumentUniverseMember.symbol.asc())
            )
            symbols_result = await session.execute(symbols_stmt)
            symbols = [row[0] for row in symbols_result.all()]
            if not symbols:
                logger.warning(
                    "Universe %s for strategy %s is empty; using static fallback",
                    universe_id,
                    sid,
                )
                return settings.TRADING_UNIVERSE
            return symbols

    async def get_all_symbols(self) -> list[str]:
        async with self._get_session() as session:
            stmt = (
                select(func.distinct(InstrumentUniverseMember.symbol))
                .join(InstrumentUniverse, InstrumentUniverse.id == InstrumentUniverseMember.universe_id)
                .where(
                    InstrumentUniverseMember.is_deleted.is_(False),
                    InstrumentUniverse.is_deleted.is_(False),
                )
                .order_by(InstrumentUniverseMember.symbol.asc())
            )
            result = await session.execute(stmt)
            symbols = [row[0] for row in result.all()]
            if symbols:
                return symbols
            return settings.TRADING_UNIVERSE

    async def get_global_symbols(self) -> list[str]:
        async with self._get_session() as session:
            universe_stmt = (
                select(InstrumentUniverse.id)
                .where(
                    InstrumentUniverse.is_global.is_(True),
                    InstrumentUniverse.is_deleted.is_(False),
                )
                .order_by(InstrumentUniverse.id.asc())
                .limit(1)
            )
            result = await session.execute(universe_stmt)
            universe_id = result.scalar_one_or_none()
            if universe_id is None:
                return await self.get_all_symbols()

            symbols_stmt = (
                select(InstrumentUniverseMember.symbol)
                .join(InstrumentUniverse, InstrumentUniverse.id == InstrumentUniverseMember.universe_id)
                .where(
                    InstrumentUniverseMember.universe_id == universe_id,
                    InstrumentUniverseMember.is_deleted.is_(False),
                    InstrumentUniverse.is_deleted.is_(False),
                )
                .order_by(InstrumentUniverseMember.symbol.asc())
            )
            symbols_result = await session.execute(symbols_stmt)
            symbols = [row[0] for row in symbols_result.all()]
            if symbols:
                return symbols
            return await self.get_all_symbols()

    async def get_symbols_for_universe(
        self,
        universe_id: int,
        include_deleted: bool = False,
    ) -> list[str]:
        async with self._get_session() as session:
            stmt = select(InstrumentUniverseMember.symbol).where(
                InstrumentUniverseMember.universe_id == universe_id,
            )
            if not include_deleted:
                stmt = stmt.where(InstrumentUniverseMember.is_deleted.is_(False))
            result = await session.execute(stmt.order_by(InstrumentUniverseMember.symbol.asc()))
            symbols = [row[0] for row in result.all()]
            return symbols

    async def _ensure_instrument_info(self, session: AsyncSession, symbols: list[str]) -> None:
        stmt = insert(InstrumentInfo).values(
            [{"symbol": symbol, "active": True} for symbol in symbols]
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["symbol"])
        await session.execute(stmt)

    def _normalize_symbols(self, symbols: Iterable[str]) -> list[str]:
        normalized: List[str] = []
        seen = set()
        for sym in symbols:
            if sym is None:
                continue
            symbol = sym.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            normalized.append(symbol)
        return normalized

    @asynccontextmanager
    async def _get_session(self):
        if self.session is not None:
            yield self.session
        else:
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
