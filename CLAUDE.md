# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stocker is a production-grade systematic trading platform implementing a volatility-targeted trend-following strategy. It uses an event-driven microservices architecture with Python 3.12+/FastAPI backend and Redis Streams for event processing.

## Build & Development Commands

All commands run from `backend/` directory using Poetry:

```bash
# Install dependencies
poetry install

# Start infrastructure (Postgres + Redis)
docker-compose up postgres redis -d

# Run database migrations
poetry run alembic upgrade head

# Start FastAPI server
poetry run uvicorn stocker.api.main:app --reload

# Start Celery Beat scheduler
poetry run celery -A stocker.scheduler.celery_app beat --loglevel=info

# Start a stream consumer (each runs as separate process)
poetry run python -m stocker.stream_consumers.signal_consumer

# Run full pipeline (all consumers + infrastructure)
./scripts/run_pipeline.sh
```

## Testing

```bash
# Run all tests with coverage
poetry run pytest

# Run specific test file
poetry run pytest tests/unit/test_signal_strategy.py

# Run integration tests only
poetry run pytest tests/integration/
```

## Code Quality

```bash
# Format code
poetry run ruff format .

# Lint
poetry run ruff check .

# Type check
poetry run mypy stocker/
```

## Database Migrations

```bash
# Create new migration
poetry run alembic revision --autogenerate -m "Description"

# Apply migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1
```

## Architecture

### Event-Driven Pipeline

The system processes daily market data through a pipeline of Redis Stream consumers:

```
Celery Beat (5:15 PM ET) → Market Data Ingest
    ↓ market-bars stream
Signal Consumer → Compute momentum/volatility signals
    ↓ signals stream
Portfolio Consumer → Compute target exposures with risk limits
    ↓ targets stream
Order Consumer → Generate orders from position deltas
    ↓ orders stream
Broker Consumer → Execute (paper/live)
    ↓ fills stream
Ledger Consumer → Update positions/NAV
    ↓ portfolio-state stream
Monitor Consumer → Check anomalies, trigger alerts
```

### Key Architectural Patterns

**Pure Strategy Classes**: Core trading logic (`stocker/strategy/`) is pure Python with no I/O dependencies. Same code runs in backtesting and production:
- `SignalStrategy` - computes momentum signals and EWMA volatility
- `PortfolioOptimizer` - computes inverse-vol weights, applies risk caps (35% single, 150% gross), circuit breaker

**Stream Consumers**: Each consumer (`stocker/stream_consumers/`) wraps pure strategy logic with database/Redis infrastructure:
- Extends `BaseStreamConsumer` which handles consumer groups, retries (3x exponential backoff), DLQ
- Reads from input stream → calls pure strategy → persists to DB → publishes to output stream → ACKs

**Celery Beat**: Used ONLY for scheduling (triggers ingest at 5:15 PM ET). NOT used for event processing - that's handled by asyncio stream consumers.

### Core Modules

- `stocker/core/` - Config, database (async SQLAlchemy), Redis setup
- `stocker/models/` - SQLAlchemy models (DailyBar, Signal, Order, Fill, Holding, PortfolioState)
- `stocker/services/market_data/` - Data providers (Alpaca, yfinance) with common interface
- `stocker/backtesting/` - BacktestEngine using pure strategy classes

### Risk Parameters (defaults in RiskConfig)

- `target_vol`: 10% annualized
- `single_cap`: 35% max per instrument
- `gross_cap`: 150% max gross exposure
- `dd_threshold`: 10% drawdown triggers 50% position reduction
