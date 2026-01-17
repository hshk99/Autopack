#!/bin/bash
# =============================================================================
# Autopack Continuous Evolution Loop
# =============================================================================
# Runs discovery → implementation cycles until Autopack reaches its ideal state
# or max cycles exceeded.
#
# Usage:
#   ./ralph/evolution_loop.sh [max_cycles] [model]
#
# Examples:
#   ./ralph/evolution_loop.sh          # Default: 50 cycles, opus model
#   ./ralph/evolution_loop.sh 100      # 100 cycles max
#   ./ralph/evolution_loop.sh 50 sonnet # Use sonnet model
# =============================================================================

set -e

# Configuration
MAX_CYCLES=${1:-50}
MODEL=${2:-opus}
DISCOVERY_MAX_ITER=10
IMPLEMENTATION_MAX_ITER=20

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROMPT_FILE="$SCRIPT_DIR/PROMPT_evolution.md"
IDEAL_STATE_FILE="$SCRIPT_DIR/IDEAL_STATE_DEFINITION.md"
GUARDRAILS_FILE="$SCRIPT_DIR/guardrails.md"
IMP_TRACKING="C:/Users/hshk9/OneDrive/Backup/Desktop/AUTOPACK_IMPS_MASTER.json"

LOG_DIR="$PROJECT_DIR/.ralph/logs"
mkdir -p "$LOG_DIR"

# State tracking
CYCLE=0
IDEAL_REACHED=false
TOTAL_IMPS_CLOSED=0
START_TIME=$(date +%s)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_phase() {
    echo -e "${PURPLE}[PHASE]${NC} $1"
}

get_unimplemented_count() {
    python -c "
import json
try:
    with open('$IMP_TRACKING', 'r', encoding='utf-8') as f:
        d = json.load(f)
    print(d.get('statistics', {}).get('unimplemented', 0))
except Exception as e:
    print(0)
" 2>/dev/null || echo "0"
}

get_critical_count() {
    python -c "
import json
try:
    with open('$IMP_TRACKING', 'r', encoding='utf-8') as f:
        d = json.load(f)
    critical = [i for i in d.get('unimplemented_imps', []) if i.get('priority') == 'critical']
    print(len(critical))
except:
    print(0)
" 2>/dev/null || echo "0"
}

check_ideal_state() {
    # Run verification checks
    local pass_count=0
    local fail_count=0

    # 1. Check retrieve_insights
    if grep -q "def retrieve_insights" "$PROJECT_DIR/src/autopack/memory/memory_service.py" 2>/dev/null; then
        ((pass_count++))
    else
        ((fail_count++))
    fi

    # 2. Check task generation wired
    if grep "_generate_improvement_tasks" "$PROJECT_DIR/src/autopack/executor/autonomous_loop.py" 2>/dev/null | grep -qv "def "; then
        ((pass_count++))
    else
        ((fail_count++))
    fi

    # 3. Check task persistence
    if grep -q "class GeneratedTaskModel\|class GeneratedTask.*Base" "$PROJECT_DIR/src/autopack/models.py" 2>/dev/null; then
        ((pass_count++))
    else
        ((fail_count++))
    fi

    # 4. Check get_pending_tasks
    if grep -q "def get_pending_tasks" "$PROJECT_DIR/src/autopack/roadc/task_generator.py" 2>/dev/null; then
        ((pass_count++))
    else
        ((fail_count++))
    fi

    # 5. Check no critical IMPs
    local critical=$(get_critical_count)
    if [ "$critical" -eq 0 ]; then
        ((pass_count++))
    else
        ((fail_count++))
    fi

    echo "$pass_count:$fail_count"
}

format_duration() {
    local seconds=$1
    local hours=$((seconds / 3600))
    local minutes=$(((seconds % 3600) / 60))
    local secs=$((seconds % 60))
    printf "%02d:%02d:%02d" $hours $minutes $secs
}

# -----------------------------------------------------------------------------
# Main Evolution Loop
# -----------------------------------------------------------------------------

echo ""
echo "=============================================="
echo "   AUTOPACK CONTINUOUS EVOLUTION LOOP"
echo "=============================================="
echo ""
log_info "Max cycles: $MAX_CYCLES"
log_info "Model: $MODEL"
log_info "Discovery iterations per cycle: $DISCOVERY_MAX_ITER"
log_info "Implementation iterations per cycle: $IMPLEMENTATION_MAX_ITER"
log_info "IMP tracking: $IMP_TRACKING"
log_info "Log directory: $LOG_DIR"
echo ""

