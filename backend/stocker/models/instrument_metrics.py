from sqlalchemy import BigInteger, Column, Date, Integer, Numeric, String, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class InstrumentMetrics(Base, IdMixin, TimestampMixin):
    """
    Investor-facing fundamentals and valuation metrics for a symbol.
    """
    __tablename__ = "instrument_metrics"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "as_of_date",
            "period_type",
            "source",
            name="uq_instrument_metrics_symbol_date_period_source",
        ),
    )

    symbol = Column(String(20), nullable=False, index=True)
    as_of_date = Column(Date, nullable=False, index=True)
    period_type = Column(String(10), nullable=False, default="TTM")
    period_end = Column(Date)
    fiscal_year = Column(Integer)
    fiscal_quarter = Column(Integer)
    source = Column(String(50), nullable=False)
    currency = Column(String(10), default="USD")

    # Market and valuation
    market_cap = Column(Numeric(20, 2))
    enterprise_value = Column(Numeric(20, 2))
    shares_outstanding = Column(BigInteger)
    float_shares = Column(BigInteger)
    beta = Column(Numeric(6, 4))
    pe_ttm = Column(Numeric(12, 4))
    pe_forward = Column(Numeric(12, 4))
    price_to_book = Column(Numeric(12, 4))
    price_to_sales = Column(Numeric(12, 4))
    peg_ratio = Column(Numeric(12, 4))
    ev_to_ebitda = Column(Numeric(12, 4))
    ev_to_ebit = Column(Numeric(12, 4))
    fcf_yield = Column(Numeric(12, 6))
    dividend_yield = Column(Numeric(12, 6))
    dividend_rate = Column(Numeric(14, 6))
    payout_ratio = Column(Numeric(12, 6))

    # Financial statement aggregates
    revenue = Column(Numeric(20, 2))
    ebitda = Column(Numeric(20, 2))
    net_income = Column(Numeric(20, 2))
    free_cash_flow = Column(Numeric(20, 2))

    # Profitability
    gross_margin = Column(Numeric(12, 6))
    operating_margin = Column(Numeric(12, 6))
    net_margin = Column(Numeric(12, 6))
    ebitda_margin = Column(Numeric(12, 6))
    roe = Column(Numeric(12, 6))
    roa = Column(Numeric(12, 6))
    roic = Column(Numeric(12, 6))

    # Growth
    revenue_growth_yoy = Column(Numeric(12, 6))
    earnings_growth_yoy = Column(Numeric(12, 6))
    eps_growth_yoy = Column(Numeric(12, 6))
    fcf_growth_yoy = Column(Numeric(12, 6))

    # Leverage and liquidity
    debt_to_equity = Column(Numeric(12, 6))
    net_debt_to_ebitda = Column(Numeric(12, 6))
    interest_coverage = Column(Numeric(12, 6))
    current_ratio = Column(Numeric(12, 6))
    quick_ratio = Column(Numeric(12, 6))
