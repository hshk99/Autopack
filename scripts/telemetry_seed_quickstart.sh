#!/usr/bin/env bash
#
# Telemetry Seeding Quickstart Script
#
# This script demonstrates the complete workflow for seeding telemetry data:
# 1. Create fresh telemetry seed DB
# 2. Seed known-success run
# 3. Start API server with correct DATABASE_URL
# 4. Drain phases to collect telemetry
# 5. Validate and analyze results
#
# Usage:
#   bash scripts/telemetry_seed_quickstart.sh
#
# Requirements:
#   - Python 3.12+
#   - All dependencies installed (pip install -r requirements.txt)
#   - Run from repository root (c:\dev\Autopack)

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
DB_FILE="autopack_telemetry_seed.db"
RUN_ID="telemetry-collection-v4"
API_PORT=8000
API_URL="http://127.0.0.1:${API_PORT}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "========================================================================"
echo "TELEMETRY SEEDING QUICKSTART"
echo "========================================================================"
echo ""

# Step 1: Create fresh telemetry seed DB
echo -e "${YELLOW}[Step 1/5] Creating fresh telemetry seed DB...${NC}"
if [ -f "$DB_FILE" ]; then
    echo "  Removing old ${DB_FILE}..."
    rm -f "$DB_FILE"
fi

PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    python -c "from autopack.database import init_db; init_db(); print('[OK] Schema initialized')"

echo -e "${GREEN}✓ Telemetry seed DB created${NC}"
echo ""

# Step 2: Seed known-success run
echo -e "${YELLOW}[Step 2/5] Seeding known-success run...${NC}"
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    python scripts/create_telemetry_collection_run.py

echo -e "${GREEN}✓ Run '${RUN_ID}' created with 10 phases${NC}"
echo ""

# Step 3: Verify DB state
echo -e "${YELLOW}[Step 3/5] Verifying DB state...${NC}"
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    python scripts/db_identity_check.py | head -20

echo -e "${GREEN}✓ DB state verified${NC}"
echo ""

# Step 4: Start API server in background
echo -e "${YELLOW}[Step 4/5] Starting API server (${API_URL})...${NC}"
echo "  Press Ctrl+C to stop the server after draining completes"
echo ""

# Start API server with correct DATABASE_URL
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    python -m uvicorn autopack.main:app --host 127.0.0.1 --port ${API_PORT} &

API_PID=$!
echo "  API server started (PID: ${API_PID})"

# Wait for API server to start
sleep 3

# Check if API server is running
if ! kill -0 $API_PID 2>/dev/null; then
    echo -e "${RED}✗ API server failed to start${NC}"
    exit 1
fi

echo -e "${GREEN}✓ API server running at ${API_URL}${NC}"
echo ""

# Step 5: Drain phases with batch drain controller
echo -e "${YELLOW}[Step 5/5] Draining phases to collect telemetry...${NC}"
echo "  This will drain 10 phases from run '${RUN_ID}'"
echo "  TELEMETRY_DB_ENABLED=1 ensures telemetry collection"
echo ""

# Trap Ctrl+C to clean up API server
trap "echo ''; echo 'Stopping API server...'; kill $API_PID 2>/dev/null; exit 0" INT TERM

# Drain phases with telemetry enabled
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    TELEMETRY_DB_ENABLED=1 \
    python scripts/batch_drain_controller.py \
        --run-id "${RUN_ID}" \
        --batch-size 10 \
        --api-url "${API_URL}" \
        --phase-timeout-seconds 900 \
        --max-total-minutes 60

echo ""
echo -e "${GREEN}✓ Phases drained${NC}"
echo ""

# Stop API server
echo "Stopping API server..."
kill $API_PID 2>/dev/null || true
wait $API_PID 2>/dev/null || true

# Step 6: Validate telemetry collection
echo ""
echo -e "${YELLOW}[Validation] Checking telemetry results...${NC}"
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///${DB_FILE}" \
    python scripts/db_identity_check.py | grep -A 20 "Telemetry Statistics"

echo ""
echo "========================================================================"
echo -e "${GREEN}TELEMETRY SEEDING COMPLETE${NC}"
echo "========================================================================"
echo ""
echo "Next steps:"
echo "  1. Analyze telemetry:"
echo "     PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///${DB_FILE}\" \\"
echo "         python scripts/analyze_token_telemetry_v3.py --success-only"
echo ""
echo "  2. Export telemetry to CSV:"
echo "     PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///${DB_FILE}\" \\"
echo "         python scripts/export_token_estimation_telemetry.py"
echo ""
echo "Database: ${DB_FILE}"
echo "Run ID: ${RUN_ID}"
echo "========================================================================"
