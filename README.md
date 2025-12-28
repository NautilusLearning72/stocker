# Stocker - Systematic Trading Platform

A production-grade systematic trading platform implementing a volatility-targeted trend-following strategy.

## Architecture

This platform uses a modern event-driven microservices architecture:

- **Backend**: Python 3.12+ with FastAPI, SQLAlchemy, asyncio
- **Event Processing**: Redis Streams with asyncio consumers
- **Scheduling**: Celery Beat for time-based triggers
- **Database**: PostgreSQL with Alembic migrations
- **Frontend**: Angular 18+ with NgRx (coming soon)
- **Infrastructure**: AWS ECS Fargate, RDS, ElastiCache

For detailed architecture documentation, see [architecture.md](./architecture.md).

## Project Structure

```
stocker/
├── backend/                 # Python backend
│   ├── stocker/
│   │   ├── api/            # FastAPI routers
│   │   ├── scheduler/      # Celery Beat configuration
│   │   ├── tasks/          # Scheduled tasks
│   │   ├── stream_consumers/  # Asyncio Redis Stream consumers
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── strategy/       # Pure strategy classes
│   │   ├── backtesting/    # Backtesting engine
│   │   ├── core/           # Config, DB, Redis
│   │   └── utils/          # Utilities
│   ├── tests/              # Test suite
│   ├── alembic/            # Database migrations
│   └── pyproject.toml      # Poetry dependencies
├── frontend/               # Angular frontend (coming soon)
├── docker-compose.yml      # Local development
├── .github/workflows/      # CI/CD pipelines
└── architecture.md         # Detailed architecture docs
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development without Docker)
- Poetry 1.8+ (for dependency management)

### Setup with Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd stocker
   ```

2. **Create environment file**
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your configuration
   ```

3. **Start all services**
   ```bash
   docker-compose up -d
   ```

   This starts 9 services:
   - `postgres` - PostgreSQL database
   - `redis` - Redis for streams and task queue
   - `api` - FastAPI server (http://localhost:8000)
   - `celery-beat` - Task scheduler
   - `signal-consumer` - Signal processing
   - `portfolio-consumer` - Portfolio optimization
   - `order-consumer` - Order generation
   - `broker-consumer` - Broker execution
   - `ledger-consumer` - Position accounting
   - `monitor-consumer` - System monitoring

4. **Check service health**
   ```bash
   curl http://localhost:8000/health
   ```

5. **View logs**
   ```bash
   # All services
   docker-compose logs -f

   # Specific service
   docker-compose logs -f signal-consumer
   ```

6. **Stop services**
   ```bash
   docker-compose down

   # Stop and remove volumes (reset databases)
   docker-compose down -v
   ```

### Local Development (Without Docker)

1. **Install Poetry**
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

2. **Install dependencies**
   ```bash
   cd backend
   poetry install
   ```

3. **Start PostgreSQL and Redis**
   ```bash
   docker-compose up postgres redis -d
   ```

4. **Run database migrations**
   ```bash
   poetry run alembic upgrade head
   ```

5. **Start FastAPI server**
   ```bash
   poetry run uvicorn stocker.api.main:app --reload
   ```

6. **Start Celery Beat (in another terminal)**
   ```bash
   poetry run celery -A stocker.scheduler.celery_app beat --loglevel=info
   ```

7. **Start a stream consumer (in another terminal)**
   ```bash
   poetry run python -m stocker.stream_consumers.signal_consumer
   ```

### Run the Full Trading Pipeline

The easiest way to run the complete pipeline is with the launcher script:

```bash
cd backend
./scripts/run_pipeline.sh
```

This script will:
1. ✅ Start PostgreSQL and Redis (via Docker)
2. ✅ Run database migrations
3. ✅ Start all 5 stream consumers in the background
4. ✅ Trigger market data ingestion for default universe
5. ✅ Tail logs from all consumers

**Manual Pipeline Steps** (alternative):

```bash
# Terminal 1: Start consumers individually
poetry run python -m stocker.stream_consumers.signal_consumer
poetry run python -m stocker.stream_consumers.portfolio_consumer
poetry run python -m stocker.stream_consumers.order_consumer
poetry run python -m stocker.stream_consumers.broker_consumer
poetry run python -m stocker.stream_consumers.ledger_consumer

