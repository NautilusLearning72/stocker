from typing import Dict, Type

from stocker.core.config import settings
from stocker.services.fundamentals.base import FundamentalsProvider
from stocker.services.fundamentals.yfinance_provider import YFinanceFundamentalsProvider

PROVIDERS: Dict[str, Type[FundamentalsProvider]] = {
    "yfinance": YFinanceFundamentalsProvider,
}


def get_fundamentals_provider(name: str = "yfinance") -> FundamentalsProvider:
    """Factory to get fundamentals provider instance."""
    provider_class = PROVIDERS.get(name)
    if not provider_class:
        if settings.USE_YFINANCE_FALLBACK:
            return YFinanceFundamentalsProvider()
        raise ValueError(f"Unknown fundamentals provider: {name}")

    return provider_class()
