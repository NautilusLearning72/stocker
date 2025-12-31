from typing import Dict, Type

from stocker.core.config import settings
from stocker.services.sentiment.base import SentimentProvider
from stocker.services.sentiment.gdelt_provider import GdeltSentimentProvider

PROVIDERS: Dict[str, Type[SentimentProvider]] = {
    "gdelt": GdeltSentimentProvider,
}


def get_sentiment_provider(name: str = "gdelt") -> SentimentProvider:
    provider_class = PROVIDERS.get(name)
    if not provider_class:
        if name and name != "gdelt" and "gdelt" in PROVIDERS:
            return GdeltSentimentProvider()
        raise ValueError(f"Unknown sentiment provider: {name}")
    return provider_class()
