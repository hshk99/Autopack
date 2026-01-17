#!/bin/bash
# =============================================================================
# Autopack Ideal State Verification Script
# =============================================================================
# Run this to check how close Autopack is to its ideal state.
# =============================================================================

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMP_TRACKING="C:/Users/hshk9/OneDrive/Backup/Desktop/AUTOPACK_IMPS_MASTER.json"

echo ""
echo "=== Autopack Ideal State Verification ==="
echo "Project: $PROJECT_DIR"
echo "IMP Tracking: $IMP_TRACKING"
echo ""

PASS=0
FAIL=0
CHECKS=()

# Helper function
check() {
    local name="$1"
    local result="$2"
    if [ "$result" = "PASS" ]; then
        echo -e "  [\033[0;32m✓\033[0m] $name"
        PASS=$((PASS+1))
        CHECKS+=("PASS:$name")
    else
        echo -e "  [\033[0;31m✗\033[0m] $name"
        FAIL=$((FAIL+1))
        CHECKS+=("FAIL:$name")
    fi
}

echo "Self-Improvement Loop:"
echo "----------------------"

# 1. Check TelemetryAnalyzer
if [ -f "$PROJECT_DIR/src/autopack/telemetry/analyzer.py" ]; then
    check "TelemetryAnalyzer exists" "PASS"
else
    check "TelemetryAnalyzer exists" "FAIL"
fi

# 2. Check telemetry_to_memory_bridge
if [ -f "$PROJECT_DIR/src/autopack/memory/telemetry_to_memory_bridge.py" ]; then
    check "Telemetry-to-memory bridge exists" "PASS"
else
    check "Telemetry-to-memory bridge exists" "FAIL"
fi

# 3. Check retrieve_insights
if grep -q "def retrieve_insights" "$PROJECT_DIR/src/autopack/memory/memory_service.py" 2>/dev/null; then
    check "MemoryService.retrieve_insights()" "PASS"
else
    check "MemoryService.retrieve_insights()" "FAIL"
fi

# 4. Check task generation wired (called, not just defined)
WIRED=$(grep "_generate_improvement_tasks" "$PROJECT_DIR/src/autopack/executor/autonomous_loop.py" 2>/dev/null | grep -v "def _generate" | wc -l)
if [ "$WIRED" -gt 0 ]; then
    check "Task generation wired to executor" "PASS"
else
    check "Task generation wired to executor" "FAIL"
fi

# 5. Check GeneratedTask persistence
if grep -q "class GeneratedTaskModel\|class GeneratedTask.*Base" "$PROJECT_DIR/src/autopack/models.py" 2>/dev/null; then
    check "GeneratedTask database model" "PASS"
else
    check "GeneratedTask database model" "FAIL"
fi

# 6. Check get_pending_tasks
if grep -q "def get_pending_tasks" "$PROJECT_DIR/src/autopack/roadc/task_generator.py" 2>/dev/null; then
    check "TaskGenerator.get_pending_tasks()" "PASS"
else
    check "TaskGenerator.get_pending_tasks()" "FAIL"
fi

echo ""
echo "ROAD Framework:"
echo "---------------"

# Check ROAD components
ROAD_COMPONENTS=("roada" "roadb" "roadc" "roadg" "roadh" "roadi" "roadj" "roadk" "roadl")
for component in "${ROAD_COMPONENTS[@]}"; do
    if [ -d "$PROJECT_DIR/src/autopack/$component" ] || ls "$PROJECT_DIR/src/autopack/$component"* 2>/dev/null | grep -q .; then
        check "ROAD-${component: -1}" "PASS"
    else
        check "ROAD-${component: -1}" "FAIL"
    fi
done

echo ""
echo "IMP Status:"
echo "-----------"

# Check IMP tracking file
if [ -f "$IMP_TRACKING" ]; then
    TOTAL=$(python -c "import json; d=json.load(open('$IMP_TRACKING')); print(d.get('statistics',{}).get('total_imps',0))" 2>/dev/null || echo "?")
    UNIMPLEMENTED=$(python -c "import json; d=json.load(open('$IMP_TRACKING')); print(d.get('statistics',{}).get('unimplemented',0))" 2>/dev/null || echo "?")
    CRITICAL=$(python -c "import json; d=json.load(open('$IMP_TRACKING')); print(len([i for i in d.get('unimplemented_imps',[]) if i.get('priority')=='critical']))" 2>/dev/null || echo "?")
    HIGH=$(python -c "import json; d=json.load(open('$IMP_TRACKING')); print(len([i for i in d.get('unimplemented_imps',[]) if i.get('priority')=='high']))" 2>/dev/null || echo "?")

    echo "  Total IMPs tracked: $TOTAL"
    echo "  Unimplemented: $UNIMPLEMENTED"
    echo "  - CRITICAL: $CRITICAL"
    echo "  - HIGH: $HIGH"

    if [ "$CRITICAL" = "0" ]; then
        check "No CRITICAL IMPs remaining" "PASS"
    else
        check "No CRITICAL IMPs remaining" "FAIL"
    fi
else
    echo "  IMP tracking file not found"
    check "No CRITICAL IMPs remaining" "FAIL"
fi

# Summary
echo ""
echo "=============================================="
echo "VERIFICATION SUMMARY"
echo "=============================================="
echo ""
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Total:  $((PASS + FAIL))"
echo ""

PERCENTAGE=$((PASS * 100 / (PASS + FAIL)))
echo "  Progress: ${PERCENTAGE}%"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "  \033[0;32mIDEAL_STATE_REACHED: true\033[0m"
    echo ""
    echo "  Autopack has reached its README ideal state!"
    exit 0
else
    echo -e "  \033[0;33mIDEAL_STATE_REACHED: false\033[0m"
    echo ""
    echo "  Remaining gaps to close:"
    for item in "${CHECKS[@]}"; do
        if [[ $item == FAIL:* ]]; then
            echo "    - ${item#FAIL:}"
        fi
    done
    exit 1
fi
