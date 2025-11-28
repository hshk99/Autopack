#!/bin/bash
# FileOrganizer Phase 2 - Unattended Autonomous Build Runner
#
# This script triggers the full Phase 2 build defined in WHATS_LEFT_TO_BUILD.md
# with zero human interaction.
#
# Usage: ./run_phase2.sh

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================================"
echo "FILEORGANIZER PHASE 2 - AUTONOMOUS BUILD (UNATTENDED MODE)"
echo "================================================================================"
echo ""
echo "Project: FileOrganizer v1.0 Alpha → Beta"
echo "Tasks: All items from WHATS_LEFT_TO_BUILD.md"
echo "Mode: Non-interactive (zero human prompts)"
echo ""
echo "Reports will be written to:"
echo "  - ${SCRIPT_DIR}/PHASE2_BUILD_REPORT_<timestamp>.md"
echo "  - ${SCRIPT_DIR}/PHASE2_BUILD_DATA_<timestamp>.json"
echo ""
echo "================================================================================"
echo ""

# Run the orchestrator in non-interactive mode
python "${SCRIPT_DIR}/scripts/phase2_orchestrator.py" --non-interactive

echo ""
echo "================================================================================"
echo "PHASE 2 BUILD COMPLETE"
echo "================================================================================"
echo ""
echo "Check the report files listed above for results."
echo ""
