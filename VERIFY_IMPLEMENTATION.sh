#!/bin/bash
# Verification script for ROAD implementations

echo "============================================"
echo "ROAD Implementation Verification"
echo "============================================"
echo ""

# Check all files exist
echo "Checking implementation files..."
files=(
  "src/autopack/telemetry_outcomes.py"
  "src/autopack/executor/task_generator.py"
  "src/autopack/executor/policy_promoter.py"
  "scripts/analyze_run_telemetry.py"
  "scripts/governance_pr_gateway.py"
  "scripts/replay_campaign.py"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    echo "✓ $file"
  else
    echo "✗ MISSING: $file"
  fi
done

echo ""
echo "Checking test files..."
test_files=(
  "tests/autopack/test_telemetry_outcomes.py"
  "tests/executor/test_task_generator.py"
  "tests/executor/test_policy_promoter.py"
  "tests/scripts/test_analyze_run_telemetry.py"
  "tests/scripts/test_governance_pr_gateway.py"
  "tests/scripts/test_replay_campaign.py"
)

for file in "${test_files[@]}"; do
  if [ -f "$file" ]; then
    echo "✓ $file"
  else
    echo "✗ MISSING: $file"
  fi
done

echo ""
echo "Checking documentation..."
docs=(
  "ROAD_IMPLEMENTATION_SUMMARY.md"
  "IMPLEMENTATION_STATUS.md"
)

for file in "${docs[@]}"; do
  if [ -f "$file" ]; then
    echo "✓ $file"
  else
    echo "✗ MISSING: $file"
  fi
done

echo ""
echo "============================================"
echo "Running full test suite..."
echo "============================================"
python -m pytest \
    tests/autopack/test_telemetry_outcomes.py \
    tests/scripts/test_analyze_run_telemetry.py \
    tests/executor/test_task_generator.py \
    tests/scripts/test_governance_pr_gateway.py \
    tests/scripts/test_replay_campaign.py \
    tests/executor/test_policy_promoter.py \
    -v --tb=short 2>&1 | tail -20

echo ""
echo "============================================"
echo "Verification Complete!"
echo "============================================"
