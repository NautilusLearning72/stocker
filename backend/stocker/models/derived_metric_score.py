from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint, Index, Boolean

from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class DerivedMetricScore(Base, IdMixin, TimestampMixin):
    """Materialized composite scores for rule sets."""

    __tablename__ = "derived_metric_scores"
    __table_args__ = (
        UniqueConstraint(
            "rule_set_id",
            "symbol",
            "as_of_date",
            name="uq_derived_metric_scores_rule_set_symbol_date",
        ),
        Index("ix_derived_metric_scores_rule_set_date", "rule_set_id", "as_of_date"),
        Index("ix_derived_metric_scores_symbol_date", "symbol", "as_of_date"),
    )

    rule_set_id = Column(Integer, ForeignKey("derived_metric_rule_sets.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    score = Column(Numeric(20, 8))
    rank = Column(Integer)
    percentile = Column(Numeric(6, 4))
    passes_required = Column(Boolean, nullable=False, default=False)
