from sqlalchemy import Boolean, Column, Integer, String, Text

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class InstrumentUniverse(Base, IdMixin, TimestampMixin):
    """User-defined instrument universes."""

    __tablename__ = "instrument_universe"

    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    is_global = Column(Boolean, default=False, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
