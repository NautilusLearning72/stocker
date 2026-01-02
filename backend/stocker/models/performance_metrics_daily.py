from sqlalchemy import Column, String, Date, Numeric, UniqueConstraint, Index
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin


class PerformanceMetricsDaily(Base, IdMixin, TimestampMixin):
    """
    Pre-computed daily performance metrics for fast dashboard queries.
    Calculated end-of-day by the performance snapshot task.
    """
    __tablename__ = "performance_metrics_daily"

    portfolio_id = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)

    # Daily returns
    daily_return = Column(Numeric(12, 8))
    daily_pnl = Column(Numeric(18, 4))

    # Rolling metrics (30-day lookback)
    rolling_sharpe_30d = Column(Numeric(10, 6))
    rolling_vol_30d = Column(Numeric(10, 6))
    rolling_max_dd_30d = Column(Numeric(10, 6))

    # Exposure breakdown
    long_exposure = Column(Numeric(10, 6))
    short_exposure = Column(Numeric(10, 6))

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'date', name='uq_perf_metrics_daily_port_date'),
        Index('ix_perf_metrics_daily_portfolio_date', 'portfolio_id', 'date'),
    )
