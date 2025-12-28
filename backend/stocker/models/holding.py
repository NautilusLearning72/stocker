from sqlalchemy import Column, String, Date, Numeric
from stocker.core.database import Base
from stocker.models.base import IdMixin

class Holding(Base, IdMixin):
    """
    Current portfolio holdings (snapshot).
    """
    __tablename__ = "holdings"

    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    symbol = Column(String(20), nullable=False)
    qty = Column(Numeric(12, 4), nullable=False)
    cost_basis = Column(Numeric(14, 4), nullable=False)
    market_value = Column(Numeric(18, 4), nullable=False)
