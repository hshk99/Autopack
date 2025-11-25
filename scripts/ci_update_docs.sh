#!/bin/bash
# CI Documentation Update Script
# Run this as part of CI flow to detect and document major structural changes

echo "========================================"
echo "CI Flow: Documentation Update"
echo "========================================"

# Run full structural analysis
echo ""
echo "[1/2] Analyzing structural changes..."
python scripts/update_docs.py --analyze

if [ $? -eq 1 ]; then
    echo ""
    echo "[2/2] Structural changes detected and documented"
    echo "✓ CHANGELOG.md updated with new modules/classes/APIs"
    echo "✓ README.md statistics updated"
    echo ""
    echo "Note: Review CHANGELOG.md before committing"
else
    echo ""
    echo "[2/2] No major structural changes detected"
    echo "✓ Documentation is up to date"
fi

echo ""
echo "========================================"
echo "Documentation update complete"
echo "========================================"
