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
    DEFAULT_STRATEGY_ID: str = "main_strategy"
    USE_DYNAMIC_UNIVERSE: bool = False
    UNIVERSE_SIZE: int = 250
    UNIVERSE_LOOKBACK_DAYS: int = 20
    UNIVERSE_SOURCE: str = "alpaca_most_actives"
    UNIVERSE_SCREENER_BY: str = "volume"
    UNIVERSE_SCREENER_MAX: int = 100
    UNIVERSE_REFRESH_HOUR: int = 18
    UNIVERSE_REFRESH_MINUTE: int = 0

    # Strategy Parameters
    LOOKBACK_DAYS: int = 126
    EWMA_LAMBDA: float = 0.94
    TARGET_VOL: float = 0.10
    SINGLE_INSTRUMENT_CAP: float = 0.35
    GROSS_EXPOSURE_CAP: float = 1.50
    DRAWDOWN_THRESHOLD: float = 0.10
    DRAWDOWN_SCALE_FACTOR: float = 0.50

    # Trend Confirmation Settings
    CONFIRMATION_ENABLED: bool = False
    CONFIRMATION_TYPE: Literal["donchian", "dual_ma", "both"] = "donchian"
    DONCHIAN_PERIOD: int = 20
    MA_FAST_PERIOD: int = 50
    MA_SLOW_PERIOD: int = 200

    # Risk Management
    MIN_NOTIONAL_USD: float = 50.0
    SLIPPAGE_BPS: float = 5.0
    COMMISSION_PER_TRADE: float = 1.0
    ALLOW_SHORT_SELLING: bool = True
    ORDER_EXECUTION_TYPE: Literal["moo", "market", "auto"] = "auto"  # moo=Market-on-Open, market=immediate, auto=dynamic
    # Alpaca OPG submission window (ET)
    OPG_WINDOW_START_HOUR: int = 19
    OPG_WINDOW_START_MINUTE: int = 0
    OPG_WINDOW_END_HOUR: int = 9
    OPG_WINDOW_END_MINUTE: int = 28
    EXTENDED_HOURS_LIMIT_BPS: float = 10.0

    # Fractional Sizing Settings
    FRACTIONAL_SIZING_ENABLED: bool = True
    FRACTIONAL_DECIMALS: int = 4
    MIN_NOTIONAL_MODE: Literal["fixed", "nav_scaled", "liquidity_scaled"] = "fixed"
    MIN_NOTIONAL_NAV_BPS: float = 5.0  # 5 bps of NAV as min when nav_scaled

    # Diversification Controls
    DIVERSIFICATION_ENABLED: bool = False
    SECTOR_CAP: float = 0.50  # Max 50% per sector
    ASSET_CLASS_CAP: float = 0.60  # Max 60% per asset class
    CORRELATION_THROTTLE_ENABLED: bool = False
    CORRELATION_THRESHOLD: float = 0.70  # Throttle when corr > 0.7
    CORRELATION_LOOKBACK: int = 60  # 60-day rolling correlation
    CORRELATION_SCALE_FACTOR: float = 0.50  # Scale new adds by 50% when corr high

    # Signal Enhancement Settings
    ENHANCEMENT_ENABLED: bool = False  # Enable signal enhancement
    CONVICTION_ENABLED: bool = True  # Scale by trend conviction
    SENTIMENT_ENABLED: bool = True  # Use market sentiment
    REGIME_ENABLED: bool = True  # Adjust for market regime
    QUALITY_ENABLED: bool = True  # Factor in instrument quality
    MIN_LOOKBACK_RETURN: float = 0.02  # 2% minimum for full conviction
    CONVICTION_SCALE_MIN: float = 0.3  # Minimum scaling for weak signals
    SENTIMENT_WEIGHT: float = 0.2  # How much sentiment affects signal
    SENTIMENT_CONTRARIAN: bool = False  # Fade extreme sentiment
    REGIME_DEFENSIVE_SCALE: float = 0.5  # Scale down in risk-off
    BREADTH_THRESHOLD: float = 0.4  # Below this = risk-off

    # Exit Rule Settings
    EXIT_RULES_ENABLED: bool = False
    TRAILING_STOP_ATR_MULTIPLE: float = 3.0  # Exit if retraces 3 ATRs from peak
    ATR_EXIT_MULTIPLE: float = 2.0  # Exit if moves 2 ATRs against entry
    ATR_PERIOD: int = 14  # ATR calculation period
    PERSISTENCE_DAYS: int = 3  # Days signal must persist before flip

    # Market Data Provider
    POLYGON_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    USE_YFINANCE_FALLBACK: bool = True
    FUNDAMENTALS_PROVIDER: str = "yfinance"
    FUNDAMENTALS_REFRESH_HOUR: int = 19
    FUNDAMENTALS_REFRESH_MINUTE: int = 0
    FUNDAMENTALS_MAX_RETRIES: int = 3
    FUNDAMENTALS_RETRY_BACKOFF_SEC: float = 1.0

    # Corporate Actions Provider
    CORP_ACTIONS_PROVIDER: str = "yfinance"
    CORP_ACTIONS_LOOKBACK_DAYS: int = 90
    CORP_ACTIONS_REFRESH_DAY: int = 0  # Monday
    CORP_ACTIONS_REFRESH_HOUR: int = 21
    CORP_ACTIONS_REFRESH_MINUTE: int = 0
    CORP_ACTIONS_MAX_RETRIES: int = 3
    CORP_ACTIONS_RETRY_BACKOFF_SEC: float = 1.0

    # Sentiment Data Provider
    SENTIMENT_PROVIDER: str = "gdelt"
    SENTIMENT_PERIOD: Literal["DAILY", "WEEKLY"] = "WEEKLY"
    SENTIMENT_LOOKBACK_DAYS: int = 7
    SENTIMENT_REFRESH_DAY: int = 0  # Monday
    SENTIMENT_REFRESH_HOUR: int = 20
    SENTIMENT_REFRESH_MINUTE: int = 0
    SENTIMENT_ONLY_MISSING: bool = True
    SENTIMENT_MAX_RETRIES: int = 3
    SENTIMENT_RETRY_BACKOFF_SEC: float = 1.0
    SENTIMENT_REQUEST_TIMEOUT_SEC: float = 10.0
    SENTIMENT_REQUEST_DELAY_SEC: float = 0.2
    SENTIMENT_MAX_CONCURRENCY: int = 4
    SENTIMENT_RATE_LIMIT_PER_SEC: float = 2.0
    SENTIMENT_MAX_SYMBOLS: int = 0

    # Derived Metrics
    DERIVED_METRICS_LOOKBACK_DAYS: int = 300
    DERIVED_METRICS_SENTIMENT_LOOKBACK_DAYS: int = 90
    DERIVED_METRICS_USE_GLOBAL_UNIVERSE: bool = True
    DERIVED_METRICS_CALC_VERSION: str = "v1"

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
    HEALTH_CONSUMER_WARN_SEC: int = 300
    HEALTH_CONSUMER_ERROR_SEC: int = 900

    # Portfolio Sync (Alpaca)
    PORTFOLIO_SYNC_LOOKBACK_DAYS: int = 30
    PORTFOLIO_SYNC_ORDER_LIMIT: int = 500

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:4200",
        "http://web.localhost:4200",
        "http://localhost:8000",
    ]

    @property
    def sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        return self.DATABASE_URL.replace("+asyncpg", "")


# Global settings instance
settings = Settings()
