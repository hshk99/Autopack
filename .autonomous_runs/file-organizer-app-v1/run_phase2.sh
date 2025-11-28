#!/bin/bash
# FileOrganizer Phase 2 - Fully Autonomous Build Runner
#
# This script triggers the full Phase 2 build defined in WHATS_LEFT_TO_BUILD.md
# with zero human interaction. Auto-starts Autopack service if needed.
#
# Usage: ./run_phase2.sh

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================================"
echo "FILEORGANIZER PHASE 2 - AUTONOMOUS BUILD (FULLY UNATTENDED)"
echo "================================================================================"
echo ""
echo "Project: FileOrganizer v1.0 Alpha → Beta"
echo "Tasks: All items from WHATS_LEFT_TO_BUILD.md"
echo "Mode: Non-interactive (zero human prompts, auto-start service)"
echo ""
echo "Reports will be written to:"
echo "  - ${SCRIPT_DIR}/PHASE2_BUILD_REPORT_<timestamp>.md"
echo "  - ${SCRIPT_DIR}/PHASE2_BUILD_DATA_<timestamp>.json"
echo ""
echo "================================================================================"
echo ""

# Run the canonical Phase 2 runner (auto-starts Autopack API service)
python "${SCRIPT_DIR}/scripts/autopack_phase2_runner.py" --non-interactive

echo ""
echo "================================================================================"
echo "PHASE 2 BUILD COMPLETE"
echo "================================================================================"
echo ""
echo "Check the report files listed above for results."
echo ""
