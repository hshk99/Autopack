#!/usr/bin/env bash
#
# Local CI Parity Script (Bash)
#
# Runs the same must-pass checks as CI to reduce "works locally but not in CI" churn.
# Exit code 0 = all checks pass (green), non-zero = failures detected (red).
#
# Usage:
#   bash scripts/ci_parity.sh
#   ./scripts/ci_parity.sh  # (if chmod +x)
#
# Checks:
#   1. Ruff linting (src/ tests/)
#   2. Black formatting (src/ tests/)
#   3. Core tests subset (excludes research/aspirational, max 5 failures)
#   4. Docs/SOT integrity (BUILD_HISTORY unique IDs, doc links, SOT drift)
#   5. Security normalization + diff gate (fixture validation)

set -euo pipefail

echo "=========================================="
echo "Local CI Parity Check"
echo "=========================================="
echo ""

# Track failures
FAILURES=0

# 1. Ruff linting
echo "==> [1/5] Ruff linting..."
if ruff check src/ tests/; then
    echo "✓ Ruff: PASS"
else
    echo "✗ Ruff: FAIL"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 2. Black formatting
echo "==> [2/5] Black formatting..."
if black --check src/ tests/; then
    echo "✓ Black: PASS"
else
    echo "✗ Black: FAIL"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 3. Core tests (exclude research/aspirational, max 5 failures)
echo "==> [3/5] Core tests (excluding research/aspirational)..."
if PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" \
   pytest tests/ \
   -m "not research and not aspirational and not legacy_contract" \
   -v --maxfail=5 -x; then
    echo "✓ Core tests: PASS"
else
    echo "✗ Core tests: FAIL"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 4. Docs/SOT integrity checks
echo "==> [4/5] Docs/SOT integrity..."
DOC_FAILURES=0

# BUILD_HISTORY unique IDs
if python -c "from tests.docs.test_build_history_unique_build_ids import test_build_history_has_unique_build_ids; test_build_history_has_unique_build_ids()"; then
    echo "  ✓ BUILD_HISTORY unique IDs"
else
    echo "  ✗ BUILD_HISTORY unique IDs"
    DOC_FAILURES=$((DOC_FAILURES + 1))
fi

# Doc link hygiene
if python scripts/check_doc_links.py; then
    echo "  ✓ Doc link hygiene"
else
    echo "  ✗ Doc link hygiene"
    DOC_FAILURES=$((DOC_FAILURES + 1))
fi

# SOT summary drift
if python scripts/tidy/sot_summary_refresh.py --check; then
    echo "  ✓ SOT summary drift"
else
    echo "  ✗ SOT summary drift"
    DOC_FAILURES=$((DOC_FAILURES + 1))
fi

if [ $DOC_FAILURES -eq 0 ]; then
    echo "✓ Docs/SOT integrity: PASS"
else
    echo "✗ Docs/SOT integrity: FAIL ($DOC_FAILURES checks failed)"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 5. Security normalization + diff gate (fixture validation)
echo "==> [5/5] Security tooling validation..."
SECURITY_FAILURES=0

# Normalize Trivy fixture
if python scripts/security/normalize_sarif.py \
   tests/fixtures/security/trivy-sample.sarif \
   --tool trivy > /dev/null; then
    echo "  ✓ SARIF normalization (Trivy)"
else
    echo "  ✗ SARIF normalization (Trivy)"
    SECURITY_FAILURES=$((SECURITY_FAILURES + 1))
fi

# Normalize CodeQL fixture
if python scripts/security/normalize_sarif.py \
   tests/fixtures/security/codeql-sample.sarif \
   --tool codeql > /dev/null; then
    echo "  ✓ SARIF normalization (CodeQL)"
else
    echo "  ✗ SARIF normalization (CodeQL)"
    SECURITY_FAILURES=$((SECURITY_FAILURES + 1))
fi

# Run security contract tests
if PYTHONPATH=src pytest tests/security/ -v --maxfail=3; then
    echo "  ✓ Security contract tests"
else
    echo "  ✗ Security contract tests"
    SECURITY_FAILURES=$((SECURITY_FAILURES + 1))
fi

if [ $SECURITY_FAILURES -eq 0 ]; then
    echo "✓ Security tooling: PASS"
else
    echo "✗ Security tooling: FAIL ($SECURITY_FAILURES checks failed)"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# Summary
echo "=========================================="
if [ $FAILURES -eq 0 ]; then
    echo "✓ ALL CHECKS PASSED (ready to push)"
    echo "=========================================="
    exit 0
else
    echo "✗ $FAILURES CHECK(S) FAILED (fix before push)"
    echo "=========================================="
    exit 1
fi
