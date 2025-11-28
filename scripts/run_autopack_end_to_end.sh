#!/bin/bash
# End-to-End Autopack Execution Script
# Creates AND executes an Autopack run from a WHATS_LEFT_TO_BUILD.md file

set -e

# Configuration
PROJECT_DIR="${1:-.autonomous_runs/file-organizer-app-v1}"
TASKS_FILE="${2:-WHATS_LEFT_TO_BUILD.md}"
API_URL="${AUTOPACK_API_URL:-http://localhost:8000}"

echo "========================================"
echo "AUTOPACK END-TO-END EXECUTION"
echo "========================================"
echo "Project: $PROJECT_DIR"
echo "Tasks: $TASKS_FILE"
echo "API: $API_URL"
echo "========================================"
echo

# Step 1: Check if API is running
echo "[1/3] Checking Autopack API..."
if ! curl -sf "$API_URL/health" > /dev/null; then
    echo "ERROR: Autopack API is not running at $API_URL"
    echo "Start it with: cd /c/dev/Autopack && python -m uvicorn src.autopack.main:app --host 0.0.0.0 --port 8000"
    exit 1
fi
echo "✓ API is healthy"
echo

# Step 2: Create run using autopack_runner.py
echo "[2/3] Creating Autopack run from $TASKS_FILE..."
cd "/c/dev/Autopack/$PROJECT_DIR"

# Set API URL via environment variable (autopack_runner uses AUTOPACK_API_URL env var)
export AUTOPACK_API_URL="$API_URL"

RUN_ID=$(python scripts/autopack_runner.py \
    --non-interactive \
    --tasks-file "$TASKS_FILE" \
    2>&1 | grep -oP 'Run ID: \K[^\s]+' | tail -1)

if [ -z "$RUN_ID" ]; then
    echo "ERROR: Failed to create run"
    exit 1
fi

echo "✓ Run created: $RUN_ID"
echo

# Step 3: Execute run using autonomous_executor
echo "[3/3] Executing run autonomously..."
cd /c/dev/Autopack

# Check for API keys
if [ -z "$OPENAI_API_KEY" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "ERROR: No LLM API keys found"
    echo "Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable"
    exit 1
fi

# Execute with autonomous executor
export PYTHONPATH=src
export AUTOPACK_API_URL="$API_URL"
python -m autopack.autonomous_executor \
    --run-id "$RUN_ID" \
    --api-url "$API_URL"

echo
echo "========================================"
echo "EXECUTION COMPLETE"
echo "========================================"
echo "Run ID: $RUN_ID"
echo "View results: $API_URL/runs/$RUN_ID"
echo "========================================"