# Check prerequisites
if ! command -v claude &> /dev/null; then
    log_error "Claude CLI not found. Please install claude-code first."
    exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
    log_error "Prompt file not found: $PROMPT_FILE"
    exit 1
fi

if [ ! -f "$IMP_TRACKING" ]; then
    log_warning "IMP tracking file not found. Will be created on first discovery."
fi

# Initial state
INITIAL_UNIMPLEMENTED=$(get_unimplemented_count)
log_info "Starting with $INITIAL_UNIMPLEMENTED unimplemented IMPs"
echo ""

# Main loop
while [ $CYCLE -lt $MAX_CYCLES ] && [ "$IDEAL_REACHED" = "false" ]; do
    CYCLE=$((CYCLE + 1))
    CYCLE_START=$(date +%s)
    CYCLE_LOG="$LOG_DIR/cycle_${CYCLE}_$(date +%Y%m%d_%H%M%S).log"

    echo ""
    echo "=============================================="
    echo -e "${PURPLE}EVOLUTION CYCLE $CYCLE of $MAX_CYCLES${NC}"
    echo "=============================================="
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Log: $CYCLE_LOG"
    echo ""

    # =========================================================================
    # PHASE A: DISCOVERY
    # =========================================================================
    log_phase "Phase A: Discovery"

    DISCOVERY_ITER=0
    DISCOVERY_COMPLETE=false
    PRE_DISCOVERY_COUNT=$(get_unimplemented_count)

    while [ $DISCOVERY_ITER -lt $DISCOVERY_MAX_ITER ] && [ "$DISCOVERY_COMPLETE" = "false" ]; do
        DISCOVERY_ITER=$((DISCOVERY_ITER + 1))
        log_info "Discovery iteration $DISCOVERY_ITER/$DISCOVERY_MAX_ITER..."

        # Build combined prompt
        COMBINED_PROMPT=$(cat "$PROMPT_FILE" "$GUARDRAILS_FILE" 2>/dev/null)

        # Run Claude for discovery
        echo "$COMBINED_PROMPT" | claude -p \
            --dangerously-skip-permissions \
            --model "$MODEL" \
            2>&1 | tee -a "$CYCLE_LOG"

        # Check for discovery completion markers
        if grep -q "DISCOVERY_COMPLETE: true" "$CYCLE_LOG" 2>/dev/null; then
            DISCOVERY_COMPLETE=true
            log_success "Discovery phase complete"
        fi

        # Also check for explicit gap count
        if grep -q "NEW_GAPS_FOUND: 0" "$CYCLE_LOG" 2>/dev/null; then
            DISCOVERY_COMPLETE=true
            log_info "No new gaps found"
        fi

        sleep 2  # Brief pause between iterations
    done

    POST_DISCOVERY_COUNT=$(get_unimplemented_count)
    NEW_GAPS=$((POST_DISCOVERY_COUNT - PRE_DISCOVERY_COUNT))
    if [ $NEW_GAPS -gt 0 ]; then
        log_info "Discovered $NEW_GAPS new IMPs"
    fi

    # =========================================================================
    # PHASE B: IMPLEMENTATION
    # =========================================================================
    log_phase "Phase B: Implementation"

    UNIMPLEMENTED=$(get_unimplemented_count)

    if [ "$UNIMPLEMENTED" -eq 0 ]; then
        log_info "No IMPs to implement, proceeding to ideal state check"
    else
        log_info "$UNIMPLEMENTED IMPs to implement"

        IMPL_ITER=0
        IMPL_COMPLETE=false
        NO_PROGRESS=0
        CYCLE_IMPS_CLOSED=0

        while [ $IMPL_ITER -lt $IMPLEMENTATION_MAX_ITER ] && [ "$IMPL_COMPLETE" = "false" ]; do
            IMPL_ITER=$((IMPL_ITER + 1))
            PREV_UNIMPLEMENTED=$UNIMPLEMENTED

            log_info "Implementation iteration $IMPL_ITER/$IMPLEMENTATION_MAX_ITER..."

            # Run Claude for implementation
            COMBINED_PROMPT=$(cat "$PROMPT_FILE" "$GUARDRAILS_FILE" 2>/dev/null)
            echo "$COMBINED_PROMPT" | claude -p \
                --dangerously-skip-permissions \
                --model "$MODEL" \
                2>&1 | tee -a "$CYCLE_LOG"

            # Check progress
            UNIMPLEMENTED=$(get_unimplemented_count)
            CLOSED=$((PREV_UNIMPLEMENTED - UNIMPLEMENTED))

            if [ "$CLOSED" -gt 0 ]; then
                NO_PROGRESS=0
                CYCLE_IMPS_CLOSED=$((CYCLE_IMPS_CLOSED + CLOSED))
                TOTAL_IMPS_CLOSED=$((TOTAL_IMPS_CLOSED + CLOSED))
                log_success "Closed $CLOSED IMP(s). Remaining: $UNIMPLEMENTED"
            else
                NO_PROGRESS=$((NO_PROGRESS + 1))
                log_warning "No progress ($NO_PROGRESS/3)"

                if [ $NO_PROGRESS -ge 3 ]; then
                    log_error "Circuit breaker: No progress for 3 iterations"
                    break
                fi
            fi

            # Check for implementation completion
            if grep -q "IMPLEMENTATION_COMPLETE: true" "$CYCLE_LOG" 2>/dev/null; then
                IMPL_COMPLETE=true
            fi

            if [ "$UNIMPLEMENTED" -eq 0 ]; then
                IMPL_COMPLETE=true
                log_success "All IMPs implemented!"
            fi

            sleep 2  # Brief pause
        done

        log_info "Cycle closed $CYCLE_IMPS_CLOSED IMPs"
    fi

    # =========================================================================
    # PHASE C: IDEAL STATE CHECK
    # =========================================================================
    log_phase "Phase C: Ideal State Check"

    VERIFICATION=$(check_ideal_state)
    PASS_COUNT=$(echo "$VERIFICATION" | cut -d: -f1)
    FAIL_COUNT=$(echo "$VERIFICATION" | cut -d: -f2)

    log_info "Verification: $PASS_COUNT passed, $FAIL_COUNT failed"

    if [ "$FAIL_COUNT" -eq 0 ]; then
        IDEAL_REACHED=true

        CYCLE_END=$(date +%s)
        TOTAL_DURATION=$((CYCLE_END - START_TIME))

        echo ""
        echo "=============================================="
        echo -e "${GREEN}    IDEAL STATE REACHED!${NC}"
        echo "=============================================="
        echo ""
        log_success "Autopack has evolved to its README ideal state"
        log_info "Total cycles: $CYCLE"
        log_info "Total IMPs closed: $TOTAL_IMPS_CLOSED"
        log_info "Total duration: $(format_duration $TOTAL_DURATION)"
        echo ""

        # Write completion marker
        echo "IDEAL_STATE_REACHED: true" >> "$CYCLE_LOG"
        echo "EXIT_SIGNAL: true" >> "$CYCLE_LOG"
    else
        log_warning "$FAIL_COUNT ideal state checks failed"
        log_info "Continuing to next evolution cycle..."

        # Extract and show remaining gaps if possible
        CRITICAL_COUNT=$(get_critical_count)
        if [ "$CRITICAL_COUNT" -gt 0 ]; then
            log_warning "$CRITICAL_COUNT CRITICAL IMPs remaining"
        fi
    fi

    # Cycle summary
    CYCLE_END=$(date +%s)
    CYCLE_DURATION=$((CYCLE_END - CYCLE_START))
    log_info "Cycle $CYCLE completed in $(format_duration $CYCLE_DURATION)"

    # Cooldown between cycles
    if [ "$IDEAL_REACHED" = "false" ]; then
        log_info "Cooldown before next cycle..."
        sleep 5
    fi
done

# Final summary
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

echo ""
echo "=============================================="
echo "   EVOLUTION LOOP COMPLETE"
echo "=============================================="
echo ""

if [ "$IDEAL_REACHED" = "true" ]; then
    log_success "Status: IDEAL STATE REACHED"
else
    log_warning "Status: MAX CYCLES REACHED"
    log_info "Review logs in $LOG_DIR for details"
fi

echo ""
log_info "Summary:"
echo "  - Cycles completed: $CYCLE"
echo "  - IMPs closed: $TOTAL_IMPS_CLOSED"
echo "  - Starting IMPs: $INITIAL_UNIMPLEMENTED"
echo "  - Remaining IMPs: $(get_unimplemented_count)"
echo "  - Total duration: $(format_duration $TOTAL_DURATION)"
echo ""
log_info "Logs saved to: $LOG_DIR"
echo ""
