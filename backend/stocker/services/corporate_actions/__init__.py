from typing import Dict, Type

from stocker.services.corporate_actions.base import CorporateActionsProvider
from stocker.services.corporate_actions.yfinance_provider import (
    YFinanceCorporateActionsProvider,
)

PROVIDERS: Dict[str, Type[CorporateActionsProvider]] = {
    "yfinance": YFinanceCorporateActionsProvider,
}


def get_corporate_actions_provider(name: str = "yfinance") -> CorporateActionsProvider:
    provider_class = PROVIDERS.get(name)
    if not provider_class:
        raise ValueError(f"Unknown corporate actions provider: {name}")
    return provider_class()
