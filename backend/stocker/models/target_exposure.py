from sqlalchemy import Column, String, Date, Numeric, Boolean, Text, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class TargetExposure(Base, IdMixin, TimestampMixin):
    """
    Target portfolio exposures.
    """
    __tablename__ = "target_exposures"
    __table_args__ = (
        UniqueConstraint("portfolio_id", "symbol", "date", name="uq_target_exposures_port_sym_date"),
    )

    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    symbol = Column(String(20), nullable=False)
    target_exposure = Column(Numeric(10, 6), nullable=False)
    scaling_factor = Column(Numeric(5, 4), default=1.0)
    is_capped = Column(Boolean, default=False)
    reason = Column(Text)
