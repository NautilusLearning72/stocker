from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class InstrumentUniverseMember(Base, IdMixin, TimestampMixin):
    """Membership mapping between universes and instruments."""

    __tablename__ = "instrument_universe_member"
    __table_args__ = (
        UniqueConstraint("universe_id", "symbol", name="uq_universe_symbol"),
    )

    universe_id = Column(Integer, ForeignKey("instrument_universe.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
