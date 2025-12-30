from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class StrategyUniverse(Base, IdMixin, TimestampMixin):
    """Mapping between a strategy (by id) and a universe."""

    __tablename__ = "strategy_universe"
    __table_args__ = (
        UniqueConstraint("strategy_id", name="uq_strategy_universe_strategy"),
    )

    strategy_id = Column(String(100), nullable=False, index=True)
    universe_id = Column(Integer, ForeignKey("instrument_universe.id"), nullable=False)
