from typing import Dict, Type
from stocker.services.market_data.base import MarketDataProvider
from stocker.services.market_data.yfinance_provider import YFinanceProvider
from stocker.services.market_data.alpaca_provider import AlpacaProvider
from stocker.core.config import settings

PROVIDERS: Dict[str, Type[MarketDataProvider]] = {
    "yfinance": YFinanceProvider,
    "alpaca": AlpacaProvider,
}

def get_market_data_provider(name: str = "yfinance") -> MarketDataProvider:
    """Factory to get provider instance."""
    provider_class = PROVIDERS.get(name)
    if not provider_class:
        # Fallback based on config or default
        if settings.USE_YFINANCE_FALLBACK:
            return YFinanceProvider()
        raise ValueError(f"Unknown provider: {name}")
    
    return provider_class()
