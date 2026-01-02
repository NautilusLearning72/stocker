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

# Fetch market sentiment for global universe
echo -e "\n${YELLOW}🧠 Ingesting market sentiment for global universe...${NC}"
poetry run python -c "
from stocker.tasks.market_sentiment import ingest_market_sentiment
result = ingest_market_sentiment()
print(f'✓ Market sentiment ingestion completed: {result}')
"

# Fetch corporate actions for global universe
echo -e "\n${YELLOW}🏦 Ingesting corporate actions for global universe...${NC}"
poetry run python -c "
from stocker.tasks.corporate_actions import ingest_corporate_actions
result = ingest_corporate_actions()
print(f'✓ Corporate actions ingestion completed: {result}')
"

# Initialize portfolio if not exists
echo -e "\n${YELLOW}💰 Initializing portfolio...${NC}"
poetry run python -c "
from stocker.tasks.portfolio import initialize_portfolio
result = initialize_portfolio()
status = result['status']
if status == 'created':
    print(f'✓ Portfolio initialized: NAV=\${result[\"nav\"]:,.2f}, Cash=\${result[\"cash\"]:,.2f}')
else:
    print(f'✓ Portfolio exists: NAV=\${result[\"nav\"]:,.2f}, Cash=\${result[\"cash\"]:,.2f}')
"

# Sync portfolio state/holdings from broker (if configured)
if [ -n "$ALPACA_API_KEY" ] && [ -n "$ALPACA_SECRET_KEY" ]; then
    echo -e "\n${YELLOW}🔄 Syncing portfolio from broker...${NC}"
    poetry run python -c "
import asyncio
from stocker.services.portfolio_sync_service import PortfolioSyncService

result = asyncio.run(PortfolioSyncService().sync_portfolio('main'))
print(
    '✓ Portfolio sync completed: '
    f\"orders+{result['orders_created']} updated={result['orders_updated']} \"
    f\"fills+{result['fills_created']} holdings={result['holdings_refreshed']} \"
    f\"state={result['portfolio_state_updated']}\"
)
"
else
    echo -e "${YELLOW}⚠️  Skipping broker sync: Alpaca credentials not set.${NC}"
fi

# Sync position states for exit rules
echo -e "\n${YELLOW}🧭 Syncing position states from holdings...${NC}"
poetry run python -c "
from stocker.tasks.position_state import sync_position_states
result = sync_position_states()
print(f'✓ Position state sync completed: {result}')
"

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

poetry run python -m stocker.stream_consumers.monitor_consumer > logs/monitor_consumer.log 2>&1 &
echo "  ✓ Monitor Consumer (PID: $!)"

poetry run python -m stocker.stream_consumers.exit_consumer > logs/exit_consumer.log 2>&1 &
echo "  ✓ Exit Consumer (PID: $!)"

# Wait for consumers to initialize
sleep 2

# Trigger market data ingestion via Celery task
echo -e "\n${YELLOW}📊 Triggering market data ingestion...${NC}"
poetry run python -c "
from stocker.tasks.market_data import ingest_market_data

# Run the market data ingestion task
# This will:
# 1. Fetch price data for the trading universe
# 2. Validate data quality
# 3. Store in database
# 4. Publish to 'market-bars' stream to trigger signal generation
result = ingest_market_data()
print(f'✓ Market data ingestion completed: {result}')
"

# Sync any pending MOO order fills
echo -e "\n${YELLOW}📋 Syncing pending MOO order fills...${NC}"
poetry run python -c "
from stocker.tasks.order_sync import sync_moo_fills

# Sync fills for any MOO orders submitted previously
# This catches fills for orders that executed at market open
result = sync_moo_fills()
print(f'✓ MOO order sync completed: {result[\"synced\"]} filled, {result[\"failed\"]} failed, {result[\"pending\"]} pending')
"

echo -e "\n${GREEN}✅ Pipeline is running!${NC}"
echo "================================"
echo "Logs are in: logs/"
echo "API available at: http://localhost:8000"
echo "Press Ctrl+C to stop all consumers"
echo ""

# Keep script running and tail logs
tail -f logs/*.log
