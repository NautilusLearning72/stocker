from sqlalchemy import Column, String, Date, Numeric, BigInteger, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class DailyBar(Base, IdMixin, TimestampMixin):
    """
    Daily OHLCV data.
    Source of truth for historical and daily intake data.
    """
    __tablename__ = "prices_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_prices_daily_symbol_date"),
    )

    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Numeric(14, 4), nullable=False)
    high = Column(Numeric(14, 4), nullable=False)
    low = Column(Numeric(14, 4), nullable=False)
    close = Column(Numeric(14, 4), nullable=False)
    adj_close = Column(Numeric(14, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
    source = Column(String(50), nullable=False, default="yfinance")
    source_hash = Column(String(64))  # SHA256 for deduplication
