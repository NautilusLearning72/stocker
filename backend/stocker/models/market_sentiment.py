from sqlalchemy import Column, String, Date, Numeric, Integer, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class MarketSentiment(Base, IdMixin, TimestampMixin):
    """
    Aggregated sentiment data derived from news/social.
    """
    __tablename__ = "market_sentiment"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "date",
            "source",
            "period",
            "window_days",
            name="uq_market_sentiment_symbol_date_source_period",
        ),
    )

    symbol = Column(String(20), index=True, nullable=True)  # Nullable if market-wide
    date = Column(Date, nullable=False, index=True)
    source = Column(String(50), nullable=False)
    period = Column(String(10), nullable=False, default="WEEKLY")
    window_days = Column(Integer, nullable=False, default=7)
    sentiment_score = Column(Numeric(5, 4), nullable=False)  # -1.0 to 1.0
    sentiment_magnitude = Column(Numeric(10, 4))
    article_count = Column(Integer)
    positive_count = Column(Integer)
    neutral_count = Column(Integer)
    negative_count = Column(Integer)
    source_hash = Column(String(64))
