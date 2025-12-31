from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class SentimentProvider(ABC):
    """Abstract base class for sentiment providers."""

    @abstractmethod
    async def fetch_market_sentiment(
        self,
        symbols: list[str],
        as_of_date: date,
        window_days: int,
        period: str,
        symbol_names: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch aggregated sentiment for symbols as of a given date."""
        raise NotImplementedError
