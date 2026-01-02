# Stocker: Systematic Trading Platform Architecture

## Executive Summary

This document defines the architecture for **Stocker**, a systematic trading platform implementing a volatility-targeted trend-following strategy. The system uses a **Python/FastAPI** stack with an event-driven microservices architecture optimized for daily algorithmic trading.

**Key Architecture Decisions:**
- **Backend**: Python 3.12+ with FastAPI + SQLAlchemy + Celery
- **Event Streaming**: Redis Streams (lighter weight than Kafka for daily trading)
- **Database**: PostgreSQL with Alembic migrations
- **Frontend**: Angular 18+ with NgRx state management
- **Infrastructure**: AWS ECS Fargate, RDS PostgreSQL, ElastiCache Redis
- **Deployment**: GitHub Actions CI/CD with blue/green deployments
- **Local Development**: Docker Compose with local Postgres/Redis

**Total Estimated AWS Cost**: ~$250/month (~$100/month with Fargate Spot)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Technology Stack](#2-technology-stack)
3. [Service Architecture (7 Microservices)](#3-service-architecture-7-microservices)
4. [Backtesting Architecture](#4-backtesting-architecture)
5. [Data Models](#5-data-models)
6. [Angular Frontend](#6-angular-frontend)
7. [AWS Infrastructure](#7-aws-infrastructure)
8. [Deployment Pipeline](#8-deployment-pipeline)
9. [Project Structure](#9-project-structure)
10. [Risks & Decisions](#10-risks--decisions)

**See also**: [implementation-plan.md](./implementation-plan.md) for detailed implementation tasks.

---

## 1. Architecture Overview

### 1.1 High-Level System Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ANGULAR UI (Port 4200)                        │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐                  │
│  │  Dashboard   │  │   Signals   │  │    Admin     │                  │
│  │   (NgRx)     │  │    View     │  │    Panel     │                  │
│  └──────────────┘  └─────────────┘  └──────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
        ┌────────────────┐  ┌────────────┐  ┌────────────────┐
        │  Trading API   │  │ Admin API  │  │  SSE Stream    │
        │  (FastAPI)     │  │ (FastAPI)  │  │  (FastAPI)     │
        │  Port 8001     │  │ Port 8002  │  │  Port 8003     │
        └────────────────┘  └────────────┘  └────────────────┘
                    │            │            │
                    └────────────┼────────────┘
                                 │
                    ┌────────────▼───────────────┐
                    │    PostgreSQL (RDS)        │
                    │  - prices_daily            │
                    │  - signals                 │
                    │  - orders / fills          │
                    │  - portfolio_state         │
                    └────────────────────────────┘
                                 │
        ┌────────────────────────┼──────────────────────┐
        │                        │                      │
        │         REDIS (ElastiCache)                   │
        │  ┌─────────────────────────────────────────┐  │
        │  │  Redis Streams (Event Bus)              │  │
        │  │  - market-bars                          │  │
        │  │  - signals                              │  │
        │  │  - targets                              │  │
        │  │  - orders                               │  │
        │  │  - fills                                │  │
        │  │  - portfolio-state                      │  │
        │  │  - alerts                               │  │
        │  └─────────────────────────────────────────┘  │
        │                                                │
        │  ┌─────────────────────────────────────────┐  │
        │  │  Celery Task Queue                      │  │
        │  └─────────────────────────────────────────┘  │
        └────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼──────────────────────┐
        │                        │                      │
        ▼                        ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐
│ Celery Beat     │  │ Asyncio         │  │ Asyncio          │
│ (Scheduler)     │  │ Consumer 1      │  │ Consumer N       │
│                 │  │                 │  │                  │
│ - Ingestor Task │  │ - Signal Engine │  │ - Monitoring     │
│   (17:15 ET)    │  │ - Portfolio Eng │  │ - Broker Adapter │
│                 │  │ - Order Manager │  │ - Ledger         │
└─────────────────┘  └─────────────────┘  └──────────────────┘
```

### 1.2 Daily Trading Data Flow

```
17:00 ET - Market Close
    │
    ▼
[1] Market Data Ingestor (Celery scheduled task)
    │ - Fetch daily OHLCV from provider (Polygon/Alpha Vantage)
    │ - Validate data quality
    │ - Store: prices_daily table
    │ - Publish: market-bars stream
    │
    ▼
[2] Signal Engine (Asyncio consumer)
    │ - Compute 126-day momentum
    │ - Compute EWMA volatility (λ=0.94)
    │ - Determine direction (+1/-1)
    │ - Store: signals table
    │ - Publish: signals stream
    │
    ▼
[3] Portfolio/Risk Engine (Asyncio consumer)
    │ - Compute inverse-volatility weights
    │ - Apply caps (35% single, 150% gross)
    │ - Apply drawdown circuit breaker
    │ - Store: target_exposures table
    │ - Publish: targets stream
    │
    ▼
[4] Order Manager (Asyncio consumer)
    │ - Diff current holdings vs targets
    │ - Generate Market-On-Open orders
    │ - Apply idempotency checks
    │ - Store: orders table
    │ - Publish: orders stream
    │
    ▼
[5] Broker Adapter (Asyncio consumer)
    │ - Paper: simulate fills at next open
    │ - Live: submit to broker API (Alpaca/IB)
    │ - Store: fills table
    │ - Publish: fills stream
    │
    ▼
[6] Ledger (Asyncio consumer)
    │ - Update positions (FIFO accounting)
    │ - Compute NAV, P&L, drawdown
    │ - Store: holdings, portfolio_state tables
    │ - Publish: portfolio-state stream
    │
    ▼
[7] Monitoring (Asyncio consumer)
    │ - Check for anomalies
    │ - Trigger alerts if needed
    │ - Publish: alerts stream
    │
    ▼
[Angular UI] Real-time updates via Server-Sent Events

Next Day 09:30 ET - Market Open
    │
    ▼
[5] Broker Adapter executes orders
```

---

## 2. Technology Stack

### 2.1 Backend Technologies

| Component | Technology | Justification |
|-----------|------------|---------------|
| **Language** | Python 3.12+ | ML ecosystem, rapid development, team expertise |
| **API Framework** | FastAPI 0.115+ | Async support, auto-docs, excellent performance |
| **ORM** | SQLAlchemy 2.0+ | Industry standard, type-safe, PostgreSQL support |
| **Scheduler** | Celery Beat 5.4+ | Distributed cron for scheduled tasks (NOT workers) |
| **Event Streaming** | Redis Streams 7.x | Event bus with consumer groups, replay capability |
| **Event Consumers** | Python asyncio | Native async/await for stream processing |
| **Validation** | Pydantic 2.10+ | Type safety, automatic validation |
| **Testing** | pytest 8.x | Powerful fixtures, async support |
| **Linting** | Ruff 0.8+ | Fast linter/formatter |
| **Type Checking** | mypy 1.13+ | Static type checking for production |
| **Dependencies** | Poetry 1.8+ | Modern dependency resolution, lock files |


### 2.3 Database & Migrations

| Component | Technology | Justification |
|-----------|------------|---------------|
| **Database** | PostgreSQL 16+ | ACID compliance, window functions, Python support |
| **Migrations** | Alembic 1.14+ | **NOT Flyway** - SQLAlchemy-native, autogenerate |
| **Async Driver** | asyncpg 0.30+ | Async Postgres driver for FastAPI |

**Critical Decision: Alembic > Flyway**

Flyway is a Java tool. For Python/SQLAlchemy:
- **Alembic** auto-generates migrations from model changes
- Type-safe migrations in Python (not manual SQL)
- Better FastAPI/SQLAlchemy integration

```bash
# Alembic workflow
# 1. Modify SQLAlchemy models
# 2. Auto-generate migration
alembic revision --autogenerate -m "Add drawdown threshold"
# 3. Review generated migration
# 4. Apply
alembic upgrade head
```

### 2.4 Frontend Technologies

| Component | Technology | Justification |
|-----------|------------|---------------|
| **Framework** | Angular 18+ | Enterprise-grade, complex dashboards |
| **State Mgmt** | NgRx 18+ | Redux pattern, time-travel debugging |
| **UI Library** | Angular Material 18+ | Professional components, accessibility |
| **Charts** | ApexCharts 3.54+ | Trading-focused visualizations |
| **Real-Time** | Server-Sent Events | Simpler than WebSockets, auto-reconnect |

**Why SSE over WebSockets?**
- Simpler server implementation (no connection state)
- Auto-reconnect built-in
- Sufficient for daily trading updates
- Native browser support

### 2.5 Local Development

**Critical Decision: Docker Compose Locally, NOT AWS RDS**

❌ **AWS RDS for Local Dev Issues:**
- Network latency on every query
- Can't work offline
- Costs money 24/7
- Hard to reset to clean state
- Difficult test isolation

✅ **Docker Compose Benefits:**
- Instant local setup
- Offline development
- Free
- Easy to reset (`docker-compose down -v`)
- Fast test runs

**Environment Strategy:**
- **Local**: Docker Compose (Postgres + Redis)
- **CI**: Ephemeral Docker containers
- **Staging**: AWS RDS (small instance)
- **Production**: AWS RDS (Multi-AZ)

---

## 3. Service Architecture (7 Microservices)

### 3.1 Service 1: Market Data Ingestor

**Type**: Celery scheduled task (NOT a REST API)
**Schedule**: Daily at 17:15 ET (after market close)

**Responsibilities:**
1. Fetch daily OHLCV bars from provider
2. Validate data quality
3. Store in `prices_daily` table
4. Publish to `market-bars` Redis Stream

**Data Providers:**
- **Polygon.io** - $199/month, excellent API ✅ Recommended
- **Alpha Vantage** - Free tier, good for testing
- **yfinance** - Free, unreliable for production

### 3.2 Service 2: Signal Engine

**Type**: Python asyncio consumer (consumes Redis Stream)
**Trigger**: New events on `market-bars` stream

**Responsibilities:**
1. Query last 252 bars from Postgres
2. Compute log returns
3. Compute EWMA volatility (λ=0.94)
4. Compute 126-day momentum
5. Determine direction (+1 long, -1 short)
6. Store in `signals` table
7. Publish to `signals` Redis Stream

**Core Calculations:**
- **EWMA Volatility**: RiskMetrics style (λ=0.94), annualized
- **Momentum**: 126-day lookback return (≈6 months)
- **Direction**: Sign of momentum (+1 or -1)

### 3.3 Service 3: Portfolio/Risk Engine

**Type**: Python asyncio consumer (consumes Redis Stream)
**Trigger**: New events on `signals` stream

**Responsibilities:**
1. Compute inverse-volatility weights (equal risk contribution)
2. Apply directional signals
3. Apply risk caps:
   - Single instrument: 35% max
   - Gross exposure: 150% max
4. Apply drawdown circuit breaker (reduce 50% if DD > 10%)
5. Store in `target_exposures` table
6. Publish to `targets` Redis Stream

**Risk Management:**
- **Inverse-vol weighting**: Higher weight to lower volatility assets
- **Position caps**: Prevent concentration risk
- **Circuit breaker**: Automatic de-risk on drawdowns

### 3.4 Service 4: Order Manager

**Type**: Python asyncio consumer (consumes Redis Stream)
**Trigger**: New events on `targets` stream

**Responsibilities:**
1. Fetch current holdings
2. Compute delta: desired_qty - current_qty
3. Generate Market-On-Open orders
4. Apply minimum notional filter ($50)
5. Apply idempotency (prevent duplicates)
6. Store in `orders` table
7. Publish to `orders` Redis Stream

**Idempotency:**
- Order key: `portfolio_id|date|symbol|target_hash`
- SHA256 hash prevents duplicate submissions
- Database unique constraint enforces

### 3.5 Service 5: Broker Adapter

**Type**: Python asyncio consumer + FastAPI (webhooks)
**Trigger**: Consumes `orders` Redis Stream

**Modes:**
1. **Paper Mode**: Simulate fills at next day's open with slippage
2. **Live Mode**: Submit to broker API (Alpaca, Interactive Brokers)

**Responsibilities:**
1. Execute orders via broker
2. Listen for fill confirmations
3. Store in `fills` table
4. Publish to `fills` Redis Stream

**Paper Trading Slippage Model:**
- Base fill price: next day's open
- Slippage: 5 bps random (0-0.05%)
- Commission: $1 per trade

### 3.6 Service 6: Ledger

**Type**: Python asyncio consumer (consumes Redis Stream)
**Trigger**: New events on `fills` stream

**Responsibilities:**
1. Update positions (FIFO accounting)
2. Compute NAV (cash + mark-to-market)
3. Compute realized P&L
4. Compute unrealized P&L
5. Compute drawdown from peak
6. Store in `holdings`, `portfolio_state` tables
7. Publish to `portfolio-state` Redis Stream

**Accounting:**
- **FIFO**: First-in-first-out position accounting
- **NAV**: Cash + sum of (position × current price)
- **Drawdown**: (Peak NAV - Current NAV) / Peak NAV

### 3.7 Service 7: Monitoring & Alerts

**Type**: Python asyncio consumer + FastAPI (health endpoints)
**Trigger**: Consumes all streams + scheduled checks

**Responsibilities:**
1. Monitor all Redis Streams for anomalies
2. Check data freshness
3. Detect signal anomalies (volatility spikes)
4. Monitor drawdown thresholds
5. Trigger kill switch if needed
6. Send alerts (email, Slack, PagerDuty)
7. Publish to `alerts` Redis Stream

**Alert Channels:**
- **INFO/WARNING**: Slack notification
- **ERROR**: Email + Slack
- **CRITICAL**: Email + Slack + PagerDuty incident

**Kill Switch:**
- Cancels all pending orders
- Creates liquidation orders (if live)
- Halts trading until manual override

### 3.8 Worker Pattern Architecture

**Critical Design Principle**: Clear separation between **scheduling** and **event processing**.

#### Celery Beat: Scheduling ONLY

**Purpose**: Time-based task triggering (distributed cron replacement)

```python
# Celery Beat Schedule
app.conf.beat_schedule = {
    "ingest-market-data-daily": {
        "task": "stocker.tasks.ingest_market_data",
        "schedule": crontab(hour=17, minute=15),  # 5:15 PM ET
    },
}
```

**What it does**:
- Triggers `ingest_market_data` task at 5:15 PM ET
- NO workers consuming from streams
- Task publishes to Redis Stream and exits

#### Redis Streams: Event Bus

**Purpose**: Append-only event log for the data pipeline

**Features**:
- **Consumer groups**: Multiple consumers can process in parallel
- **ACK mechanism**: Ensures messages are processed exactly once
- **Replay capability**: Critical for debugging trading decisions
- **Audit trail**: Complete history of who processed what, when

**Streams**:
1. `market-bars` → `signals` → `targets` → `orders` → `fills` → `portfolio-state` → `alerts`

#### Python Asyncio Consumers: Event Processing

**Purpose**: Process events from Redis Streams using native async/await

**Why asyncio consumers instead of Celery workers?**
- ✅ **No conceptual mismatch**: Celery workers consume from Celery queues, NOT Redis Streams
- ✅ **Fine-grained control**: Full control over message processing, retry logic, dead letter queue
- ✅ **No framework overhead**: Pure Python async functions
- ✅ **Easy to test**: Just async functions with test Redis
- ✅ **Consumer groups**: Built-in Redis Streams feature for failover

**Pattern**:
```python
# Each consumer:
# 1. Read from Redis Stream using xreadgroup
# 2. Process event (call pure strategy logic)
# 3. Store result in PostgreSQL
# 4. Publish to next stream using xadd
# 5. Acknowledge message using xack
```

**Example Consumer Flow**:
```
SignalConsumer (asyncio process):
  ├─ Reads from "market-bars" stream (consumer group: "signal-processors")
  ├─ Fetches 252 bars from Postgres
  ├─ Calls SignalStrategy.compute_signal() (pure logic, no I/O)
  ├─ Stores signal in Postgres
  ├─ Publishes to "signals" stream
  └─ ACKs message
```

**Deployment**:
- **Local**: 6 separate processes via docker-compose
- **AWS ECS**: 6 separate Fargate tasks (0.5 vCPU each)
- **Process management**: Supervisor or systemd for graceful shutdown

**Key Files**:
- `stocker/stream_consumers/base.py` - Base consumer class with retry, ACK, DLQ
- `stocker/stream_consumers/signal_consumer.py` - Signal engine consumer
- `stocker/stream_consumers/portfolio_consumer.py` - Portfolio/risk consumer
- `stocker/stream_consumers/order_consumer.py` - Order manager consumer
- `stocker/stream_consumers/broker_consumer.py` - Broker adapter consumer
- `stocker/stream_consumers/ledger_consumer.py` - Ledger consumer
- `stocker/stream_consumers/monitor_consumer.py` - Monitoring consumer

---

## 4. Backtesting Architecture

### 4.1 Design Principle: Pure Business Logic

**Critical Requirement**: All core trading logic must be **pure, stateless functions** that can be tested in isolation without dependencies on Celery, Redis, or live databases.

**Separation of Concerns:**
```
┌─────────────────────────────────────────────────────────┐
│           PRODUCTION (Event-Driven)                     │
│                                                         │
│  Celery Workers → Infrastructure Layer                  │
│         │              (Redis, Postgres)                │
│         ▼                                               │
│  ┌──────────────────────────────────┐                  │
│  │   Core Strategy Classes          │  ← Pure Python   │
│  │  (SignalStrategy,                │     (No I/O)     │
│  │   PortfolioOptimizer,            │                  │
│  │   RiskManager)                   │                  │
│  └──────────────────────────────────┘                  │
│         ▲                                               │
│         │                                               │
│  Backtesting Engine ← Historical Data (Pandas)          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Core Strategy Classes

These classes are **pure business logic** - no database, no Redis, no Celery dependencies.

#### 4.2.1 SignalStrategy

**Purpose**: Compute trading signals from price data
**Location**: `backend/stocker/strategy/signal_strategy.py`

```python
from dataclasses import dataclass
from decimal import Decimal
import numpy as np
import pandas as pd

@dataclass
class SignalConfig:
    """Configuration for signal generation."""
    lookback_days: int = 126
    ewma_lambda: float = 0.94

@dataclass
class Signal:
    """Pure signal output (no database model)."""
    symbol: str
    date: str
    lookback_return: float
    ewma_vol: float
    direction: int  # +1 or -1
    inv_vol_weight: float

class SignalStrategy:
    """
    Pure signal computation logic.

    Can be called from:
    - Asyncio consumer (production)
    - Backtesting engine (historical)
    - Unit tests (isolated)
    """

    def __init__(self, config: SignalConfig):
        self.config = config

    def compute_signal(
        self,
        symbol: str,
        prices: pd.DataFrame
    ) -> Signal:
        """
        Compute signal from price data.

        Args:
            symbol: Instrument symbol
            prices: DataFrame with columns [date, adj_close]
                   Sorted ascending by date, last 252 rows

        Returns:
            Signal object with computed values
        """
        if len(prices) < self.config.lookback_days + 1:
            raise ValueError(
                f"Need {self.config.lookback_days + 1} prices, "
                f"got {len(prices)}"
            )

        # Compute log returns
        log_returns = np.diff(np.log(prices['adj_close'].values))

        # EWMA volatility
        ewma_vol = self._compute_ewma_volatility(
            log_returns,
            self.config.ewma_lambda
        )

        # Momentum (lookback return)
        current_price = float(prices.iloc[-1]['adj_close'])
        past_price = float(prices.iloc[-(self.config.lookback_days + 1)]['adj_close'])
        lookback_return = (current_price / past_price) - 1.0

        # Direction
        direction = 1 if lookback_return > 0 else -1

        # Inverse-vol weight (preliminary)
        inv_vol_weight = 1.0 / ewma_vol if ewma_vol > 0 else 0.0

        return Signal(
            symbol=symbol,
            date=str(prices.iloc[-1]['date']),
            lookback_return=lookback_return,
            ewma_vol=ewma_vol,
            direction=direction,
            inv_vol_weight=inv_vol_weight
        )

    def _compute_ewma_volatility(
        self,
        returns: np.ndarray,
        lambda_: float
    ) -> float:
        """Compute EWMA volatility (RiskMetrics style)."""
        weights = np.array([
            (1 - lambda_) * (lambda_ ** i)
            for i in range(len(returns))
        ])[::-1]
        weights /= weights.sum()

        variance = np.sum(weights * returns**2)
        daily_vol = np.sqrt(variance)
        annual_vol = daily_vol * np.sqrt(252)

        return float(annual_vol)
```

#### 4.2.2 PortfolioOptimizer

**Purpose**: Compute target exposures from signals
**Location**: `backend/stocker/strategy/portfolio_optimizer.py`

```python
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class RiskConfig:
    """Risk management configuration."""
    target_vol: float = 0.10
    single_cap: float = 0.35
    gross_cap: float = 1.50
    dd_threshold: float = 0.10
    dd_scale: float = 0.50

@dataclass
class TargetExposure:
    """Pure target exposure (no database model)."""
    symbol: str
    raw_exposure: float
    target_exposure: float
    scaling_factor: float
    reason: str

class PortfolioOptimizer:
    """
    Pure portfolio optimization logic.

    Computes target exposures from signals.
    No dependencies on infrastructure.
    """

    def __init__(self, config: RiskConfig):
        self.config = config

    def compute_targets(
        self,
        signals: List[Signal],
        current_drawdown: float = 0.0
    ) -> List[TargetExposure]:
        """
        Compute target exposures from signals.

        Args:
            signals: List of signals for all symbols
            current_drawdown: Portfolio drawdown (0.0 to 1.0)

        Returns:
            List of target exposures
        """
        if not signals:
            return []

        # Step 1: Inverse-volatility weights
        weights = self._compute_inverse_vol_weights(signals)

        # Step 2: Apply direction
        exposures = {
            s.symbol: weights[s.symbol] * s.direction
            for s in signals
        }
        raw_exposures = exposures.copy()

        # Step 3: Apply single instrument cap
        exposures = self._apply_single_cap(exposures)

        # Step 4: Apply gross exposure cap
        exposures = self._apply_gross_cap(exposures)

        # Step 5: Apply drawdown scaling
        k = 1.0
        reason = "Normal operations"

        if current_drawdown > self.config.dd_threshold:
            k = self.config.dd_scale
            exposures = {
                sym: exp * k
                for sym, exp in exposures.items()
            }
            reason = f"Drawdown {current_drawdown:.2%} > {self.config.dd_threshold:.2%}, scaled by {k}"

        # Convert to target objects
        targets = [
            TargetExposure(
                symbol=symbol,
                raw_exposure=raw_exposures[symbol],
                target_exposure=exposures[symbol],
                scaling_factor=k,
                reason=reason
            )
            for symbol in exposures.keys()
        ]

        return targets

    def _compute_inverse_vol_weights(
        self,
        signals: List[Signal]
    ) -> Dict[str, float]:
        """Compute equal risk contribution weights."""
        inv_vols = {s.symbol: s.inv_vol_weight for s in signals}
        total_inv_vol = sum(inv_vols.values())

        if total_inv_vol == 0:
            return {s.symbol: 0.0 for s in signals}

        return {
            symbol: inv_vol / total_inv_vol
            for symbol, inv_vol in inv_vols.items()
        }

    def _apply_single_cap(
        self,
        exposures: Dict[str, float]
    ) -> Dict[str, float]:
        """Cap individual instrument exposure."""
        return {
            symbol: max(-self.config.single_cap, min(self.config.single_cap, exp))
            for symbol, exp in exposures.items()
        }

    def _apply_gross_cap(
        self,
        exposures: Dict[str, float]
    ) -> Dict[str, float]:
        """Scale down if gross exposure exceeds limit."""
        gross = sum(abs(exp) for exp in exposures.values())

        if gross > self.config.gross_cap:
            scale = self.config.gross_cap / gross
            return {
                symbol: exp * scale
                for symbol, exp in exposures.items()
            }

        return exposures
```

### 4.3 Backtesting Engine

**Purpose**: Run historical simulations using pure strategy classes
**Location**: `backend/stocker/backtesting/backtest_engine.py`

```python
from dataclasses import dataclass
from datetime import date
import pandas as pd
from typing import List, Dict
from stocker.strategy.signal_strategy import SignalStrategy, SignalConfig
from stocker.strategy.portfolio_optimizer import PortfolioOptimizer, RiskConfig

@dataclass
class BacktestConfig:
    """Backtesting configuration."""
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    commission_per_trade: float = 1.0
    slippage_bps: float = 5.0
    signal_config: SignalConfig = SignalConfig()
    risk_config: RiskConfig = RiskConfig()

@dataclass
class BacktestResult:
    """Backtesting results."""
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float]

class BacktestEngine:
    """
    Historical backtesting engine.

    Uses pure strategy classes (SignalStrategy, PortfolioOptimizer)
    with historical data.
    """

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.signal_strategy = SignalStrategy(config.signal_config)
        self.portfolio_optimizer = PortfolioOptimizer(config.risk_config)

    def run(
        self,
        historical_prices: Dict[str, pd.DataFrame]
    ) -> BacktestResult:
        """
        Run backtest on historical data.

        Args:
            historical_prices: Dict mapping symbol to DataFrame
                              with columns [date, open, close, adj_close, volume]

        Returns:
            BacktestResult with equity curve, trades, metrics
        """
        # Initialize portfolio state
        cash = self.config.initial_capital
        positions: Dict[str, int] = {}
        equity_curve = []
        trades = []

        # Get trading dates
        all_dates = sorted(set(
            date
            for df in historical_prices.values()
            for date in df['date'].values
        ))

        # Filter to backtest period
        backtest_dates = [
            d for d in all_dates
            if self.config.start_date <= d <= self.config.end_date
        ]

        peak_nav = self.config.initial_capital

        for current_date in backtest_dates:
            # Step 1: Compute signals for all symbols
            signals = []
            for symbol, price_df in historical_prices.items():
                # Get prices up to current date
                historical_window = price_df[
                    price_df['date'] <= current_date
                ].tail(252)

                if len(historical_window) < self.config.signal_config.lookback_days + 1:
                    continue

                try:
                    signal = self.signal_strategy.compute_signal(
                        symbol,
                        historical_window
                    )
                    signals.append(signal)
                except Exception as e:
                    # Skip symbol if computation fails
                    continue

            # Step 2: Get current prices for mark-to-market
            current_prices = {
                symbol: float(df[df['date'] == current_date]['adj_close'].iloc[0])
                for symbol, df in historical_prices.items()
                if current_date in df['date'].values
            }

            # Step 3: Mark positions to market
            positions_value = sum(
                qty * current_prices.get(symbol, 0)
                for symbol, qty in positions.items()
            )
            nav = cash + positions_value

            # Step 4: Compute drawdown
            if nav > peak_nav:
                peak_nav = nav
            drawdown = (peak_nav - nav) / peak_nav if peak_nav > 0 else 0.0

            # Step 5: Compute target exposures
            targets = self.portfolio_optimizer.compute_targets(
                signals,
                current_drawdown=drawdown
            )

            # Step 6: Generate orders (simplified - assume next day open execution)
            for target in targets:
                if target.symbol not in current_prices:
                    continue

                current_price = current_prices[target.symbol]
                desired_qty = int((target.target_exposure * nav) / current_price)
                current_qty = positions.get(target.symbol, 0)
                delta_qty = desired_qty - current_qty

                if abs(delta_qty) > 0 and abs(delta_qty * current_price) >= 50:
                    # Execute trade (simplified: assume fill at current price + slippage)
                    slippage_factor = 1 + (self.config.slippage_bps / 10000)
                    if delta_qty > 0:  # Buy
                        fill_price = current_price * slippage_factor
                    else:  # Sell
                        fill_price = current_price / slippage_factor

                    # Update cash
                    cash -= delta_qty * fill_price
                    cash -= self.config.commission_per_trade

                    # Update position
                    positions[target.symbol] = positions.get(target.symbol, 0) + delta_qty

                    # Record trade
                    trades.append({
                        'date': current_date,
                        'symbol': target.symbol,
                        'side': 'BUY' if delta_qty > 0 else 'SELL',
                        'qty': abs(delta_qty),
                        'price': fill_price,
                        'commission': self.config.commission_per_trade
                    })

            # Record equity curve
            equity_curve.append({
                'date': current_date,
                'nav': nav,
                'cash': cash,
                'positions_value': positions_value,
                'drawdown': drawdown
            })

        # Compute metrics
        equity_df = pd.DataFrame(equity_curve)
        trades_df = pd.DataFrame(trades)

        returns = equity_df['nav'].pct_change().dropna()

        metrics = {
            'total_return': (equity_df['nav'].iloc[-1] / self.config.initial_capital) - 1,
            'cagr': self._compute_cagr(equity_df),
            'volatility': returns.std() * np.sqrt(252),
            'sharpe_ratio': (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0,
            'max_drawdown': equity_df['drawdown'].max(),
            'num_trades': len(trades_df)
        }

        return BacktestResult(
            equity_curve=equity_df,
            trades=trades_df,
            metrics=metrics
        )

    def _compute_cagr(self, equity_df: pd.DataFrame) -> float:
        """Compute compound annual growth rate."""
        total_return = equity_df['nav'].iloc[-1] / equity_df['nav'].iloc[0]
        num_years = len(equity_df) / 252
        cagr = (total_return ** (1 / num_years)) - 1
        return cagr
```

### 4.4 Integration with Production System

**Asyncio Consumer Wrapper** (Production):
```python
# stocker/stream_consumers/signal_consumer.py
from stocker.stream_consumers.base import BaseStreamConsumer
from stocker.strategy.signal_strategy import SignalStrategy, SignalConfig
from stocker.models import DailyBar, Signal as SignalModel
from stocker.core.database import AsyncSessionLocal
import pandas as pd

class SignalConsumer(BaseStreamConsumer):
    """
    Production wrapper around pure SignalStrategy.

    Handles infrastructure (database, Redis) while delegating
    calculation to pure business logic.
    """

    def __init__(self, redis_url: str, db_url: str):
        super().__init__(
            redis_url=redis_url,
            stream_name="market-bars",
            consumer_group="signal-processors"
        )
        self.strategy = SignalStrategy(
            SignalConfig(lookback_days=126, ewma_lambda=0.94)
        )

    async def process_message(self, message_id: str, data: dict):
        """Process a market-bars event."""
        symbol = data['symbol']
        date = data['date']

        # 1. Fetch data from database
        async with AsyncSessionLocal() as session:
            stmt = select(DailyBar).where(
                DailyBar.symbol == symbol,
                DailyBar.date <= date
            ).order_by(DailyBar.date.desc()).limit(252)

            result = await session.execute(stmt)
            bars = result.scalars().all()

            # 2. Convert to pandas DataFrame (pure data structure)
            prices_df = pd.DataFrame([
                {'date': bar.date, 'adj_close': float(bar.adj_close)}
                for bar in reversed(bars)
            ])

            # 3. Call pure strategy logic (NO I/O)
            signal = self.strategy.compute_signal(symbol, prices_df)

            # 4. Persist to database
            signal_model = SignalModel(
                symbol=signal.symbol,
                date=signal.date,
                lookback_return=signal.lookback_return,
                ewma_vol=signal.ewma_vol,
                direction=signal.direction,
                inv_vol_weight=signal.inv_vol_weight
            )
            session.add(signal_model)
            await session.commit()

        # 5. Publish to Redis Stream
        await self.redis.xadd("signals", {
            "symbol": signal.symbol,
            "date": signal.date,
            "direction": str(signal.direction)
        })
```

### 4.5 Backtesting Workflow

```bash
# Run backtest from command line
python -m stocker.backtesting.cli \
  --start-date 2015-01-01 \
  --end-date 2024-12-31 \
  --initial-capital 100000 \
  --output backtest_results.html

# Output:
# =============== Backtest Results ===============
# Period: 2015-01-01 to 2024-12-31
#
# Total Return:        +87.3%
# CAGR:                +6.5%
# Volatility:          12.4%
# Sharpe Ratio:        0.52
# Max Drawdown:        -18.2%
# Number of Trades:    1,247
# ================================================
```

### 4.6 Testing Strategy

**Unit Tests** (Pure Logic):
```python
# tests/unit/test_signal_strategy.py
def test_signal_strategy_momentum():
    """Test momentum calculation in isolation."""
    config = SignalConfig(lookback_days=10, ewma_lambda=0.94)
    strategy = SignalStrategy(config)

    # Create test data
    prices = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=20),
        'adj_close': [100 + i for i in range(20)]  # Uptrend
    })

    signal = strategy.compute_signal('TEST', prices)

    assert signal.direction == 1  # Long signal
    assert signal.lookback_return > 0  # Positive momentum
    assert signal.ewma_vol > 0  # Valid volatility
```

**Integration Tests** (With Database):
```python
# tests/integration/test_signal_consumer.py
import pytest
from stocker.stream_consumers.signal_consumer import SignalConsumer

@pytest.mark.asyncio
async def test_signal_consumer_end_to_end(test_db, test_redis):
    """Test asyncio consumer with test infrastructure."""
    # Seed test database with prices
    # ...

    # Create consumer
    consumer = SignalConsumer(
        redis_url="redis://localhost:6379/15",  # Test DB
        db_url="postgresql://test"
    )

    # Publish test event
    await test_redis.xadd("market-bars", {
        "symbol": "SPY",
        "date": "2024-12-27",
    })

    # Process one message
    await consumer.process_next_message()

    # Assert signal was stored
    async with test_db() as session:
        stmt = select(Signal).where(
            Signal.symbol == 'SPY',
            Signal.date == '2024-12-27'
        )
        result = await session.execute(stmt)
        signal = result.scalar_one_or_none()

        assert signal is not None
        assert signal.direction in [1, -1]
```

### 4.7 Benefits of This Architecture

✅ **Backtesting Accuracy**: Same code runs in backtest and production (no code/behavior mismatch)
✅ **Fast Unit Tests**: Pure functions test instantly without database/Redis
✅ **Easy Debugging**: Core logic can be stepped through in isolation
✅ **Strategy Iteration**: Tweak parameters and re-run backtest in seconds
✅ **Confidence**: If backtest passes, production will behave identically

---

## 5. Data Models

### 5.1 Core Database Tables

**prices_daily** - Market data
```python
id | symbol | date | open | high | low | close | adj_close | volume | source | source_hash | created_at
```

**signals** - Computed trading signals
```python
id | symbol | date | lookback_return | ewma_vol | direction | inv_vol_weight | created_at
```

**target_exposures** - Portfolio target positions
```python
id | portfolio_id | date | symbol | raw_exposure | target_exposure | scaling_factor | reason | created_at
```

**orders** - Order instructions
```python
id | order_id | portfolio_id | date | symbol | side | qty | type | status | broker_order_id | created_at | updated_at
```
*Unique constraint on (portfolio_id, symbol, date) for idempotency*

**fills** - Execution confirmations
```python
id | order_id | symbol | qty | price | commission | filled_at | created_at
```

**holdings** - Current positions
```python
id | portfolio_id | symbol | qty | avg_price | updated_at
```

**portfolio_state** - Daily portfolio snapshot
```python
id | portfolio_id | date | cash | positions_value | nav | gross_exposure | net_exposure | realised_pnl | unrealised_pnl | peak_nav | drawdown | created_at
```

### 5.2 Redis Streams

| Stream Name | Purpose | Key Fields |
|-------------|---------|------------|
| `market-bars` | Daily OHLCV data | symbol, date, close, volume |
| `signals` | Trading signals | symbol, date, direction, ewma_vol |
| `targets` | Target exposures | portfolio_id, symbol, exposure |
| `orders` | Order instructions | order_id, symbol, side, qty |
| `fills` | Execution confirms | order_id, symbol, qty, price |
| `portfolio-state` | Portfolio updates | portfolio_id, nav, drawdown |
| `alerts` | System alerts | type, severity, message |

---

## 6. Angular Frontend

### 6.1 Architecture

**State Management**: NgRx (Redux pattern)
**Real-Time Updates**: Server-Sent Events (SSE)
**UI Components**: Angular Material

### 6.2 Key Features

**Dashboard:**
- Real-time NAV display
- Portfolio holdings table
- Performance chart (NAV over time)
- Drawdown gauge
- Recent orders

**Signals View:**
- Table of all signals for current date
- Momentum vs volatility chart
- Historical signal accuracy

**Admin Panel:**
- Edit strategy configuration
- Manage trading universe
- Kill switch button
- Manual trade override

### 6.3 Real-Time Data Flow

```typescript
// SSE connection to backend
eventSource = new EventSource('/stream/portfolio/default');

eventSource.addEventListener('portfolio_state', (event) => {
  const state = JSON.parse(event.data);
  store.dispatch(portfolioStateUpdated({ state }));
});
```

---

## 7. AWS Infrastructure

### 7.1 AWS Services

| Service | Purpose | Configuration |
|---------|---------|---------------|
| **ECS Fargate** | Container orchestration | 2 API tasks (HA), 1 Celery Beat, 6 asyncio consumers |
| **RDS PostgreSQL** | Primary database | Multi-AZ (prod), db.t4g.small |
| **ElastiCache Redis** | Event streams + scheduler | cache.t4g.small |
| **ECR** | Docker registry | Private registry |
| **ALB** | Load balancer | Routes to FastAPI services |
| **S3** | Backups, logs | Lifecycle: 90 days |
| **CloudWatch** | Logging + metrics | Custom metrics: NAV, drawdown |
| **Secrets Manager** | API keys, passwords | Rotation enabled |
| **VPC** | Network isolation | Public/private subnets |

### 7.2 Cost Estimate (Monthly)

| Service | Configuration | Cost |
|---------|--------------|------|
| ECS Fargate | 2 API tasks (0.5 vCPU, 1GB) 24/7 | $30 |
| ECS Fargate | 1 Celery Beat (0.25 vCPU, 0.5GB) 24/7 | $10 |
| ECS Fargate | 6 asyncio consumers (0.5 vCPU, 1GB) 24/7 | $90 |
| RDS PostgreSQL | db.t4g.small, Multi-AZ | $60 |
| ElastiCache Redis | cache.t4g.small | $25 |
| ALB | 1 load balancer | $20 |
| S3 + CloudWatch | Storage + logs | $15 |
| **Total** | | **~$250/month** |

**Cost Optimization:**
- Fargate Spot: 70% discount → ~$100/month
- Aurora Serverless v2: Auto-scales → ~$120/month

---

## 8. Deployment Pipeline

### 8.1 GitHub Actions CI/CD

**Workflow:**
1. **Test** - Run pytest + mypy on PR
2. **Build** - Build Docker image, push to ECR
3. **Deploy Staging** - Auto-deploy `develop` branch
4. **Deploy Production** - Manual approval for `main` branch

**Key Features:**
- Ephemeral test databases (Docker Postgres)
- Blue/green deployments (zero downtime)
- Automatic rollback on health check failure
- Code coverage reporting

### 8.2 Deployment Strategy

**Blue/Green:**
- ECS maintains 2 task versions
- ALB routes to new tasks
- Health checks pass → cutover
- Old tasks terminated

**Rollback:**
```bash
aws ecs update-service \
  --cluster stocker-cluster \
  --service stocker-api \
  --task-definition stocker-api:42  # Previous revision
```

### 8.3 ECS Task Definitions

**Process Model** (9 ECS tasks total):

```yaml
# Task 1: FastAPI (x2 for HA)
stocker-api:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: uvicorn stocker.api.main:app --host 0.0.0.0 --port 8000
  desired_count: 2
  health_check: /health

# Task 2: Celery Beat (scheduler)
stocker-celery-beat:
  image: stocker:latest
  cpu: 256
  memory: 512
  command: celery -A stocker.scheduler.celery_app beat --loglevel=info
  desired_count: 1

# Tasks 3-8: Asyncio Stream Consumers (x6)
stocker-signal-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.signal_consumer
  desired_count: 1

stocker-portfolio-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.portfolio_consumer
  desired_count: 1

stocker-order-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.order_consumer
  desired_count: 1

stocker-broker-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.broker_consumer
  desired_count: 1

stocker-ledger-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.ledger_consumer
  desired_count: 1

stocker-monitor-consumer:
  image: stocker:latest
  cpu: 512
  memory: 1024
  command: python -m stocker.stream_consumers.monitor_consumer
  desired_count: 1
```

### 8.4 Docker Compose (Local Development)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: stocker
      POSTGRES_USER: stocker
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  api:
    build: ./backend
    command: uvicorn stocker.api.main:app --reload --host 0.0.0.0
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  celery-beat:
    build: ./backend
    command: celery -A stocker.scheduler.celery_app beat --loglevel=info
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  signal-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.signal_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  portfolio-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.portfolio_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  order-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.order_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  broker-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.broker_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  ledger-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.ledger_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

  monitor-consumer:
    build: ./backend
    command: python -m stocker.stream_consumers.monitor_consumer
    environment:
      DATABASE_URL: postgresql+asyncpg://stocker:dev@postgres:5432/stocker
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - postgres
      - redis
    volumes:
      - ./backend:/app

volumes:
  postgres_data:
  redis_data:
```

**Usage:**
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f signal-consumer

# Stop all services
docker-compose down

# Reset databases
docker-compose down -v
```

---

## 9. Project Structure

```
stocker/
  backend/
    stocker/
      api/                  # FastAPI routers
      scheduler/            # Celery Beat configuration
      tasks/                # Celery scheduled tasks (market data ingest)
      stream_consumers/     # Asyncio Redis Stream consumers (6 services)
        base.py             # BaseStreamConsumer (retry, ACK, DLQ)
        signal_consumer.py  # Signal engine consumer
        portfolio_consumer.py  # Portfolio/risk consumer
        order_consumer.py   # Order manager consumer
        broker_consumer.py  # Broker adapter consumer
        ledger_consumer.py  # Ledger consumer
        monitor_consumer.py # Monitoring consumer
      models/               # SQLAlchemy models
      schemas/              # Pydantic schemas
      services/             # Business logic
      strategy/             # Pure strategy classes (NEW)
        signal_strategy.py  # SignalStrategy (pure logic)
        portfolio_optimizer.py  # PortfolioOptimizer (pure logic)
      backtesting/          # Backtesting engine (NEW)
        backtest_engine.py  # BacktestEngine
        cli.py              # Command-line interface
      core/                 # Config, DB, Redis
      utils/                # Math, calendar, accounting
    tests/
      unit/
        test_signal_strategy.py  # Pure logic tests (NEW)
        test_portfolio_optimizer.py  # Pure logic tests (NEW)
      integration/
        test_signal_consumer.py  # Consumer integration tests
        test_portfolio_consumer.py  # Consumer integration tests
      backtests/            # Backtest results (NEW)
    alembic/                # Database migrations
    pyproject.toml          # Poetry dependencies
    Dockerfile

  frontend/
    stocker-ui/             # Angular app
      src/app/
        features/
          dashboard/
          signals/
          admin/
        core/
          services/
          guards/

  docker-compose.yml        # Local development
  .github/workflows/        # CI/CD pipelines
  architecture.md           # This file
  README.md
```

---

## 10. Risks & Decisions

### 10.1 Key Architectural Decisions

| Decision | Chosen | Rejected | Rationale |
|----------|--------|----------|-----------|
| Event Streaming | Redis Streams | Kafka | Lighter weight, Python-native, sufficient for daily trading |
| Event Processing | Asyncio consumers | Celery workers | Celery workers consume from Celery queues, NOT Redis Streams |
| Scheduling | Celery Beat | Cron | Distributed, timezone-aware, integrates with existing stack |
| Database Migrations | Alembic | Flyway | Flyway is Java; Alembic is Python-native with SQLAlchemy |
| Local DB | Docker Postgres | AWS RDS | Cost, speed, offline development |
| Real-Time UI | SSE | WebSockets | Simpler, auto-reconnect, sufficient for daily updates |
| Container Orchestration | ECS Fargate | EKS | Simpler ops, no Kubernetes complexity |
| State Management | NgRx | Plain services | Complex app benefits from Redux pattern |

### 10.2 Technical Risks

1. **Redis Streams Complexity**
   - Risk: More complex than simple queue
   - Mitigation: Start simple, add consumer groups if needed
   - Alternative: RabbitMQ

2. **AWS Costs**
   - Risk: $250/month ongoing (9 ECS tasks: 2 API, 1 Celery Beat, 6 consumers)
   - Mitigation: Fargate Spot (70% discount → ~$100/month), Aurora Serverless v2
   - Alternative: Fly.io, Railway (cheaper PaaS)

3. **Real-Time Performance**
   - Risk: SSE may not scale to many users
   - Mitigation: Start with SSE, upgrade to WebSockets if needed
   - Alternative: Polling fallback

### 10.3 Open Questions

1. **Market Data Provider**: Polygon ($199/month) vs yfinance (free)?
2. **Broker**: Alpaca vs Interactive Brokers for live trading?
3. **Monitoring**: Self-hosted (Prometheus/Grafana) vs DataDog?

---

## Summary

This architecture provides a **production-grade systematic trading platform** with:

✅ **Robust Event-Driven Design**: 7 microservices communicating via Redis Streams
✅ **Type-Safe Python**: FastAPI + SQLAlchemy + Pydantic
✅ **Modern Frontend**: Angular + NgRx with real-time updates
✅ **AWS-Ready**: ECS Fargate deployment with ~$250/month cost (~$100 with Spot)
✅ **Clean Architecture**: Celery Beat for scheduling, asyncio consumers for event processing

**Key Strengths:**
- Lightweight alternative to Kafka (Redis Streams with consumer groups)
- Python-native tooling (Alembic, asyncio, Celery Beat)
- Clear separation: scheduling (Celery Beat) vs event processing (asyncio)
- Cost-effective local development (Docker Compose)
- Comprehensive monitoring and kill switch
- Pure business logic classes (same code for backtest and production)
- Scalable to intraday trading (add more asyncio consumers)

**Next Steps:**
1. Review and approve architecture
2. Follow [implementation-plan.md](./implementation-plan.md) for detailed tasks
3. See [tooling.md](./tooling.md) for market data and broker recommendations
