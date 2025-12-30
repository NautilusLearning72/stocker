#!/bin/bash
# Stocker Pipeline Launcher
# Starts all stream consumers and triggers market data ingestion

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."  # Go to backend/ directory

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Stocker Pipeline Launcher${NC}"
echo "================================"

# Check if .env exists (in backend/ or project root)
if [ -f ".env" ]; then
    ENV_FILE=".env"
elif [ -f "../.env" ]; then
    ENV_FILE="../.env"
    # Copy to backend/ for easier Python discovery
    cp "../.env" ".env"
else
    echo -e "${RED}❌ Error: .env file not found in backend/ or project root.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Using env file: $ENV_FILE${NC}"

# Extract just ALPACA keys for validation (without sourcing full file which mangles JSON)
ALPACA_API_KEY=$(grep "^ALPACA_API_KEY=" "$ENV_FILE" | cut -d'=' -f2)
ALPACA_SECRET_KEY=$(grep "^ALPACA_SECRET_KEY=" "$ENV_FILE" | cut -d'=' -f2)

if [ -z "$ALPACA_API_KEY" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    echo -e "${YELLOW}⚠️  Warning: Alpaca credentials not set. Broker consumer will use mock mode.${NC}"
fi

# Start infrastructure if not running
echo -e "\n${YELLOW}📦 Starting infrastructure...${NC}"
docker compose up postgres redis -d 2>/dev/null || echo "Infrastructure might already be running"

# Wait for services
echo "Waiting for PostgreSQL..."
sleep 3

# Run migrations
echo -e "\n${YELLOW}🔄 Running database migrations...${NC}"
poetry run alembic upgrade head

# Fetch instrument metrics for configured universes
echo -e "\n${YELLOW}🌐 Ingesting instrument metrics for configured universes...${NC}"
./scripts/refresh_universe.sh

# Create log directory
mkdir -p logs

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down consumers...${NC}"
    pkill -f "stocker.stream_consumers" 2>/dev/null || true
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}
trap cleanup EXIT

# Start consumers in background
echo -e "\n${YELLOW}🔌 Starting stream consumers...${NC}"

poetry run python -m stocker.stream_consumers.signal_consumer > logs/signal_consumer.log 2>&1 &
echo "  ✓ Signal Consumer (PID: $!)"

poetry run python -m stocker.stream_consumers.portfolio_consumer > logs/portfolio_consumer.log 2>&1 &
echo "  ✓ Portfolio Consumer (PID: $!)"

poetry run python -m stocker.stream_consumers.order_consumer > logs/order_consumer.log 2>&1 &
echo "  ✓ Order Consumer (PID: $!)"

poetry run python -m stocker.stream_consumers.broker_consumer > logs/broker_consumer.log 2>&1 &
echo "  ✓ Broker Consumer (PID: $!)"

poetry run python -m stocker.stream_consumers.ledger_consumer > logs/ledger_consumer.log 2>&1 &
echo "  ✓ Ledger Consumer (PID: $!)"

# Wait for consumers to initialize
sleep 2

# Trigger market data ingestion
echo -e "\n${YELLOW}📊 Triggering market data ingestion...${NC}"
poetry run python -c "
from stocker.services.market_data_service import MarketDataService
from stocker.services.universe_service import UniverseService
from stocker.core.config import settings
from datetime import date, timedelta
import asyncio

async def ingest():
    service = MarketDataService()
    universe_service = UniverseService()
    symbols = await universe_service.get_symbols_for_strategy(settings.DEFAULT_STRATEGY_ID)
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    result = await service.fetch_and_store_daily_bars(symbols, start_date, end_date)
    print(f'Ingested {result} bars')

asyncio.run(ingest())
"

echo -e "\n${GREEN}✅ Pipeline is running!${NC}"
echo "================================"
echo "Logs are in: logs/"
echo "API available at: http://localhost:8000"
echo "Press Ctrl+C to stop all consumers"
echo ""

# Keep script running and tail logs
tail -f logs/*.log
