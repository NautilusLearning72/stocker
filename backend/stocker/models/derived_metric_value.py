from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Index

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class DerivedMetricValue(Base, IdMixin, TimestampMixin):
    """Computed metric values per symbol/date with normalization for ranking."""

    __tablename__ = "derived_metric_values"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "as_of_date",
            "metric_id",
            name="uq_derived_metric_values_symbol_date_metric",
        ),
        Index("ix_derived_metric_values_metric_date", "metric_id", "as_of_date"),
        Index("ix_derived_metric_values_symbol_date", "symbol", "as_of_date"),
    )

    symbol = Column(String(20), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    metric_id = Column(Integer, ForeignKey("derived_metric_definitions.id"), nullable=False, index=True)
    value = Column(Numeric(20, 8))
    zscore = Column(Numeric(12, 6))
    percentile = Column(Numeric(6, 4))
    rank = Column(Integer)
    source = Column(String(50), nullable=False)
    calc_version = Column(String(20), nullable=False, default="v1")
