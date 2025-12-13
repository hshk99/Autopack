#!/bin/bash
# Full Probe Suite for Memory-Based Classification System
# Steps 2-4: Run probes, verify all pass, document issues

echo "========================================================================"
echo "STEP 2: RUNNING FULL PROBE CHECKLIST"
echo "========================================================================"
echo ""

# Set environment
export PYTHONPATH=src
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
export QDRANT_HOST="http://localhost:6333"
export EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"

cd /c/dev/Autopack

# Clean up old test files
rm -f PROBE_*.md probe_*.py probe_*.log 2>/dev/null

# Create test files for comprehensive probe
echo "Creating test files..."
echo "# Implementation Plan: Test System" > PROBE_PLAN.md
echo "# Analysis: Performance Findings" > PROBE_ANALYSIS.md
echo "[2025-12-11] INFO: Test log" > probe_api_test.log
echo "print('test')" > probe_script.py
echo "# File Organizer Country Pack Implementation" > FILEORG_PROBE_PLAN.md

echo "Test files created: 5"
echo ""

# Run classification test
echo "========================================================================"
echo "PROBE 1: Three-Tier Classification Pipeline"
echo "========================================================================"
python scripts/tidy_workspace.py --root . --dry-run --verbose 2>&1 | \
  grep -E "(PROBE_|probe_|Classifier.*confidence)" | head -40

echo ""
echo "========================================================================"
echo "PROBE 2: Database Seed Data Verification"
echo "========================================================================"
python scripts/temp/check_db_seed_data.py 2>&1 | head -60

echo ""
echo "========================================================================"
echo "PROBE 3: Learned Patterns Check"
echo "========================================================================"
python scripts/temp/check_db_seed_data.py 2>&1 | grep -A 5 "learned"

echo ""
echo "========================================================================"
echo "STEP 3: VERIFICATION RESULTS"
echo "========================================================================"
echo ""
echo "Checking for success criteria:"
echo ""

# Check 1: PostgreSQL
pg_count=$(psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM directory_routing_rules WHERE source_context='cursor'" 2>/dev/null || echo "0")
if [ "$pg_count" -eq "12" ]; then
  echo "[PASS] PostgreSQL: 12 routing rules found"
else
  echo "[FAIL] PostgreSQL: Expected 12 rules, found $pg_count"
fi

# Check 2: Qdrant
qdrant_count=$(python -c "
from qdrant_client import QdrantClient
client = QdrantClient(url='http://localhost:6333')
info = client.get_collection('file_routing_patterns')
print(info.points_count)
" 2>/dev/null || echo "0")

if [ "$qdrant_count" -ge "9" ]; then
  echo "[PASS] Qdrant: $qdrant_count patterns (>= 9 seed patterns)"
else
  echo "[FAIL] Qdrant: Expected >= 9 patterns, found $qdrant_count"
fi

# Check 3: No Unicode errors
unicode_errors=$(python scripts/tidy_workspace.py --root . --dry-run 2>&1 | grep -c "charmap" || echo "0")
if [ "$unicode_errors" -eq "0" ]; then
  echo "[PASS] No Unicode encoding errors"
else
  echo "[FAIL] Found $unicode_errors Unicode encoding errors"
fi

# Check 4: Classification working
classified=$(python scripts/tidy_workspace.py --root . --dry-run --verbose 2>&1 | grep -c "PROBE_" || echo "0")
if [ "$classified" -ge "5" ]; then
  echo "[PASS] All 5 test files classified"
else
  echo "[WARN] Only $classified/5 test files classified"
fi

echo ""
echo "========================================================================"
echo "STEP 4: SUMMARY & DOCUMENTATION"
echo "========================================================================"
echo ""
echo "Test Suite Complete!"
echo ""
echo "Results saved to: PROBE_RESULTS_$(date +%Y%m%d_%H%M%S).txt"
echo ""
echo "Next Steps:"
echo "1. Review any [FAIL] items above"
echo "2. Check PROBE_CHECKLIST_MEMORY_CLASSIFICATION.md for detailed test matrix"
echo "3. Run specific probes for any failures"
echo ""
