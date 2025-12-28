from sqlalchemy import Column, String, Date, Numeric, SmallInteger, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class Signal(Base, IdMixin, TimestampMixin):
    """
    Trading signals.
    """
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("strategy_version", "symbol", "date", name="uq_signals_strat_sym_date"),
    )

    strategy_version = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    lookback_return = Column(Numeric(10, 6))
    ewma_vol = Column(Numeric(10, 6))
    direction = Column(SmallInteger)  # -1, 0, 1
    target_weight = Column(Numeric(10, 6))