# Terminal 2: Trigger ingestion
poetry run python -c "
from stocker.services.market_data_service import MarketDataService
from stocker.core.database import AsyncSessionLocal
import asyncio

async def ingest():
    async with AsyncSessionLocal() as session:
        service = MarketDataService(session)
        symbols = ['AAPL', 'MSFT', 'SPY']
        await service.ingest_daily_bars(symbols, lookback_days=30)

asyncio.run(ingest())
"
```

## Development Workflow

### Running Tests

```bash
cd backend
poetry run pytest

# With coverage
poetry run pytest --cov=stocker --cov-report=html

# Specific test file
poetry run pytest tests/unit/test_signal_strategy.py

# Integration tests
poetry run pytest tests/integration/
```

### Code Quality

```bash
# Format code
poetry run ruff format .

# Lint code
poetry run ruff check .

# Type checking
poetry run mypy stocker/
```

### Database Migrations

```bash
# Create a new migration
poetry run alembic revision --autogenerate -m "Description of changes"

# Apply migrations
poetry run alembic upgrade head

# Rollback migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history
```

### Backtesting

```bash
# Run backtest
poetry run python -m stocker.backtesting.cli \
  --start-date 2015-01-01 \
  --end-date 2024-12-31 \
  --initial-capital 100000 \
  --output backtest_results.html
```

### End-to-End Verification

To run the integrated pipeline test (mocking market data -> signal -> portfolio -> order -> broker -> ledger):

```bash
# Requires Docker containers (Redis, Postgres) to be running
# In backend/ directory:
poetry run python scripts/verify_e2e.py
```

## API Documentation

Once the API server is running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Configuration

Configuration is managed through environment variables. See `backend/.env.example` for all available options.

Key configuration areas:
- **Database**: Connection URL, pool size
- **Redis**: Connection URL, max connections
- **Trading**: Universe, strategy parameters
- **Market Data**: API keys for data providers
- **Broker**: Paper vs live mode, API credentials
- **Monitoring**: Alert webhooks and emails

## Architecture Highlights

### Worker Pattern

- **Celery Beat**: Scheduling ONLY (triggers market data ingest at 5:15 PM ET)
- **Redis Streams**: Event bus with consumer groups for the data pipeline
- **Asyncio Consumers**: 6 processes handling event processing with retry logic

### Data Flow

```
Market Close (5:15 PM ET)
  ↓
Celery Beat → Market Data Ingest Task → Publish to Redis Stream
  ↓
Signal Consumer → Compute Signals → Publish to signals stream
  ↓
Portfolio Consumer → Compute Targets → Publish to targets stream
  ↓
Order Consumer → Generate Orders → Publish to orders stream
  ↓
Broker Consumer → Execute Orders → Publish to fills stream
  ↓
Ledger Consumer → Update Positions → Publish to portfolio-state stream
  ↓
Monitor Consumer → Check Anomalies → Publish alerts
```

### Pure Business Logic

All core trading logic (SignalStrategy, PortfolioOptimizer) is implemented as pure Python classes with no I/O dependencies. This allows:
- Same code runs in backtesting and production
- Fast unit tests without database/Redis
- Easy debugging and iteration

## Deployment

See [architecture.md](./architecture.md#8-deployment-pipeline) for AWS ECS deployment instructions.

## Implementation Roadmap

For the detailed, component-by-component implementation plan, see **[implementation-plan.md](./implementation-plan.md)**.

**Current Progress**:
- ✅ Phase 1: Foundation (monorepo, Docker, config)
- ✅ Phase 2: Core Strategy Logic
- ✅ Phase 3: Data Infrastructure
- ✅ Phase 4: Stream Consumers
- ✅ Phase 5: Trading Pipeline (Verification & Launch)
- ⬜ Phase 6: API Layer
- ⬜ Phase 7: Frontend
- ⬜ Phase 8: Deployment & CI/CD
- ⬜ Phase 9: Paper Trading
- ⬜ Phase 10: Production Launch

## Contributing

1. Create a feature branch from `develop`
2. Make your changes
3. Run tests and linting
4. Submit a pull request

## License

Proprietary - All rights reserved

## Support

For questions or issues, refer to the planning notes in `.claude/plans/` or contact the development team.
