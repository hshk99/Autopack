#!/usr/bin/env bash
# Regenerate requirements files from pyproject.toml
#
# Usage: bash scripts/regenerate_requirements.sh
#
# This script regenerates:
# - requirements.txt: Runtime-only dependencies (for containers)
# - requirements-dev.txt: Runtime + dev dependencies (for local development)
#
# WHY NO HASHES:
# - Cross-platform hash differences cause drift (Windows vs Linux)
# - Repo policy: requirements are Linux/WSL canonical and compared in CI via
#   scripts/check_dependency_sync.py (without hashes)
# - Tradeoff: simpler maintenance vs cryptographic verification
#
# CONTAINER SECURITY:
# - Containers use requirements.txt (runtime-only, no dev tools)
# - Reduces attack surface (no pytest, black, mypy, etc.)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "🔧 Regenerating requirements files from pyproject.toml..."

# Runtime-only (for containers)
echo "📦 Compiling requirements.txt (runtime-only)..."
pip-compile \
  --output-file=requirements.txt \
  pyproject.toml

# Dev (runtime + dev extras)
echo "🛠️  Compiling requirements-dev.txt (runtime + dev)..."
pip-compile \
  --extra=dev \
  --output-file=requirements-dev.txt \
  pyproject.toml

echo ""
echo "✅ Done! Files regenerated:"
echo "   - requirements.txt (runtime-only)"
echo "   - requirements-dev.txt (runtime + dev)"
echo ""
echo "Next steps:"
echo "  1. Review diff: git diff requirements*.txt"
echo "  2. Test locally: pip install -r requirements.txt"
echo "  3. Commit if changes are expected"
