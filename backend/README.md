# Stocker Backend

This is the backend service for the Stocker trading platform.

## Setup

1.  Install dependencies: `poetry install`
2.  Run migrations: `poetry run alembic upgrade head`
3.  Start server: `poetry run uvicorn stocker.api.main:app --reload`
