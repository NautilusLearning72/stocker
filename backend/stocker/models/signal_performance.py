from sqlalchemy import Column, String, Date, Numeric, Integer, SmallInteger, Boolean, Index
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class SignalPerformance(Base, IdMixin, TimestampMixin):
    """
    Tracks individual signal outcomes for hit rate and return analysis.
    Records entry/exit details when positions are closed.
    """
    __tablename__ = "signal_performance"

    portfolio_id = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)

    # Signal info
    direction = Column(SmallInteger, nullable=False)  # -1, 0, 1
    signal_date = Column(Date, nullable=False)

    # Entry details
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Numeric(14, 4), nullable=False)

    # Exit details (populated when position closes)
    exit_date = Column(Date)
    exit_price = Column(Numeric(14, 4))
    holding_days = Column(Integer)
    realized_return = Column(Numeric(12, 8))

    # Classification
    is_winner = Column(Boolean)
    exit_reason = Column(String(50))  # 'signal_flip', 'trailing_stop', 'atr_exit', etc.

    __table_args__ = (
        Index('ix_signal_perf_portfolio', 'portfolio_id'),
        Index('ix_signal_perf_symbol', 'symbol'),
        Index('ix_signal_perf_signal_date', 'signal_date'),
        Index('ix_signal_perf_exit_date', 'exit_date'),
    )
