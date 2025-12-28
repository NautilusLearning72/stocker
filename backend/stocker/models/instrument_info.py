from sqlalchemy import Column, String, Boolean, Date
from stocker.core.database import Base
from stocker.models.base import TimestampMixin

class InstrumentInfo(Base, TimestampMixin):
    """
    Master table for tradable assets (Sector, Industry, etc.).
    """
    __tablename__ = "instrument_info"

    symbol = Column(String(20), primary_key=True)
    name = Column(String(255))
    asset_class = Column(String(20), default="US_EQUITY")
    sector = Column(String(100))
    industry = Column(String(100))
    exchange = Column(String(50))
    currency = Column(String(10), default="USD")
    active = Column(Boolean, default=True)
