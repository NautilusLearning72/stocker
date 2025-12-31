"""
Position state tracking for exit rules.

Tracks entry prices, peak/trough prices, and signal persistence
for implementing trailing stops, ATR exits, and persistence filters.
"""

from sqlalchemy import Column, String, SmallInteger, Integer, Date, Numeric, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import TimestampMixin, IdMixin


class PositionState(Base, IdMixin, TimestampMixin):
    """
    Track position state for exit rule evaluation.

    Updated each time a position changes or daily to track peak prices.
    """
    __tablename__ = "position_states"

    portfolio_id = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # Current position direction: -1 (short), 0 (flat), 1 (long)
    direction = Column(SmallInteger, nullable=False, default=0)

    # Entry tracking
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Numeric(14, 4), nullable=True)

    # Peak/Trough tracking for trailing stops
    # For longs: track highest price since entry
    # For shorts: track lowest price since entry
    peak_price = Column(Numeric(14, 4), nullable=True)
    trough_price = Column(Numeric(14, 4), nullable=True)

    # Persistence tracking for signal flip filtering
    # When signal starts flipping, track how many days it persists
    pending_direction = Column(SmallInteger, nullable=True)  # Direction signal is trying to flip to
    signal_flip_date = Column(Date, nullable=True)  # When signal started flipping
    consecutive_flip_days = Column(Integer, default=0)  # Days signal has persisted in new direction

    # ATR at entry (for ATR-based exits)
    entry_atr = Column(Numeric(10, 4), nullable=True)

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'symbol', name='uq_position_states_port_sym'),
    )

    def __repr__(self) -> str:
        return (
            f"<PositionState(symbol={self.symbol}, direction={self.direction}, "
            f"entry_price={self.entry_price}, peak={self.peak_price})>"
        )
