#!/bin/bash
# Full System Integration Test

echo "========================================================================"
echo "AUTOPACK MEMORY CLASSIFICATION SYSTEM - COMPREHENSIVE PROBE"
echo "========================================================================"
echo ""

# 1. Check databases
echo "=== 1. Checking Databases ==="
PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
QDRANT_HOST="http://localhost:6333" \
python scripts/temp/check_db_seed_data.py | head -50
echo ""

# 2. Create diverse test files
echo "=== 2. Creating Test Files ==="
echo "# Implementation Plan: Test System" > PROBE_PLAN.md
echo "# Analysis: Test Findings" > PROBE_ANALYSIS.md
echo "[2025-12-11] INFO: Test log entry" > probe_api_test.log
echo "print('test')" > probe_script.py
echo "# File Organizer Country Pack Plan" > FILEORG_PROBE_PLAN.md
echo "Created 5 test files"
echo ""

# 3. Run tidy with verbose logging
echo "=== 3. Running Tidy (Dry-Run) ==="
PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
QDRANT_HOST="http://localhost:6333" \
python scripts/tidy_workspace.py --root . --dry-run --verbose 2>&1 | grep -E "(PROBE_|probe_|Classifier|Memory|Pattern|Qdrant error)" | head -30
echo ""

# 4. Check learned patterns
echo "=== 4. Checking Learned Patterns ==="
PYTHONPATH=src QDRANT_HOST="http://localhost:6333" \
python scripts/temp/check_db_seed_data.py 2>/dev/null | grep -A 20 "Qdrant File Routing Patterns" | grep "learned"
echo ""

# 5. Verification Summary
echo "========================================================================"
echo "VERIFICATION SUMMARY"
echo "========================================================================"
echo "Check above output for:"
echo "  [ ] All 5 test files classified"
echo "  [ ] No 'Qdrant error: object has no attribute search' messages"
echo "  [ ] Confidence values > 0.5"
echo "  [ ] Correct project/type detection (autopack/file-organizer-app-v1)"
echo "  [ ] PostgreSQL/Qdrant/Pattern methods working"
echo ""
echo "Test complete!"
