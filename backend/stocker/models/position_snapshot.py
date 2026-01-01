"""
Position snapshots enriched with P&L metrics from broker.
"""

from sqlalchemy import Column, String, Date, Numeric, TIMESTAMP, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class PositionSnapshot(Base, IdMixin, TimestampMixin):
    """
    Snapshot of broker positions for UI/P&L reporting.
    """

    __tablename__ = "position_snapshots"

    portfolio_id = Column(String(50), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=True)
    qty = Column(Numeric(18, 4), nullable=False)

    avg_entry_price = Column(Numeric(14, 4), nullable=True)
    cost_basis = Column(Numeric(18, 4), nullable=True)
    market_value = Column(Numeric(18, 4), nullable=True)

    current_price = Column(Numeric(14, 4), nullable=True)
    lastday_price = Column(Numeric(14, 4), nullable=True)
    change_today = Column(Numeric(12, 6), nullable=True)

    unrealized_pl = Column(Numeric(18, 4), nullable=True)
    unrealized_plpc = Column(Numeric(10, 6), nullable=True)
    unrealized_intraday_pl = Column(Numeric(18, 4), nullable=True)
    unrealized_intraday_plpc = Column(Numeric(10, 6), nullable=True)

    asset_class = Column(String(20), nullable=True)
    exchange = Column(String(20), nullable=True)
    source = Column(String(20), nullable=False, default="alpaca")
    as_of_ts = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "symbol",
            "date",
            "source",
            name="uq_position_snapshots_port_sym_date_source",
        ),
    )
