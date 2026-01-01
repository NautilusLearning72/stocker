import logging
from datetime import date
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from stocker.core.database import AsyncSessionLocal
from stocker.models.corporate_action import CorporateAction
from stocker.services.corporate_actions import get_corporate_actions_provider

logger = logging.getLogger(__name__)


class CorporateActionsService:
    """Service to fetch and store corporate actions."""

    def __init__(self, provider_name: str = "yfinance"):
        self.provider = get_corporate_actions_provider(provider_name)
        self.provider_name = provider_name

    async def fetch_and_store_actions(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> int:
        if not symbols:
            return 0

        records = self.provider.fetch_corporate_actions(symbols, start_date, end_date)
        if not records:
            logger.warning("No corporate actions returned from provider")
            return 0

        async with AsyncSessionLocal() as session:
            stmt = insert(CorporateAction).values(records)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_corporate_actions_symbol_date_type_source",
                set_=self._build_update_map(stmt),
            )
            try:
                await session.execute(stmt)
                await session.commit()
                logger.info("Upserted %s corporate action rows", len(records))
                return len(records)
            except Exception as exc:
                await session.rollback()
                logger.error("Failed to store corporate actions: %s", exc)
                return 0

    def _build_update_map(self, stmt: Any) -> dict[str, Any]:
        excluded = stmt.excluded
        skip = {"id", "symbol", "date", "action_type", "source", "created_at"}
        update_map = {
            column.name: getattr(excluded, column.name)
            for column in CorporateAction.__table__.columns
            if column.name not in skip and column.name != "updated_at"
        }
        update_map["updated_at"] = excluded.created_at
        return update_map
