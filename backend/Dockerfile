# Multi-stage build for production optimization
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.0 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Set work directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Development stage
FROM base as development

# Install all dependencies (including dev)
RUN poetry install --no-root

# Copy application code
COPY . .

# Production stage
FROM base as production

# Install only production dependencies
RUN poetry install --only main --no-root

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 stocker && chown -R stocker:stocker /app
USER stocker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "stocker.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
