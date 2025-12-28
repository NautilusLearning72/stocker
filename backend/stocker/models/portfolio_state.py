from sqlalchemy import Column, String, Date, Numeric
from stocker.core.database import Base
from stocker.models.base import IdMixin

class PortfolioState(Base, IdMixin):
    """
    Daily portfolio state snapshot.
    """
    __tablename__ = "portfolio_state"

    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    nav = Column(Numeric(18, 4), nullable=False)
    cash = Column(Numeric(18, 4), nullable=False)
    gross_exposure = Column(Numeric(10, 4), nullable=False)
    net_exposure = Column(Numeric(10, 4), nullable=False)
    realized_pnl = Column(Numeric(18, 4), nullable=False)
    unrealized_pnl = Column(Numeric(18, 4), nullable=False)
    drawdown = Column(Numeric(10, 4), nullable=False)
    high_water_mark = Column(Numeric(18, 4), nullable=False)
