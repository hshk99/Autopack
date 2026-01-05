# Regenerate requirements files from pyproject.toml (PowerShell version)
#
# Usage: powershell scripts/regenerate_requirements.ps1
#
# This script regenerates:
# - requirements.txt: Runtime-only dependencies (for containers)
# - requirements-dev.txt: Runtime + dev dependencies (for local development)

$ErrorActionPreference = "Stop"

$REPO_ROOT = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Push-Location $REPO_ROOT

Write-Host "🔧 Regenerating requirements files from pyproject.toml..." -ForegroundColor Cyan

# IMPORTANT:
# pip-compile resolves environment markers based on the current platform.
# If you run this on Windows, it will typically DROP non-Windows marker deps (e.g. python-magic)
# and may INLINE Windows-only deps without markers (e.g. pywin32), producing requirements files
# that break Linux CI and Docker builds.
#
# Repo policy: committed requirements*.txt must be generated on Linux (or WSL/CI runner).
Write-Host "⚠️  This script should be run under Linux/WSL for repo-committed requirements files." -ForegroundColor Yellow
Write-Host "   If you're on Windows PowerShell, use WSL and run: bash scripts/regenerate_requirements.sh" -ForegroundColor Yellow
throw "Refusing to regenerate requirements on Windows to avoid non-portable output."

# Runtime-only (for containers)
Write-Host "📦 Compiling requirements.txt (runtime-only)..." -ForegroundColor Yellow
pip-compile --output-file=requirements.txt pyproject.toml

# Dev (runtime + dev extras)
Write-Host "🛠️  Compiling requirements-dev.txt (runtime + dev)..." -ForegroundColor Yellow
pip-compile --extra=dev --output-file=requirements-dev.txt pyproject.toml

Write-Host ""
Write-Host "✅ Done! Files regenerated:" -ForegroundColor Green
Write-Host "   - requirements.txt (runtime-only)"
Write-Host "   - requirements-dev.txt (runtime + dev)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Review diff: git diff requirements*.txt"
Write-Host "  2. Test locally: pip install -r requirements.txt"
Write-Host "  3. Commit if changes are expected"

Pop-Location
