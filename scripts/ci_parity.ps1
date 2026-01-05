#
# Local CI Parity Script (PowerShell)
#
# Runs the same must-pass checks as CI to reduce "works locally but not in CI" churn.
# Exit code 0 = all checks pass (green), non-zero = failures detected (red).
#
# Usage:
#   powershell -File scripts/ci_parity.ps1
#   .\scripts\ci_parity.ps1  # (if in scripts/ directory)
#
# Checks:
#   1. Ruff linting (src/ tests/)
#   2. Black formatting (src/ tests/)
#   3. Core tests subset (excludes research/aspirational, max 5 failures)
#   4. Docs/SOT integrity (BUILD_HISTORY unique IDs, doc links, SOT drift)
#   5. Security normalization + diff gate (fixture validation)

$ErrorActionPreference = "Continue"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Local CI Parity Check" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Track failures
$FAILURES = 0

# 1. Ruff linting
Write-Host "==> [1/5] Ruff linting..." -ForegroundColor Yellow
ruff check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Ruff: PASS" -ForegroundColor Green
} else {
    Write-Host "✗ Ruff: FAIL" -ForegroundColor Red
    $FAILURES++
}
Write-Host ""

# 2. Black formatting
Write-Host "==> [2/5] Black formatting..." -ForegroundColor Yellow
black --check src/ tests/
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Black: PASS" -ForegroundColor Green
} else {
    Write-Host "✗ Black: FAIL" -ForegroundColor Red
    $FAILURES++
}
Write-Host ""

# 3. Core tests (exclude research/aspirational, max 5 failures)
Write-Host "==> [3/5] Core tests (excluding research/aspirational)..." -ForegroundColor Yellow
$env:PYTHONPATH = "src"
$env:DATABASE_URL = "sqlite:///:memory:"
pytest tests/ -m "not research and not aspirational and not legacy_contract" -v --maxfail=5 -x
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Core tests: PASS" -ForegroundColor Green
} else {
    Write-Host "✗ Core tests: FAIL" -ForegroundColor Red
    $FAILURES++
}
Write-Host ""

# 4. Docs/SOT integrity checks
Write-Host "==> [4/5] Docs/SOT integrity..." -ForegroundColor Yellow
$DOC_FAILURES = 0

# BUILD_HISTORY unique IDs
python -c "from tests.docs.test_build_history_unique_build_ids import test_build_history_has_unique_build_ids; test_build_history_has_unique_build_ids()"
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ BUILD_HISTORY unique IDs" -ForegroundColor Green
} else {
    Write-Host "  ✗ BUILD_HISTORY unique IDs" -ForegroundColor Red
    $DOC_FAILURES++
}

# Doc link hygiene
python scripts/check_doc_links.py
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Doc link hygiene" -ForegroundColor Green
} else {
    Write-Host "  ✗ Doc link hygiene" -ForegroundColor Red
    $DOC_FAILURES++
}

# SOT summary drift
python scripts/tidy/sot_summary_refresh.py --check
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ SOT summary drift" -ForegroundColor Green
} else {
    Write-Host "  ✗ SOT summary drift" -ForegroundColor Red
    $DOC_FAILURES++
}

if ($DOC_FAILURES -eq 0) {
    Write-Host "✓ Docs/SOT integrity: PASS" -ForegroundColor Green
} else {
    Write-Host "✗ Docs/SOT integrity: FAIL ($DOC_FAILURES checks failed)" -ForegroundColor Red
    $FAILURES++
}
Write-Host ""

# 5. Security normalization + diff gate (fixture validation)
Write-Host "==> [5/5] Security tooling validation..." -ForegroundColor Yellow
$SECURITY_FAILURES = 0

# Normalize Trivy fixture
python scripts/security/normalize_sarif.py tests/fixtures/security/trivy-sample.sarif --tool trivy | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ SARIF normalization (Trivy)" -ForegroundColor Green
} else {
    Write-Host "  ✗ SARIF normalization (Trivy)" -ForegroundColor Red
    $SECURITY_FAILURES++
}

# Normalize CodeQL fixture
python scripts/security/normalize_sarif.py tests/fixtures/security/codeql-sample.sarif --tool codeql | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ SARIF normalization (CodeQL)" -ForegroundColor Green
} else {
    Write-Host "  ✗ SARIF normalization (CodeQL)" -ForegroundColor Red
    $SECURITY_FAILURES++
}

# Run security contract tests
$env:PYTHONPATH = "src"
pytest tests/security/ -v --maxfail=3
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Security contract tests" -ForegroundColor Green
} else {
    Write-Host "  ✗ Security contract tests" -ForegroundColor Red
    $SECURITY_FAILURES++
}

if ($SECURITY_FAILURES -eq 0) {
    Write-Host "✓ Security tooling: PASS" -ForegroundColor Green
} else {
    Write-Host "✗ Security tooling: FAIL ($SECURITY_FAILURES checks failed)" -ForegroundColor Red
    $FAILURES++
}
Write-Host ""

# Summary
Write-Host "==========================================" -ForegroundColor Cyan
if ($FAILURES -eq 0) {
    Write-Host "✓ ALL CHECKS PASSED (ready to push)" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "✗ $FAILURES CHECK(S) FAILED (fix before push)" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Cyan
    exit 1
}
