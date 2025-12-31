"""
Strategy configuration storage.

Stores trading parameters in the database, allowing runtime configuration
via the admin UI. Values here take precedence over .env settings.
"""

from sqlalchemy import Column, String, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import TimestampMixin


class StrategyConfig(Base, TimestampMixin):
    """
    Key-value storage for strategy configuration parameters.

    On startup, missing keys are seeded from .env/defaults.
    DB values take precedence over environment variables.
    """
    __tablename__ = "strategy_config"

    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)
    value_type = Column(String(20), nullable=False)  # int, float, bool, str
    category = Column(String(50), nullable=False)    # strategy, risk, confirmation, exit, diversification, sizing
    description = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint('key', name='uq_strategy_config_key'),
    )

    def __repr__(self) -> str:
        return f"<StrategyConfig(key={self.key}, value={self.value}, category={self.category})>"
