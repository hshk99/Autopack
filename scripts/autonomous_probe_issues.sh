#!/usr/bin/env bash
# Chunk B probe script: autonomous_probe_issues.sh
#
# Per Chunk B requirements:
# - Simulates a run with phases that log minor and major issues
# - Verifies phase files, run index, and backlog entries
# - Tests de-duplication and aging behavior

set -e

echo "=== Autopack Chunk B Probe: Issue Tracking ==="
echo ""

# Configuration
API_URL="${API_URL:-http://localhost:8000}"
RUN_ID="probe-issues-$(date +%s)"
AUTONOMOUS_RUNS_DIR="${AUTONOMOUS_RUNS_DIR:-.autonomous_runs}"

echo "Configuration:"
echo "  API URL: $API_URL"
echo "  Run ID: $RUN_ID"
echo "  Autonomous runs dir: $AUTONOMOUS_RUNS_DIR"
echo ""

# Wait for API
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

# Test 1: Create a run with 2 phases
echo "Test 1: Creating run with 2 phases..."
curl -s -X POST "${API_URL}/runs/start" \
    -H "Content-Type: application/json" \
    -d "{
        \"run\": {
            \"run_id\": \"${RUN_ID}\",
            \"safety_profile\": \"normal\",
            \"run_scope\": \"multi_tier\"
        },
        \"tiers\": [
            {\"tier_id\": \"T1\", \"tier_index\": 0, \"name\": \"Core\"}
        ],
        \"phases\": [
            {
                \"phase_id\": \"P1\",
                \"phase_index\": 0,
                \"tier_id\": \"T1\",
                \"name\": \"Phase with minor issue\",
                \"task_category\": \"feature_scaffolding\",
                \"complexity\": \"low\"
            },
            {
                \"phase_id\": \"P2\",
                \"phase_index\": 1,
                \"tier_id\": \"T1\",
                \"name\": \"Phase with major issue\",
                \"task_category\": \"schema_change\",
                \"complexity\": \"high\"
            }
        ]
    }" > /dev/null
echo "✓ Run created"
echo ""

# Test 2: Record a minor issue in phase P1
echo "Test 2: Recording minor issue in phase P1..."
RESPONSE=$(curl -s -X POST "${API_URL}/runs/${RUN_ID}/phases/P1/record_issue?issue_key=test_failure__missing_assert&severity=minor&source=test&category=test_failure&task_category=feature_scaffolding&complexity=low&evidence_refs=tests/test_foo.py::test_bar")
echo "✓ Minor issue recorded"

# Verify phase file
if [ -f "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/phase_00_P1_issues.json" ]; then
    echo "✓ Phase issue file created: phase_00_P1_issues.json"
    MINOR_COUNT=$(cat "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/phase_00_P1_issues.json" | grep -o '"minor_issue_count": [0-9]*' | grep -o '[0-9]*')
    if [ "$MINOR_COUNT" = "1" ]; then
        echo "✓ Minor issue count is 1"
    else
        echo "ERROR: Expected minor_issue_count=1, got $MINOR_COUNT"
        exit 1
    fi
else
    echo "ERROR: Phase issue file not found"
    exit 1
fi
echo ""

# Test 3: Record a major issue in phase P2
echo "Test 3: Recording major issue in phase P2..."
curl -s -X POST "${API_URL}/runs/${RUN_ID}/phases/P2/record_issue?issue_key=schema_violation__missing_migration&severity=major&source=static_check&category=schema_contract_change&task_category=schema_change&complexity=high" > /dev/null
echo "✓ Major issue recorded"

# Verify phase file
if [ -f "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/phase_01_P2_issues.json" ]; then
    echo "✓ Phase issue file created: phase_01_P2_issues.json"
    MAJOR_COUNT=$(cat "${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/phase_01_P2_issues.json" | grep -o '"major_issue_count": [0-9]*' | grep -o '[0-9]*')
    if [ "$MAJOR_COUNT" = "1" ]; then
        echo "✓ Major issue count is 1"
    else
        echo "ERROR: Expected major_issue_count=1, got $MAJOR_COUNT"
        exit 1
    fi
else
    echo "ERROR: Phase issue file not found"
    exit 1
fi
echo ""

# Test 4: Record same issue in P1 again (test de-duplication)
echo "Test 4: Recording duplicate issue in P1..."
curl -s -X POST "${API_URL}/runs/${RUN_ID}/phases/P1/record_issue?issue_key=test_failure__missing_assert&severity=minor&source=test&category=test_failure" > /dev/null
echo "✓ Duplicate issue recorded"

