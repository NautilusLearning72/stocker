from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Index

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class DerivedMetricRule(Base, IdMixin, TimestampMixin):
    """Atomic metric rule belonging to a rule set."""

    __tablename__ = "derived_metric_rules"
    __table_args__ = (
        Index("ix_derived_metric_rules_rule_set", "rule_set_id"),
        Index("ix_derived_metric_rules_metric", "metric_id"),
    )

    rule_set_id = Column(Integer, ForeignKey("derived_metric_rule_sets.id"), nullable=False)
    metric_id = Column(Integer, ForeignKey("derived_metric_definitions.id"), nullable=False)
    operator = Column(String(10), nullable=False)
    threshold_low = Column(Numeric(20, 8))
    threshold_high = Column(Numeric(20, 8))
    weight = Column(Numeric(10, 6), nullable=False, default=1.0)
    is_required = Column(Boolean, nullable=False, default=False)
    normalize = Column(String(20))
