#!/usr/bin/env bash
# Chunk A probe script: autonomous_probe_run_state.sh
#
# Per Chunk A requirements:
# - Creates a dummy run
# - Enqueues a dummy tier and phases
# - Advances them through the state machine without touching git
# - Asserts the expected DB entries and files exist

set -e

echo "=== Autopack Chunk A Probe: Run State ==="
echo ""

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
RUN_ID="probe-run-$(date +%s)"
AUTONOMOUS_RUNS_DIR="${AUTONOMOUS_RUNS_DIR:-.autonomous_runs}"

echo "Configuration:"
echo "  API URL: $API_URL"
echo "  Run ID: $RUN_ID"
echo "  Autonomous runs dir: $AUTONOMOUS_RUNS_DIR"
echo ""

# Wait for API to be ready
echo "Waiting for API to be ready..."
for i in {1..30}; do
    if curl -s "${API_URL}/health" > /dev/null 2>&1; then
        echo "API is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "ERROR: API did not become ready in time"
        exit 1
    fi
    sleep 1
done
echo ""

# Test 1: Create a run with tiers and phases
echo "Test 1: Creating run with 2 tiers and 3 phases..."
RESPONSE=$(curl -s -X POST "${API_URL}/runs/start" \
    -H "Content-Type: application/json" \
    -d "{
        \"run\": {
            \"run_id\": \"${RUN_ID}\",
            \"safety_profile\": \"normal\",
            \"run_scope\": \"multi_tier\",
            \"token_cap\": 5000000,
            \"max_phases\": 25,
            \"max_duration_minutes\": 120
        },
        \"tiers\": [
            {
                \"tier_id\": \"T1\",
                \"tier_index\": 0,
                \"name\": \"Foundation\",
                \"description\": \"Core infrastructure\"
            },
            {
                \"tier_id\": \"T2\",
                \"tier_index\": 1,
                \"name\": \"Features\",
                \"description\": \"Feature implementation\"
            }
        ],
        \"phases\": [
            {
                \"phase_id\": \"F1.1\",
                \"phase_index\": 0,
                \"tier_id\": \"T1\",
                \"name\": \"Setup database models\",
                \"description\": \"Create initial DB schema\",
                \"task_category\": \"schema_change\",
                \"complexity\": \"medium\",
                \"builder_mode\": \"scaffolding_heavy\"
            },
            {
                \"phase_id\": \"F1.2\",
                \"phase_index\": 1,
                \"tier_id\": \"T1\",
                \"name\": \"Add API endpoints\",
                \"description\": \"Create REST API\",
                \"task_category\": \"feature_scaffolding\",
                \"complexity\": \"low\",
                \"builder_mode\": \"tweak_light\"
            },
            {
                \"phase_id\": \"F2.1\",
                \"phase_index\": 2,
                \"tier_id\": \"T2\",
                \"name\": \"Implement business logic\",
                \"description\": \"Core feature implementation\",
                \"task_category\": \"feature_scaffolding\",
                \"complexity\": \"high\",
                \"builder_mode\": \"scaffolding_heavy\"
            }
        ]
    }")

# Check if run was created
RUN_STATE=$(echo "$RESPONSE" | grep -o '"state":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ "$RUN_STATE" != "RUN_CREATED" ]; then
    echo "ERROR: Run was not created properly. State: $RUN_STATE"
    echo "Response: $RESPONSE"
    exit 1
fi
echo "✓ Run created with state: $RUN_STATE"
echo ""

# Test 2: Verify file layout was created
echo "Test 2: Verifying file layout..."
FILES_TO_CHECK=(
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/run_summary.md"
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/tiers/tier_00_Foundation.md"
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/tiers/tier_01_Features.md"
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/phases/phase_00_F1.1.md"
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/phases/phase_01_F1.2.md"
    "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/phases/phase_02_F2.1.md"
)

for file in "${FILES_TO_CHECK[@]}"; do
    if [ ! -f "$file" ]; then
        echo "ERROR: Expected file not found: $file"
        exit 1
    fi
    echo "✓ Found: $file"
done
echo ""

# Test 3: Retrieve run and verify structure
echo "Test 3: Retrieving run details..."
RUN_DETAILS=$(curl -s "${API_URL}/runs/${RUN_ID}")
TIER_COUNT=$(echo "$RUN_DETAILS" | grep -o '"tier_id"' | wc -l)
if [ "$TIER_COUNT" -ne 2 ]; then
    echo "ERROR: Expected 2 tiers, found $TIER_COUNT"
    exit 1
fi
echo "✓ Run has 2 tiers"

PHASE_COUNT=$(echo "$RUN_DETAILS" | grep -o '"phase_id":"F[0-9]\.[0-9]"' | wc -l)
if [ "$PHASE_COUNT" -ne 3 ]; then
    echo "ERROR: Expected 3 phases, found $PHASE_COUNT"
    exit 1
fi
echo "✓ Run has 3 phases"
echo ""

# Test 4: Update phase status
echo "Test 4: Updating phase status..."
UPDATE_RESPONSE=$(curl -s -X POST "${API_URL}/runs/${RUN_ID}/phases/F1.1/update_status" \
    -H "Content-Type: application/json" \
    -d '{
        "state": "EXECUTING",
        "builder_attempts": 1,
        "tokens_used": 1000
    }')

UPDATED_STATE=$(echo "$UPDATE_RESPONSE" | grep -o '"state":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ "$UPDATED_STATE" != "EXECUTING" ]; then
    echo "ERROR: Phase state was not updated properly. State: $UPDATED_STATE"
    exit 1
fi
echo "✓ Phase F1.1 updated to state: $UPDATED_STATE"
echo ""

# Test 5: Advance phase through states
echo "Test 5: Advancing phase through state machine..."
STATES=("GATE" "CI_RUNNING" "COMPLETE")
for state in "${STATES[@]}"; do
    curl -s -X POST "${API_URL}/runs/${RUN_ID}/phases/F1.1/update_status" \
        -H "Content-Type: application/json" \
        -d "{\"state\": \"${state}\"}" > /dev/null
    echo "✓ Advanced to state: $state"
done
echo ""

# Test 6: Verify phase is now complete
echo "Test 6: Verifying final phase state..."
FINAL_RUN=$(curl -s "${API_URL}/runs/${RUN_ID}")
PHASE_STATE=$(echo "$FINAL_RUN" | grep -A 5 '"phase_id":"F1.1"' | grep -o '"state":"[^"]*"' | head -1 | cut -d'"' -f4)
if [ "$PHASE_STATE" != "COMPLETE" ]; then
    echo "ERROR: Phase did not reach COMPLETE state. State: $PHASE_STATE"
    exit 1
fi
echo "✓ Phase F1.1 is in state: $PHASE_STATE"
echo ""

echo "=== All tests passed! ==="
echo ""
echo "Summary:"
echo "  - Created run: $RUN_ID"
echo "  - Verified file layout under $AUTONOMOUS_RUNS_DIR/$RUN_ID/"
echo "  - Created 2 tiers and 3 phases"
echo "  - Advanced phase F1.1 through state machine"
echo "  - All DB entries and files verified"
echo ""
echo "Chunk A implementation is working correctly!"
