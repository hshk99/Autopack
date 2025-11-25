#!/bin/bash
# Comprehensive probe script for dashboard features
# Tests all new functionality added in this session

set -e  # Exit on error

echo "============================================"
echo "Dashboard Features Probe Test"
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

API_BASE="http://localhost:8000"
PASS_COUNT=0
FAIL_COUNT=0

# Helper function to test endpoint
test_endpoint() {
    local name="$1"
    local method="$2"
    local endpoint="$3"
    local data="$4"
    local expected_status="$5"

    echo -n "Testing: $name ... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$API_BASE$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$API_BASE$endpoint" \
            -H "Content-Type: application/json" \
            -d "$data")
    fi

    status=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$status" = "$expected_status" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $status)"
        PASS_COUNT=$((PASS_COUNT + 1))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_status, got $status)"
        echo "Response: $body"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        return 1
    fi
}

echo "1. Testing API Health"
echo "---------------------"
test_endpoint "Root endpoint" "GET" "/" "" "200"
echo ""

echo "2. Testing Dashboard Endpoints"
echo "-------------------------------"

# Create a test run first
echo "Creating test run..."
RUN_DATA='{
  "run": {
    "run_id": "probe_test_run",
    "safety_profile": "normal",
    "run_scope": "multi_tier",
    "token_cap": 5000000
  },
  "tiers": [
    {"tier_id": "T1", "tier_index": 0, "name": "Probe Test Tier"}
  ],
  "phases": [
    {
      "phase_id": "F1.1",
      "phase_index": 0,
      "tier_id": "T1",
      "name": "Probe Test Phase",
      "task_category": "general",
      "complexity": "medium"
    }
  ]
}'

test_endpoint "Create test run" "POST" "/runs/start" "$RUN_DATA" "201"

# Test dashboard endpoints
test_endpoint "Get run status" "GET" "/dashboard/runs/probe_test_run/status" "" "200"
test_endpoint "Get usage summary" "GET" "/dashboard/usage?period=week" "" "200"
test_endpoint "Get model mappings" "GET" "/dashboard/models" "" "200"

# Test human notes
NOTE_DATA='{"run_id": "probe_test_run", "note": "Automated probe test note"}'
test_endpoint "Submit human note" "POST" "/dashboard/human-notes" "$NOTE_DATA" "200"

# Test model override
OVERRIDE_DATA='{
  "scope": "global",
  "role": "builder",
  "category": "tests",
  "complexity": "medium",
  "model": "gpt-4o-mini"
}'
test_endpoint "Model override (global)" "POST" "/dashboard/models/override" "$OVERRIDE_DATA" "200"

echo ""
echo "3. Testing Dashboard Static Files"
echo "----------------------------------"
test_endpoint "Dashboard UI (index.html)" "GET" "/dashboard/" "" "200"
echo ""

echo "4. Testing Configuration Files"
echo "-------------------------------"
if [ -f "config/models.yaml" ]; then
    echo -e "${GREEN}✓ PASS${NC} config/models.yaml exists"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo -e "${RED}✗ FAIL${NC} config/models.yaml missing"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi

if [ -f ".autopack/human_notes.md" ]; then
    echo -e "${GREEN}✓ PASS${NC} .autopack/human_notes.md created"
    PASS_COUNT=$((PASS_COUNT + 1))
else
    echo -e "${RED}✗ FAIL${NC} .autopack/human_notes.md not created"
    FAIL_COUNT=$((FAIL_COUNT + 1))
fi
echo ""

echo "5. Testing New Python Modules"
echo "------------------------------"
python -c "from src.autopack.usage_recorder import LlmUsageEvent; print('✓ usage_recorder imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} usage_recorder module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} usage_recorder module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

python -c "from src.autopack.usage_service import UsageService; print('✓ usage_service imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} usage_service module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} usage_service module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

python -c "from src.autopack.model_router import ModelRouter; print('✓ model_router imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} model_router module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} model_router module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

python -c "from src.autopack.llm_service import LlmService; print('✓ llm_service imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} llm_service module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} llm_service module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

python -c "from src.autopack.run_progress import RunProgress; print('✓ run_progress imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} run_progress module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} run_progress module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

python -c "from src.autopack.dashboard_schemas import DashboardRunStatus; print('✓ dashboard_schemas imports OK')" 2>&1 | grep -q "✓" && {
    echo -e "${GREEN}✓ PASS${NC} dashboard_schemas module"
    PASS_COUNT=$((PASS_COUNT + 1))
} || {
    echo -e "${RED}✗ FAIL${NC} dashboard_schemas module"
    FAIL_COUNT=$((FAIL_COUNT + 1))
}

echo ""
echo "============================================"
echo "Test Summary"
echo "============================================"
echo -e "${GREEN}Passed: $PASS_COUNT${NC}"
echo -e "${RED}Failed: $FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
