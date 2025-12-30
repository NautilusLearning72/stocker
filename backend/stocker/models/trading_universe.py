from sqlalchemy import Column, Date, Integer, Numeric, String, UniqueConstraint

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class TradingUniverse(Base, IdMixin, TimestampMixin):
    """Daily snapshot of the dynamic trading universe."""

    __tablename__ = "trading_universe"
    __table_args__ = (
        UniqueConstraint(
            "as_of_date",
            "symbol",
            "source",
            name="uq_trading_universe_date_symbol_source",
        ),
    )

    as_of_date = Column(Date, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    avg_dollar_volume = Column(Numeric(20, 2))
    source = Column(String(50), nullable=False)
    lookback_days = Column(Integer)
