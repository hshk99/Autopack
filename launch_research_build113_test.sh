#!/bin/bash
# BUILD-113 Real-World Test: Research System Integration
# Test autonomous fixes with research system implementation gaps

set -e

RUN_ID="research-build113-test"
API_URL="http://127.0.0.1:8001"

echo "================================================================================"
echo "BUILD-113 REAL-WORLD TEST: Research System Integration"
echo "================================================================================"
echo ""
echo "Run ID: $RUN_ID"
echo "API URL: $API_URL"
echo "Feature: --enable-autonomous-fixes (BUILD-113)"
echo ""
echo "Test Phases:"
echo "  1. gold_set.json (CLEAR_FIX test - low risk, auto-apply)"
echo "  2. build_history_integrator.py (RISKY test - high risk, human approval)"
echo "  3. research_phase.py (RISKY test - database schema, human approval)"
echo "  4. research_hooks.py (THRESHOLD test - 100-200 line boundary)"
echo "  5. research_commands.py (AMBIGUOUS test - UX decisions)"
echo "  6. research_review.py (RISKY test - workflow complexity)"
echo ""
echo "Expected BUILD-113 Behaviors:"
echo "  - CLEAR_FIX: Low-risk changes (<100 lines, high confidence)"
echo "  - RISKY: High-risk changes (>200 lines, database, integration)"
echo "  - AMBIGUOUS: Multiple valid approaches (UX, architecture)"
echo "  - NEED_MORE_EVIDENCE: Unclear requirements, needs investigation"
echo ""
echo "Metrics Tracked:"
echo "  - Decision distribution (CLEAR_FIX/RISKY/AMBIGUOUS/NEED_MORE)"
echo "  - Auto-fix rate (target: 30-50%)"
echo "  - Decision accuracy (actual vs expected)"
echo "  - Patch quality (applies cleanly vs failures)"
echo "  - Confidence calibration (scores align with outcomes)"
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
  2>&1 | tee ".autonomous_runs/${RUN_ID}/build113-test-execution.log"

echo ""
echo "================================================================================"
echo "TEST EXECUTION COMPLETE"
echo "================================================================================"
echo ""
echo "Logs:"
echo "  - Execution: .autonomous_runs/${RUN_ID}/build113-test-execution.log"
echo "  - Decisions: .autonomous_runs/${RUN_ID}/decisions/*.json"
echo "  - Patches: .autonomous_runs/${RUN_ID}/*.patch"
echo ""
echo "Next Steps:"
echo "  1. Review decision logs to validate BUILD-113 behavior"
echo "  2. Compare actual vs expected decisions from run_manifest.json"
echo "  3. Analyze decision quality and confidence scores"
echo "  4. Check patch generation correctness"
echo "  5. Validate risk threshold accuracy (100/200 lines)"
echo "  6. Document any improvements needed"
echo ""
