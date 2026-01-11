from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, UniqueConstraint, Index

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class DerivedMetricRuleSet(Base, IdMixin, TimestampMixin):
    """Rule sets for consolidated metric scoring."""

    __tablename__ = "derived_metric_rule_sets"
    __table_args__ = (
        UniqueConstraint("name", name="uq_derived_metric_rule_sets_name"),
        Index("ix_derived_metric_rule_sets_active", "is_active"),
    )

    name = Column(String(120), nullable=False)
    description = Column(Text)
    universe_id = Column(Integer, ForeignKey("instrument_universe.id"))
    is_active = Column(Boolean, nullable=False, default=True)
