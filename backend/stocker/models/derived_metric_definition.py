from sqlalchemy import Boolean, Column, Integer, String, Text, UniqueConstraint, Index

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class DerivedMetricDefinition(Base, IdMixin, TimestampMixin):
    """Catalog of derived metrics used for screening and ranking."""

    __tablename__ = "derived_metric_definitions"
    __table_args__ = (
        UniqueConstraint("metric_key", name="uq_derived_metric_definitions_key"),
        Index("ix_derived_metric_definitions_category_key", "category", "metric_key"),
    )

    metric_key = Column(String(64), nullable=False)
    name = Column(String(120), nullable=False)
    category = Column(String(50), nullable=False)
    unit = Column(String(20))
    direction = Column(String(20), nullable=False)
    lookback_days = Column(Integer)
    description = Column(Text)
    tags = Column(String(200))
    source_table = Column(String(50))
    source_field = Column(String(64))
    version = Column(String(20), nullable=False, default="v1")
    is_active = Column(Boolean, nullable=False, default=True)
