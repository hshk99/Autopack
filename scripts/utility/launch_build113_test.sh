#!/bin/bash
# BUILD-113 Real-World Test: Launch autonomous executor with autonomous fixes enabled

set -e

RUN_ID="research-tracer-test-build113"
API_URL="http://127.0.0.1:8001"

echo "================================================================================"
echo "BUILD-113 REAL-WORLD TEST: Research System with Autonomous Fixes"
echo "================================================================================"
echo ""
echo "Run ID: $RUN_ID"
echo "API URL: $API_URL"
echo "Feature: --enable-autonomous-fixes (BUILD-113)"
echo ""
echo "This will test:"
echo "1. Iterative Investigation (multi-round evidence collection)"
echo "2. Goal-Aware Decision Making (CLEAR_FIX vs RISKY vs AMBIGUOUS)"
echo "3. Decision Execution (patches with safety nets)"
echo "4. Risk threshold validation (100/200 line thresholds)"
echo ""
echo "Press Ctrl+C to stop..."
echo ""
sleep 3

# Launch with BUILD-113 enabled
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor \
  --run-id "$RUN_ID" \
  --api-url "$API_URL" \
  --enable-autonomous-fixes \
  --max-iterations 30 \
  --verbose \
  2>&1 | tee ".autonomous_runs/${RUN_ID}-build113-test.log"

echo ""
echo "================================================================================"
echo "TEST COMPLETE"
echo "================================================================================"
echo ""
echo "Log file: .autonomous_runs/${RUN_ID}-build113-test.log"
echo "Decisions: .autonomous_runs/$RUN_ID/decisions/*.json"
echo ""
echo "Review decision logs to validate BUILD-113 behavior"
