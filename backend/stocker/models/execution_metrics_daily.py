from sqlalchemy import Column, String, Date, Numeric, Integer, UniqueConstraint, Index
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class ExecutionMetricsDaily(Base, IdMixin, TimestampMixin):
    """
    Daily aggregated execution quality metrics.
    Tracks order success rates, slippage, and commission costs.
    """
    __tablename__ = "execution_metrics_daily"

    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)

    # Order counts by status
    orders_placed = Column(Integer, default=0)
    orders_filled = Column(Integer, default=0)
    orders_partial = Column(Integer, default=0)
    orders_rejected = Column(Integer, default=0)

    # Fill quality metrics
    total_slippage = Column(Numeric(18, 4), default=0)
    total_commission = Column(Numeric(18, 4), default=0)
    avg_fill_rate = Column(Numeric(10, 6))  # filled_qty / ordered_qty

    # Timing
    avg_fill_time_ms = Column(Integer)

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'date', name='uq_exec_metrics_daily_port_date'),
        Index('ix_exec_metrics_daily_portfolio_date', 'portfolio_id', 'date'),
    )
