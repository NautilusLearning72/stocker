from sqlalchemy import Column, String, Date, Numeric, Integer
from stocker.core.database import Base
from stocker.models.base import IdMixin

class MarketSentiment(Base, IdMixin):
    """
    Aggregated sentiment data derived from news/social.
    """
    __tablename__ = "market_sentiment"

    symbol = Column(String(20), index=True, nullable=True)  # Nullable if market-wide
    date = Column(Date, nullable=False, index=True)
    source = Column(String(50), nullable=False)
    sentiment_score = Column(Numeric(5, 4), nullable=False)  # -1.0 to 1.0
    sentiment_magnitude = Column(Numeric(10, 4))
    article_count = Column(Integer)
