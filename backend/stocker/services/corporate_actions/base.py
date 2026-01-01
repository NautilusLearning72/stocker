from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class CorporateActionsProvider(ABC):
    """Abstract base class for corporate actions providers."""

    @abstractmethod
    def fetch_corporate_actions(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch corporate actions for symbols over a date range."""
        raise NotImplementedError
