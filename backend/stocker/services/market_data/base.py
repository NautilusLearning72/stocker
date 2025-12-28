from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
import pandas as pd

class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def fetch_daily_bars(
        self,
        symbols: List[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV bars for symbols.
        Returns DataFrame with columns: [symbol, date, open, high, low, close, adj_close, volume]
        """
        pass

    @abstractmethod
    def fetch_latest_bar(self, symbol: str) -> Optional[dict]:
        """Fetch the most recent bar for a symbol."""
        pass
