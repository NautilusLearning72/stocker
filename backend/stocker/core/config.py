"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables and .env files.
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Stocker"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["local", "development", "staging", "production"] = "local"
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://stocker:dev@localhost:5432/stocker"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TIMEZONE: str = "America/New_York"

    # Trading Configuration
    TRADING_UNIVERSE: list[str] = ["SPY", "TLT", "GLD", "DBC", "UUP"]
    MARKET_CLOSE_HOUR: int = 17  # 5 PM ET
    MARKET_CLOSE_MINUTE: int = 15  # 15 minutes after close

    # Strategy Parameters
    LOOKBACK_DAYS: int = 126
    EWMA_LAMBDA: float = 0.94
    TARGET_VOL: float = 0.10
    SINGLE_INSTRUMENT_CAP: float = 0.35
    GROSS_EXPOSURE_CAP: float = 1.50
    DRAWDOWN_THRESHOLD: float = 0.10
    DRAWDOWN_SCALE_FACTOR: float = 0.50

    # Risk Management
    MIN_NOTIONAL_USD: float = 50.0
    SLIPPAGE_BPS: float = 5.0
    COMMISSION_PER_TRADE: float = 1.0

    # Market Data Provider
    POLYGON_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    USE_YFINANCE_FALLBACK: bool = True

    # Broker Configuration
    BROKER_MODE: Literal["paper", "live"] = "paper"
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"

    # Authentication
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Monitoring & Alerts
    SLACK_WEBHOOK_URL: str = ""
    PAGERDUTY_API_KEY: str = ""
    ALERT_EMAIL: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:4200", "http://localhost:8000"]

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "")


# Global settings instance
settings = Settings()
