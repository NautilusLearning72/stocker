from sqlalchemy import Column, String, Date, Numeric, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class CorporateAction(Base, IdMixin, TimestampMixin):
    """
    Splits and dividends.
    """
    __tablename__ = "corporate_actions"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "date",
            "action_type",
            "source",
            name="uq_corporate_actions_symbol_date_type_source",
        ),
    )

    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)  # Ex-date
    action_type = Column(String(20), nullable=False)  # CHECK (SPLIT, DIVIDEND)
    value = Column(Numeric(14, 4), nullable=False)
    source = Column(String(50), nullable=False)
    source_hash = Column(String(64))
