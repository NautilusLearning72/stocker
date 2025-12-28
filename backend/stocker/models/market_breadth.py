from sqlalchemy import Column, String, Date, Numeric
from stocker.core.database import Base
from stocker.models.base import IdMixin

class MarketBreadth(Base, IdMixin):
    """
    Broad market health indicators.
    """
    __tablename__ = "market_breadth"

    date = Column(Date, nullable=False, index=True)
    metric = Column(String(50), nullable=False)
    scope = Column(String(50), default="US_ALL")
    value = Column(Numeric(14, 4), nullable=False)
