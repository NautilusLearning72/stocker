from abc import ABC, abstractmethod
from datetime import date
from typing import Any

class FundamentalsProvider(ABC):
    """Abstract base class for fundamentals providers."""

    @abstractmethod
    def fetch_instrument_metrics(
        self,
        symbols: list[str],
        as_of_date: date,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Fetch investor-facing metrics and instrument info for symbols as of a given date."""
        raise NotImplementedError
