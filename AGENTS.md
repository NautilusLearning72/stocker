# AGENTS.md

Guidance for coding agents working in this repository.

## Project overview

Stocker is a production-grade systematic trading platform implementing a volatility-targeted trend-following strategy. It uses Python 3.12+, FastAPI, Redis Streams, PostgreSQL, and Celery Beat for scheduling.

## Key directories

- `backend/`: primary Python service (FastAPI, stream consumers, models, strategy)
- `frontend/`: Angular app (coming soon)
- `research/`: strategy research notes
- `architecture.md`, `implementation-plan.md`, `data-model.md`, `tooling.md`: design references

## Common commands

Run backend commands from `backend/` unless noted.

```bash
# Install dependencies
poetry install

# Start infra (from repo root)
docker-compose up postgres redis -d

# Run database migrations
poetry run alembic upgrade head

# Start FastAPI
poetry run uvicorn stocker.api.main:app --reload

# Start Celery Beat (scheduling only)
poetry run celery -A stocker.scheduler.celery_app beat --loglevel=info

# Start a stream consumer
poetry run python -m stocker.stream_consumers.signal_consumer

# Run full pipeline
./scripts/run_pipeline.sh
```

## Testing and quality

```bash
# Tests
poetry run pytest
poetry run pytest tests/integration/

# Format, lint, type check
poetry run ruff format .
poetry run ruff check .
poetry run mypy stocker/
```

## Migrations

```bash
poetry run alembic revision --autogenerate -m "Description"
poetry run alembic upgrade head
poetry run alembic downgrade -1
```

## Architecture guardrails

- Keep pure strategy logic in `backend/stocker/strategy/` with no I/O so it runs in backtests and production.
- Implement event processing in `backend/stocker/stream_consumers/` and extend `BaseStreamConsumer`.
- Use Redis Streams for event flow; Celery Beat is for scheduling only.
- When changing schema or models, update Alembic migrations.

## Configuration

- Copy `backend/.env.example` to `backend/.env` for local config.
- Postgres and Redis are required for end-to-end runs.
