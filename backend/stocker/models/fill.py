from sqlalchemy import Column, String, Numeric, Uuid, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from stocker.core.database import Base
from stocker.models.base import IdMixin

class Fill(Base, IdMixin):
    """
    Execution fills.
    """
    __tablename__ = "fills"

    fill_id = Column(String(100), unique=True, nullable=False)
    order_id = Column(Uuid, ForeignKey("orders.order_id"))
    date = Column(TIMESTAMP(timezone=True), nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    qty = Column(Numeric(12, 4), nullable=False)
    price = Column(Numeric(14, 4), nullable=False)
    commission = Column(Numeric(10, 4), default=0)
    exchange = Column(String(50))

    order = relationship("Order", back_populates="fills")
