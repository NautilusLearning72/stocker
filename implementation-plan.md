# Stocker: Implementation Plan

This document provides a comprehensive, logically ordered implementation plan for all components of the Stocker trading platform. Components are organized by dependency order—each section builds on the previous.

For architectural details, see [architecture.md](./architecture.md).
For tooling decisions, see [tooling.md](./tooling.md).
For database schema, see [data-model.md](./data-model.md).

---

## Table of Contents

1. [Phase 1: Foundation](#phase-1-foundation)
2. [Phase 2: Core Strategy Logic](#phase-2-core-strategy-logic)
3. [Phase 3: Data Infrastructure](#phase-3-data-infrastructure)
4. [Phase 4: Stream Consumers](#phase-4-stream-consumers)
5. [Phase 5: Trading Pipeline](#phase-5-trading-pipeline)
6. [Phase 6: API Layer](#phase-6-api-layer)
7. [Phase 7: Frontend](#phase-7-frontend)
8. [Phase 8: Deployment & CI/CD](#phase-8-deployment--cicd)
9. [Phase 9: Paper Trading](#phase-9-paper-trading)
10. [Phase 10: Production Launch](#phase-10-production-launch)

---

## Phase 1: Foundation

**Goal**: Establish the project infrastructure, database models, and base classes.

**Status**: ✅ Partially Complete (monorepo structure done)

### 1.1 Project Setup ✅

| Task | File(s) | Status |
|------|---------|--------|
| Create monorepo structure | `backend/stocker/*` | ✅ Done |
| Configure Poetry dependencies | `backend/pyproject.toml` | ✅ Done |
| Docker Compose for local dev | `docker-compose.yml` | ✅ Done |
| Backend Dockerfile | `backend/Dockerfile` | ✅ Done |
| Core configuration (Pydantic Settings) | `stocker/core/config.py` | ✅ Done |
| Database connection setup | `stocker/core/database.py` | ✅ Done |
| Redis connection setup | `stocker/core/redis.py` | ✅ Done |
| Logging configuration | `stocker/core/logging.py` | ✅ Done |
| FastAPI application skeleton | `stocker/api/main.py` | ✅ Done |
| Environment template | `backend/.env.example` | ✅ Done |

### 1.2 SQLAlchemy Models

| Task | File | Description |
|------|------|-------------|
| Base model with common fields | `stocker/models/base.py` | `id`, `created_at`, `updated_at` mixin |
| DailyBar model | `stocker/models/daily_bar.py` | OHLCV price data |
| Signal model | `stocker/models/signal.py` | Trading signals |
| TargetExposure model | `stocker/models/target_exposure.py` | Portfolio targets |
| Order model | `stocker/models/order.py` | Order instructions |
| Fill model | `stocker/models/fill.py` | Execution confirmations |
| Holding model | `stocker/models/holding.py` | Current positions |
| PortfolioState model | `stocker/models/portfolio_state.py` | Daily portfolio snapshot |
| Model exports | `stocker/models/__init__.py` | Export all models |
| IntradayBar model | `stocker/models/intraday_bar.py` | Sub-daily OHLCV |
| InstrumentInfo model | `stocker/models/instrument_info.py` | Ticker master data |
| CorporateAction model | `stocker/models/corporate_action.py` | Splits, dividends |
| MarketSentiment model | `stocker/models/market_sentiment.py` | News/social sentiment |
| MarketBreadth model | `stocker/models/market_breadth.py` | A/D line, new highs/lows |

**Implementation Details**:

```python
# stocker/models/base.py
from datetime import datetime
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import declarative_mixin

@declarative_mixin
class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@declarative_mixin
class IdMixin:
    id = Column(Integer, primary_key=True, autoincrement=True)
```

```python
# stocker/models/daily_bar.py
from sqlalchemy import Column, String, Date, Numeric, BigInteger, UniqueConstraint
from stocker.core.database import Base
from stocker.models.base import IdMixin, TimestampMixin

class DailyBar(Base, IdMixin, TimestampMixin):
    __tablename__ = "prices_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_prices_daily_symbol_date"),
    )

    symbol = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    open = Column(Numeric(12, 4), nullable=False)
    high = Column(Numeric(12, 4), nullable=False)
    low = Column(Numeric(12, 4), nullable=False)
    close = Column(Numeric(12, 4), nullable=False)
    adj_close = Column(Numeric(12, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
    source = Column(String(50), default="yfinance")
    source_hash = Column(String(64))  # SHA256 for deduplication
```

### 1.3 Alembic Migrations Setup

| Task | File(s) | Description |
|------|---------|-------------|
| Initialize Alembic | `backend/alembic/` | Run `alembic init alembic` |
| Configure async engine | `alembic/env.py` | Use sync driver for migrations |
| Initial migration | `alembic/versions/001_*.py` | Create all tables |

**Commands**:
```bash
cd backend
poetry run alembic init alembic
# Edit alembic/env.py to use settings.sync_database_url
poetry run alembic revision --autogenerate -m "Initial schema"
poetry run alembic upgrade head
```

### 1.4 Base Stream Consumer

| Task | File | Description |
|------|------|-------------|
| BaseStreamConsumer class | `stocker/stream_consumers/base.py` | Abstract base with retry, ACK, DLQ |

**Implementation Details**:

```python
# stocker/stream_consumers/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import asyncio
import logging
import os
from datetime import datetime
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class BaseStreamConsumer(ABC):
    """Base class for Redis Stream consumers."""

    def __init__(
        self,
        redis_url: str,
        stream_name: str,
        consumer_group: str,
        consumer_name: Optional[str] = None,
    ):
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"{consumer_group}-{os.getpid()}"
        self._running = False

    async def start(self) -> None:
        """Start consuming from the stream."""
        # Create consumer group if not exists
        try:
            await self.redis.xgroup_create(
                self.stream_name, self.consumer_group, id="0", mkstream=True
            )
        except Exception:
            pass  # Group likely exists

        self._running = True
        logger.info(f"Consumer {self.consumer_name} starting on {self.stream_name}")
        await self._consume_loop()

    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        while self._running:
            try:
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_name: ">"},
                    count=1,
                    block=5000,
                )
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        await self._process_with_retry(message_id, data)
            except asyncio.CancelledError:
                self._running = False
                break
            except Exception as e:
                logger.error(f"Error in consume loop: {e}")
                await asyncio.sleep(5)

    async def _process_with_retry(
        self, message_id: str, data: Dict[str, Any], max_retries: int = 3
    ) -> None:
        """Process message with retry logic."""
        for attempt in range(max_retries):
            try:
                await self.process_message(message_id, data)
                await self.redis.xack(self.stream_name, self.consumer_group, message_id)
                return
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    await self._send_to_dlq(message_id, data, str(e))

    async def _send_to_dlq(
        self, message_id: str, data: Dict[str, Any], error: str
    ) -> None:
        """Send failed message to dead letter queue."""
        dlq_stream = f"{self.stream_name}-dlq"
        await self.redis.xadd(dlq_stream, {
            "original_id": message_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
            **data,
        })
        await self.redis.xack(self.stream_name, self.consumer_group, message_id)
        logger.error(f"Sent {message_id} to DLQ: {dlq_stream}")

    @abstractmethod
    async def process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process a single message. Must be implemented by subclass."""
        pass

    async def stop(self) -> None:
        """Gracefully stop the consumer."""
        self._running = False
        await self.redis.close()
```

### 1.5 Celery Beat Scheduler

| Task | File | Description |
|------|------|-------------|
| Celery app configuration | `stocker/scheduler/celery_app.py` | Beat schedule (17:15 ET) |

```python
# stocker/scheduler/celery_app.py
from celery import Celery
from celery.schedules import crontab
from stocker.core.config import settings

app = Celery(
    "stocker-scheduler",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

app.conf.update(
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)

app.conf.beat_schedule = {
    "ingest-market-data-daily": {
        "task": "stocker.tasks.market_data.ingest_market_data",
        "schedule": crontab(
            hour=settings.MARKET_CLOSE_HOUR,
            minute=settings.MARKET_CLOSE_MINUTE,
        ),
    },
}
```

**Acceptance Criteria**:
- [x] All SQLAlchemy models created with proper relationships
- [x] Alembic migrations run successfully
- [x] BaseStreamConsumer can connect to Redis and create consumer groups
- [x] Celery Beat starts without errors
- [x] `docker-compose up` brings up all 9 services

---

## Phase 2: Core Strategy Logic

**Goal**: Implement pure business logic classes that can be used for both backtesting and production.

**Dependencies**: None (pure Python, no infrastructure)

### 2.1 Signal Strategy

| Task | File | Description |
|------|------|-------------|
| SignalConfig dataclass | `stocker/strategy/signal_strategy.py` | Configuration parameters |
| Signal dataclass | `stocker/strategy/signal_strategy.py` | Signal output |
| SignalStrategy class | `stocker/strategy/signal_strategy.py` | EWMA volatility, momentum |
| Unit tests | `tests/unit/test_signal_strategy.py` | Test with synthetic data |

**Key Methods**:
- `compute_signal(symbol: str, prices: pd.DataFrame) -> Signal`
- `_compute_ewma_volatility(returns: np.ndarray, lambda_: float) -> float`

**Test Cases**:
- Uptrend → direction = +1
- Downtrend → direction = -1
- High volatility → lower inv_vol_weight
- Insufficient data → raise ValueError

### 2.2 Portfolio Optimizer

| Task | File | Description |
|------|------|-------------|
| RiskConfig dataclass | `stocker/strategy/portfolio_optimizer.py` | Risk parameters |
| TargetExposure dataclass | `stocker/strategy/portfolio_optimizer.py` | Output |
| PortfolioOptimizer class | `stocker/strategy/portfolio_optimizer.py` | Caps, drawdown scaling |
| Unit tests | `tests/unit/test_portfolio_optimizer.py` | Test edge cases |

**Key Methods**:
- `compute_targets(signals: List[Signal], current_drawdown: float) -> List[TargetExposure]`
- `_compute_inverse_vol_weights(signals: List[Signal]) -> Dict[str, float]`
- `_apply_single_cap(exposures: Dict[str, float]) -> Dict[str, float]`
- `_apply_gross_cap(exposures: Dict[str, float]) -> Dict[str, float]`

**Test Cases**:
- Single instrument exceeds 35% → capped
- Gross exposure exceeds 150% → scaled down
- Drawdown > 10% → exposures reduced by 50%
- All signals zero volatility → zero exposure

### 2.3 Backtesting Engine

| Task | File | Description |
|------|------|-------------|
| BacktestConfig dataclass | `stocker/backtesting/backtest_engine.py` | Backtest parameters |
| BacktestResult dataclass | `stocker/backtesting/backtest_engine.py` | Results container |
| BacktestEngine class | `stocker/backtesting/backtest_engine.py` | Historical simulation |
| CLI interface | `stocker/backtesting/cli.py` | Command-line runner |

**Key Metrics to Compute**:
- Total return, CAGR
- Volatility (annualized)
- Sharpe ratio
- Maximum drawdown
- Number of trades

**Acceptance Criteria**:
- [ ] SignalStrategy returns correct direction for up/down trends
- [ ] PortfolioOptimizer respects all risk caps
- [ ] BacktestEngine produces valid equity curve
- [ ] All unit tests pass with >90% coverage

---

## Phase 3: Data Infrastructure

**Goal**: Implement market data ingestion and storage.

**Dependencies**: Phase 1 (models, Redis setup)

### 3.1 Market Data Providers

| Task | File | Description |
|------|------|-------------|
| Provider interface | `stocker/services/market_data/base.py` | Abstract base class |
| yfinance provider | `stocker/services/market_data/yfinance_provider.py` | Historical data |
| Alpaca provider | `stocker/services/market_data/alpaca_provider.py` | Live/daily data |
| Provider factory | `stocker/services/market_data/__init__.py` | Get provider by name |
| Tiingo provider | `stocker/services/market_data/tiingo_provider.py` | Backup data source |

**Implementation Details**:

```python
# stocker/services/market_data/base.py
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
        """Fetch daily OHLCV bars for symbols."""
        pass

    @abstractmethod
    def fetch_latest_bar(self, symbol: str) -> Optional[dict]:
        """Fetch the most recent bar for a symbol."""
        pass
```

```python
# stocker/services/market_data/yfinance_provider.py
import yfinance as yf
from stocker.services.market_data.base import MarketDataProvider

class YFinanceProvider(MarketDataProvider):
    """yfinance provider for backtesting."""

    def fetch_daily_bars(self, symbols, start_date, end_date):
        data = yf.download(
            tickers=symbols,
            start=start_date,
            end=end_date,
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
        )
        # Transform to standard format...
        return data
```

```python
# stocker/services/market_data/alpaca_provider.py
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from stocker.services.market_data.base import MarketDataProvider
from stocker.core.config import settings
from datetime import date
from typing import List, Optional
import pandas as pd

class AlpacaProvider(MarketDataProvider):
    """Alpaca provider for live and paper trading."""

    def __init__(self):
        self.client = StockHistoricalDataClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY
        )

    def fetch_daily_bars(self, symbols: List[str], start_date: date, end_date: date) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            start=start_date,
            end=end_date,
            timeframe=TimeFrame.Day
        )
        bars = self.client.get_stock_bars(request)
        return bars.df.reset_index()

    def fetch_latest_bar(self, symbol: str) -> Optional[dict]:
        # Use the latest bar endpoint
        request = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame.Day)
        bars = self.client.get_stock_bars(request)
        if bars.df.empty:
            return None
        return bars.df.iloc[-1].to_dict()
```

### 3.2 Market Data Service

| Task | File | Description |
|------|------|-------------|
| MarketDataService class | `stocker/services/market_data_service.py` | Orchestrate fetch & store |
| Data validation | `stocker/services/market_data_service.py` | Check for anomalies |
| Deduplication logic | `stocker/services/market_data_service.py` | Use source_hash |

### 3.3 Market Data Ingest Task

| Task | File | Description |
|------|------|-------------|
| Celery task | `stocker/tasks/market_data.py` | Scheduled ingest |
| Publish to Redis Stream | `stocker/tasks/market_data.py` | market-bars stream |

```python
# stocker/tasks/market_data.py
from celery import shared_task
from stocker.scheduler.celery_app import app
from stocker.services.market_data_service import MarketDataService
from stocker.core.redis import get_redis, StreamNames
from stocker.core.config import settings
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)

@app.task(name="stocker.tasks.market_data.ingest_market_data")
def ingest_market_data():
    """Scheduled task to ingest daily market data."""
    service = MarketDataService()
    redis = get_redis()
    today = date.today()

    for symbol in settings.TRADING_UNIVERSE:
        try:
            bar = service.fetch_and_store_bar(symbol, today)

            # Publish to Redis Stream
            redis.xadd(StreamNames.MARKET_BARS, {
                "symbol": symbol,
                "date": str(today),
                "close": str(bar.adj_close),
                "timestamp": datetime.utcnow().isoformat(),
            })
            logger.info(f"Published {symbol} to market-bars stream")
        except Exception as e:
            logger.error(f"Failed to ingest {symbol}: {e}")

    return {"status": "completed", "date": str(today)}
```

**Acceptance Criteria**:
- [ ] yfinance provider fetches 10 years of history correctly
- [ ] Alpaca provider fetches latest bar
- [ ] Data stored in `prices_daily` table with proper deduplication
- [ ] Events published to `market-bars` stream

---

## Phase 4: Stream Consumers

**Goal**: Implement all 6 asyncio stream consumers.

**Dependencies**: Phase 1 (BaseStreamConsumer), Phase 2 (Strategy classes), Phase 3 (Data)

### 4.1 Signal Consumer

| Task | File | Description |
|------|------|-------------|
| SignalConsumer class | `stocker/stream_consumers/signal_consumer.py` | market-bars → signals |
| Entry point | `stocker/stream_consumers/signal_consumer.py` | `if __name__` |

**Stream**: `market-bars` → `signals`
**Consumer Group**: `signal-processors`

### 4.2 Portfolio Consumer

| Task | File | Description |
|------|------|-------------|
| PortfolioConsumer class | `stocker/stream_consumers/portfolio_consumer.py` | signals → targets |
| Aggregation logic | `stocker/stream_consumers/portfolio_consumer.py` | Wait for all symbols |

**Stream**: `signals` → `targets`
**Consumer Group**: `portfolio-processors`

**Note**: Must wait until all symbols have signals for a date before computing targets.

### 4.3 Order Consumer

| Task | File | Description |
|------|------|-------------|
| OrderConsumer class | `stocker/stream_consumers/order_consumer.py` | targets → orders |
| Idempotency logic | `stocker/stream_consumers/order_consumer.py` | Prevent duplicates |

**Stream**: `targets` → `orders`
**Consumer Group**: `order-generators`

**Idempotency Key**: `{portfolio_id}|{date}|{symbol}|{target_hash}`

### 4.4 Broker Consumer

| Task | File | Description |
|------|------|-------------|
| BrokerConsumer class | `stocker/stream_consumers/broker_consumer.py` | orders → fills |
| Paper mode | `stocker/stream_consumers/broker_consumer.py` | Simulate fills |
| Live mode | `stocker/stream_consumers/broker_consumer.py` | Alpaca API |

**Stream**: `orders` → `fills`
**Consumer Group**: `broker-executors`

### 4.5 Ledger Consumer

| Task | File | Description |
|------|------|-------------|
| LedgerConsumer class | `stocker/stream_consumers/ledger_consumer.py` | fills → portfolio-state |
| FIFO accounting | `stocker/stream_consumers/ledger_consumer.py` | Position tracking |
| NAV calculation | `stocker/stream_consumers/ledger_consumer.py` | Mark-to-market |

**Stream**: `fills` → `portfolio-state`
**Consumer Group**: `ledger-processors`

### 4.6 Monitor Consumer

| Task | File | Description |
|------|------|-------------|
| MonitorConsumer class | `stocker/stream_consumers/monitor_consumer.py` | Multi-stream → alerts |
| Anomaly detection | `stocker/stream_consumers/monitor_consumer.py` | Data freshness, etc. |
| Kill switch | `stocker/stream_consumers/monitor_consumer.py` | Emergency halt |

**Streams**: All → `alerts`
**Consumer Group**: `system-monitors`

**Acceptance Criteria**:
- [ ] Each consumer processes messages and publishes to next stream
- [ ] ACK/retry/DLQ logic works correctly
- [ ] Integration tests pass with test Redis
- [ ] End-to-end pipeline test: market-bars → portfolio-state

---

## Phase 5: Trading Pipeline

**Goal**: Implement order management and broker integration.

**Dependencies**: Phase 4 (Consumers)

### 5.1 Order Management

| Task | File | Description |
|------|------|-------------|
| OrderService class | `stocker/services/order_service.py` | Order CRUD |
| Order validation | `stocker/services/order_service.py` | Min notional, etc. |
| Order state machine | `stocker/services/order_service.py` | pending→submitted→filled |

### 5.2 Broker Adapters

| Task | File | Description |
|------|------|-------------|
| BrokerAdapter interface | `stocker/services/broker/base.py` | Abstract base |
| PaperBrokerAdapter | `stocker/services/broker/paper.py` | Simulated execution |
| AlpacaBrokerAdapter | `stocker/services/broker/alpaca.py` | Live execution |

```python
# stocker/services/broker/base.py
from abc import ABC, abstractmethod
from stocker.models import Order, Fill

class BrokerAdapter(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> str:
        """Submit order, return broker order ID."""
        pass

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> dict:
        """Get order status from broker."""
        pass

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order."""
        pass
```

### 5.3 Ledger Service

| Task | File | Description |
|------|------|-------------|
| LedgerService class | `stocker/services/ledger_service.py` | Position management |
| FIFO lot tracking | `stocker/services/ledger_service.py` | Cost basis |
| P&L calculation | `stocker/services/ledger_service.py` | Realized/unrealized |

**Acceptance Criteria**:
- [ ] Paper broker simulates fills with slippage
- [ ] Alpaca broker submits real orders
- [ ] Positions tracked correctly with FIFO
- [ ] NAV and P&L computed accurately

---

## Phase 6: API Layer

**Goal**: Implement REST APIs for the frontend.

**Dependencies**: Phase 5 (Services)

### 6.1 Pydantic Schemas

| Task | File | Description |
|------|------|-------------|
| Portfolio schemas | `stocker/schemas/portfolio.py` | Holdings, NAV, P&L |
| Signal schemas | `stocker/schemas/signal.py` | Signal display |
| Order schemas | `stocker/schemas/order.py` | Order CRUD |
| Admin schemas | `stocker/schemas/admin.py` | Config updates |

### 6.2 API Routers

| Task | File | Description |
|------|------|-------------|
| Portfolio router | `stocker/api/routers/portfolio.py` | GET holdings, NAV |
| Signals router | `stocker/api/routers/signals.py` | GET signals |
| Orders router | `stocker/api/routers/orders.py` | GET/POST orders |
| Admin router | `stocker/api/routers/admin.py` | Config, kill switch |
| Health router | `stocker/api/routers/health.py` | Health checks |

### 6.3 SSE Streaming

| Task | File | Description |
|------|------|-------------|
| SSE endpoint | `stocker/api/routers/stream.py` | Real-time updates |
| Redis Pub/Sub integration | `stocker/api/routers/stream.py` | Subscribe to streams |

```python
# stocker/api/routers/stream.py
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from stocker.core.redis import get_async_redis, StreamNames

router = APIRouter()

@router.get("/stream/{portfolio_id}")
async def stream_portfolio(portfolio_id: str):
    async def event_generator():
        redis = await get_async_redis()
        last_id = "$"
        while True:
            messages = await redis.xread(
                {StreamNames.PORTFOLIO_STATE: last_id},
                count=1,
                block=5000,
            )
            for stream, msgs in messages:
                for msg_id, data in msgs:
                    last_id = msg_id
                    if data.get("portfolio_id") == portfolio_id:
                        yield {"event": "portfolio_state", "data": data}

    return EventSourceResponse(event_generator())
```

### 6.4 Authentication

| Task | File | Description |
|------|------|-------------|
| JWT utils | `stocker/core/security.py` | Token create/verify |
| Auth dependency | `stocker/api/deps.py` | get_current_user |
| Login endpoint | `stocker/api/routers/auth.py` | POST /auth/token |

**Acceptance Criteria**:
- [ ] All endpoints return correct data
- [ ] SSE streams real-time updates
- [ ] JWT authentication works
- [ ] OpenAPI docs complete

---

## Phase 7: Frontend

**Goal**: Build Angular dashboard.

**Dependencies**: Phase 6 (API)

### 7.1 Angular Setup

| Task | Description |
|------|-------------|
| Create Angular project | `ng new stocker-ui` in `frontend/` |
| Install dependencies | Angular Material, NgRx, ApexCharts |
| Configure environments | API URL for local/staging/prod |

### 7.2 Core Module

| Task | File | Description |
|------|------|-------------|
| Auth service | `core/services/auth.service.ts` | JWT handling |
| API service | `core/services/api.service.ts` | HTTP client |
| SSE service | `core/services/sse.service.ts` | EventSource |
| Auth guard | `core/guards/auth.guard.ts` | Route protection |

### 7.3 NgRx State

| Task | File | Description |
|------|------|-------------|
| Portfolio state | `features/dashboard/state/` | Holdings, NAV |
| Signals state | `features/signals/state/` | Current signals |
| Orders state | `features/orders/state/` | Order history |

### 7.4 Components

| Task | Directory | Description |
|------|-----------|-------------|
| Dashboard | `features/dashboard/` | NAV chart, holdings table |
| Signals view | `features/signals/` | Signal grid, momentum chart |
| Admin panel | `features/admin/` | Kill switch, config editor |
| Login | `features/auth/` | Login form |

**Acceptance Criteria**:
- [ ] Dashboard displays real-time NAV
- [ ] Holdings table updates via SSE
- [ ] Signals view shows all current signals
- [ ] Admin can trigger kill switch

---

## Phase 8: Deployment & CI/CD

**Goal**: Set up AWS infrastructure and CI/CD pipeline.

**Dependencies**: Phase 6 (Backend complete)

### 8.1 GitHub Actions

| Task | File | Description |
|------|------|-------------|
| CI workflow | `.github/workflows/ci.yml` | Test, lint, type-check |
| CD workflow | `.github/workflows/cd.yml` | Build, push, deploy |

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
      redis:
        image: redis:7-alpine
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Poetry
        run: pip install poetry
      - name: Install dependencies
        run: cd backend && poetry install
      - name: Run tests
        run: cd backend && poetry run pytest
      - name: Run linting
        run: cd backend && poetry run ruff check .
      - name: Run type checking
        run: cd backend && poetry run mypy stocker/
```

### 8.2 AWS Infrastructure

| Task | Description |
|------|-------------|
| ECR repositories | Create repos for backend image |
| ECS cluster | Create Fargate cluster |
| ECS task definitions | 9 task definitions (see architecture.md) |
| ECS services | Create services for each task |
| RDS PostgreSQL | Create Multi-AZ database |
| ElastiCache Redis | Create Redis cluster |
| ALB | Create load balancer for API |
| VPC & Security Groups | Network configuration |
| Secrets Manager | Store API keys and secrets |

### 8.3 Terraform (Optional)

| Task | File | Description |
|------|------|-------------|
| VPC module | `infra/terraform/vpc.tf` | Network setup |
| ECS module | `infra/terraform/ecs.tf` | Cluster & services |
| RDS module | `infra/terraform/rds.tf` | Database |
| Redis module | `infra/terraform/redis.tf` | Cache |

**Acceptance Criteria**:
- [ ] CI runs on every PR
- [ ] CD deploys to staging on develop merge
- [ ] CD deploys to prod on main merge (manual approval)
- [ ] All AWS resources created and connected

---

## Phase 9: Paper Trading

**Goal**: Run 30 days of paper trading to validate the system.

**Dependencies**: Phase 8 (Deployed to staging)

### 9.1 Paper Trading Setup

| Task | Description |
|------|-------------|
| Configure paper mode | Set `BROKER_MODE=paper` |
| Seed historical data | Load 1 year of daily bars |
| Initial portfolio | Set starting cash ($100,000) |

### 9.2 Daily Monitoring

| Task | Description |
|------|-------------|
| Check signals | Verify signals generated daily |
| Check orders | Verify orders submitted correctly |
| Check fills | Verify fills recorded |
| Check P&L | Verify NAV calculation |
| Check alerts | Monitor for anomalies |

### 9.3 Reconciliation

| Task | Description |
|------|-------------|
| Compare to backtest | Do live signals match historical? |
| Check slippage | Is simulated slippage realistic? |
| Identify issues | Log any discrepancies |

**Acceptance Criteria**:
- [ ] 30 days of successful paper trading
- [ ] No critical errors or missed signals
- [ ] P&L tracking accurate
- [ ] System stable under production load

---

## Phase 10: Production Launch

**Goal**: Go live with real capital.

**Dependencies**: Phase 9 (Paper trading validated)

### 10.1 Pre-Launch Checklist

| Task | Description |
|------|-------------|
| Fund Alpaca account | Deposit initial capital |
| Switch to live mode | Set `BROKER_MODE=live` |
| Update data provider | Upgrade to Alpaca Unlimited if needed |
| Verify kill switch | Test emergency halt |
| Configure alerts | Set up PagerDuty/Slack |
| Create runbook | Document operational procedures |

### 10.2 Go-Live

| Task | Description |
|------|-------------|
| Deploy to production | Update ECS services |
| Monitor first trade | Watch first order submission |
| Verify fills | Confirm broker fills match system |

### 10.3 Ongoing Operations

| Task | Description |
|------|-------------|
| Daily reconciliation | Compare system vs broker |
| Weekly review | Analyze P&L, strategy performance |
| Monthly rebalance | Review and adjust universe if needed |

**Acceptance Criteria**:
- [ ] First live trade executed successfully
- [ ] Broker fills match system records
- [ ] Monitoring alerts working
- [ ] Runbook documented

---

## Component Dependencies Graph

```
Phase 1: Foundation
    ├── Models
    ├── Migrations
    ├── BaseStreamConsumer
    └── Celery Beat
            │
            ▼
Phase 2: Core Strategy Logic
    ├── SignalStrategy (pure)
    ├── PortfolioOptimizer (pure)
    └── BacktestEngine (pure)
            │
            ▼
Phase 3: Data Infrastructure
    ├── MarketDataProviders
    ├── MarketDataService
    └── IngestTask
            │
            ▼
Phase 4: Stream Consumers
    ├── SignalConsumer
    ├── PortfolioConsumer
    ├── OrderConsumer
    ├── BrokerConsumer
    ├── LedgerConsumer
    └── MonitorConsumer
            │
            ▼
Phase 5: Trading Pipeline
    ├── OrderService
    ├── BrokerAdapters
    └── LedgerService
            │
            ▼
Phase 6: API Layer
    ├── Schemas
    ├── Routers
    ├── SSE Streaming
    └── Authentication
            │
            ▼
Phase 7: Frontend
    ├── Angular Setup
    ├── NgRx State
    └── Components
            │
            ▼
Phase 8: Deployment
    ├── CI/CD
    └── AWS Infrastructure
            │
            ▼
Phase 9: Paper Trading
            │
            ▼
Phase 10: Production Launch
```

---

## Quick Reference: Key Files

| Component | File Path |
|-----------|-----------|
| Configuration | `stocker/core/config.py` |
| Database | `stocker/core/database.py` |
| Redis | `stocker/core/redis.py` |
| Signal Strategy | `stocker/strategy/signal_strategy.py` |
| Portfolio Optimizer | `stocker/strategy/portfolio_optimizer.py` |
| Backtest Engine | `stocker/backtesting/backtest_engine.py` |
| Base Consumer | `stocker/stream_consumers/base.py` |
| Signal Consumer | `stocker/stream_consumers/signal_consumer.py` |
| Market Data Task | `stocker/tasks/market_data.py` |
| Celery App | `stocker/scheduler/celery_app.py` |
| FastAPI Main | `stocker/api/main.py` |


🔌 Live Paper Trading Test
Configure Alpaca paper trading API keys in .env
Trigger market data ingestion to run the full pipeline end-to-end
Verify orders appear in paper account
📈 Add Equity Curve Chart
Integrate ApexCharts into Dashboard
Fetch historical NAV from backend
Display interactive equity curve
🐳 Deployment Setup
Containerize the Angular frontend
Create a production Docker Compose profile
Add Nginx reverse proxy for unified access
🧪 Add Unit/Integration Tests
Pytest for backend routers
Angular Karma tests for components