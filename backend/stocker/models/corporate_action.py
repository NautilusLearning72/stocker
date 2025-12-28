from sqlalchemy import Column, String, Date, Numeric
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class CorporateAction(Base, IdMixin, TimestampMixin):
    """
    Splits and dividends.
    """
    __tablename__ = "corporate_actions"

    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # Ex-date
    action_type = Column(String(20), nullable=False)  # CHECK (SPLIT, DIVIDEND)
    value = Column(Numeric(14, 4), nullable=False)
