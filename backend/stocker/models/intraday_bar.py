from sqlalchemy import Column, String, TIMESTAMP, Numeric, BigInteger, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class IntradayBar(Base, IdMixin, TimestampMixin):
    """
    Historical and live intraday data (e.g., 1-minute, 5-minute bars).
    """
    __tablename__ = "prices_intraday"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "interval", name="uq_prices_intraday_symbol_ts_interval"),
    )

    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    interval = Column(String(10), nullable=False)  # e.g., '1m', '5m', '1h'
    open = Column(Numeric(14, 4), nullable=False)
    high = Column(Numeric(14, 4), nullable=False)
    low = Column(Numeric(14, 4), nullable=False)
    close = Column(Numeric(14, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
