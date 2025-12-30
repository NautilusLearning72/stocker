#!/bin/bash
# Refresh the dynamic trading universe

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."  # Go to backend/ directory

# Check if .env exists (in backend/ or project root)
if [ -f ".env" ]; then
    ENV_FILE=".env"
elif [ -f "../.env" ]; then
    ENV_FILE="../.env"
    cp "../.env" ".env"
else
    echo "Error: .env file not found in backend/ or project root."
    exit 1
fi

echo "Using env file: $ENV_FILE"

poetry run python - <<'PY'
from datetime import date
import asyncio

from stocker.services.instrument_metrics_service import InstrumentMetricsService
from stocker.services.universe_service import UniverseService

async def main() -> None:
    universe_service = UniverseService()
    symbols = await universe_service.get_all_symbols()
    print(f"Using {len(symbols)} symbols from user-defined universes")
    metrics_service = InstrumentMetricsService()
    metrics_count = await metrics_service.fetch_and_store_metrics(
        symbols,
        as_of_date=date.today(),
    )
    print(f"Ingested instrument metrics for {metrics_count} symbols")

asyncio.run(main())
PY