# Verify still only 1 distinct issue
ISSUE_FILE="${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/phase_00_P1_issues.json"
ISSUE_COUNT=$(cat "$ISSUE_FILE" | grep -o '"issue_key"' | wc -l)
if [ "$ISSUE_COUNT" = "1" ]; then
    echo "✓ Still only 1 distinct issue in phase file"
else
    echo "ERROR: Expected 1 distinct issue, found $ISSUE_COUNT"
    exit 1
fi

OCCURRENCE_COUNT=$(cat "$ISSUE_FILE" | grep -o '"occurrence_count": [0-9]*' | grep -o '[0-9]*')
if [ "$OCCURRENCE_COUNT" = "2" ]; then
    echo "✓ Occurrence count is 2"
else
    echo "ERROR: Expected occurrence_count=2, got $OCCURRENCE_COUNT"
    exit 1
fi
echo ""

# Test 5: Verify run issue index
echo "Test 5: Verifying run issue index..."
INDEX_FILE="${AUTONOMOUS_RUNS_DIR}/${RUN_ID}/issues/run_issue_index.json"
if [ -f "$INDEX_FILE" ]; then
    echo "✓ Run issue index file exists"

    # Check both issues are in index
    if grep -q "test_failure__missing_assert" "$INDEX_FILE"; then
        echo "✓ Minor issue in run index"
    else
        echo "ERROR: Minor issue not found in run index"
        exit 1
    fi

    if grep -q "schema_violation__missing_migration" "$INDEX_FILE"; then
        echo "✓ Major issue in run index"
    else
        echo "ERROR: Major issue not found in run index"
        exit 1
    fi
else
    echo "ERROR: Run issue index file not found"
    exit 1
fi
echo ""

# Test 6: Verify project backlog
echo "Test 6: Verifying project backlog..."
BACKLOG_FILE="project_issue_backlog.json"
if [ -f "$BACKLOG_FILE" ]; then
    echo "✓ Project backlog file exists"

    # Check both issues are in backlog
    if grep -q "test_failure__missing_assert" "$BACKLOG_FILE"; then
        echo "✓ Minor issue in project backlog"
    else
        echo "ERROR: Minor issue not found in project backlog"
        exit 1
    fi

    if grep -q "schema_violation__missing_migration" "$BACKLOG_FILE"; then
        echo "✓ Major issue in project backlog"
    else
        echo "ERROR: Major issue not found in project backlog"
        exit 1
    fi

    # Check age_in_runs is 1 (first occurrence)
    AGE_IN_RUNS=$(cat "$BACKLOG_FILE" | grep -A 5 "test_failure__missing_assert" | grep -o '"age_in_runs": [0-9]*' | grep -o '[0-9]*' | head -1)
    if [ "$AGE_IN_RUNS" = "1" ]; then
        echo "✓ Age in runs is 1"
    else
        echo "ERROR: Expected age_in_runs=1, got $AGE_IN_RUNS"
        exit 1
    fi
else
    echo "ERROR: Project backlog file not found"
    exit 1
fi
echo ""

# Test 7: Retrieve run issue index via API
echo "Test 7: Retrieving run issue index via API..."
INDEX_JSON=$(curl -s "${API_URL}/runs/${RUN_ID}/issues/index")
if echo "$INDEX_JSON" | grep -q "test_failure__missing_assert"; then
    echo "✓ Run index API works"
else
    echo "ERROR: Issue not found in API response"
    exit 1
fi
echo ""

# Test 8: Retrieve project backlog via API
echo "Test 8: Retrieving project backlog via API..."
BACKLOG_JSON=$(curl -s "${API_URL}/project/issues/backlog")
if echo "$BACKLOG_JSON" | grep -q "test_failure__missing_assert"; then
    echo "✓ Project backlog API works"
else
    echo "ERROR: Issue not found in backlog API response"
    exit 1
fi
echo ""

echo "=== All Chunk B tests passed! ==="
echo ""
echo "Summary:"
echo "  - Created run: $RUN_ID"
echo "  - Recorded 1 minor issue and 1 major issue"
echo "  - Verified de-duplication (occurrence count)"
echo "  - Verified phase issue files created"
echo "  - Verified run issue index created"
echo "  - Verified project backlog created with aging=1"
echo "  - All API endpoints working"
echo ""
echo "Chunk B implementation is working correctly!"
