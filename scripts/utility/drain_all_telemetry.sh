#!/bin/bash
# Drain all telemetry collection phases
set -e

export PYTHONUTF8=1
export PYTHONPATH=src
export TELEMETRY_DB_ENABLED=1
export AUTOPACK_SKIP_CI=1
export AUTOPACK_API_URL="http://127.0.0.1:8123"
# Use relative path from repo root (run this script from repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export DATABASE_URL="sqlite:///${REPO_ROOT}/telemetry_seed_fullrun.db"

PHASES=(
  "telemetry-p2-number-util"
  "telemetry-p3-list-util"
  "telemetry-p4-date-util"
  "telemetry-p5-dict-util"
  "telemetry-p6-string-tests"
  "telemetry-p7-number-tests"
  "telemetry-p8-list-tests"
  "telemetry-p9-readme"
  "telemetry-p10-file-util"
)

for phase_id in "${PHASES[@]}"; do
  echo "========================================"
  echo "Draining: $phase_id"
  echo "========================================"
  timeout 600 python scripts/drain_one_phase.py \
    --run-id telemetry-collection-v4 \
    --phase-id "$phase_id" \
    --force \
    --no-dual-auditor || echo "Phase $phase_id failed or timed out"
  echo ""
done

echo "All phases drained!"
