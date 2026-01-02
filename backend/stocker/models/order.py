from sqlalchemy import Column, String, Date, Numeric, Uuid, TIME, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import relationship
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin
import uuid

class Order(Base, IdMixin, TimestampMixin):
    """
    Execution orders.
    """
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint('portfolio_id', 'symbol', 'date', name='uq_order_portfolio_symbol_date'),
    )

    order_id = Column(Uuid, unique=True, nullable=False, default=uuid.uuid4)
    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10))  # CHECK (BUY, SELL)
    qty = Column(Numeric(12, 4), nullable=False)
    type = Column(String(20), default="MOO")
    status = Column(String(20))
    broker_order_id = Column(String(100))

    # Relationship to executions
    fills = relationship("Fill", back_populates="order")
