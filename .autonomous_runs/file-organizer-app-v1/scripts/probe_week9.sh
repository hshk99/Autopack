#!/bin/bash
# Week 9 Autonomous Probe - Validate Alpha Release Deliverables

echo "=========================================="
echo "Week 9 Probe: Alpha Release Validation"
echo "=========================================="

BACKEND_DIR="../fileorganizer/backend"
FRONTEND_DIR="../fileorganizer/frontend"
ROOT_DIR=".."

# Check production configuration
echo "[Probe 1] Production configuration exists..."
if [ -f "$BACKEND_DIR/.env.production" ]; then
    echo "  [OK] .env.production file found"
else
    echo "  [ERROR] .env.production missing"
    exit 1
fi

# Check integration test suite
echo "[Probe 2] Integration test suite exists..."
if [ -f "$BACKEND_DIR/tests/test_integration.py" ]; then
    echo "  [OK] Integration test suite found"
else
    echo "  [ERROR] Integration test suite missing"
    exit 1
fi

# Check documentation files
echo "[Probe 3] Documentation files exist..."
if [ -f "$ROOT_DIR/README.md" ] && [ -f "$ROOT_DIR/docs/DEPLOYMENT_GUIDE.md" ]; then
    echo "  [OK] README.md and DEPLOYMENT_GUIDE.md found"
else
    echo "  [ERROR] Documentation files missing"
    exit 1
fi

# Check backend files are in place
echo "[Probe 4] Backend structure validation..."
if [ -d "$BACKEND_DIR/app" ] && [ -f "$BACKEND_DIR/main.py" ]; then
    echo "  [OK] Backend structure valid"
else
    echo "  [ERROR] Backend structure invalid"
    exit 1
fi

# Check frontend structure
echo "[Probe 5] Frontend structure validation..."
if [ -d "$FRONTEND_DIR/src" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
    echo "  [OK] Frontend structure valid"
else
    echo "  [ERROR] Frontend structure invalid"
    exit 1
fi

echo ""
echo "=========================================="
echo "[SUCCESS] All Week 9 deliverables validated"
echo "=========================================="
echo "  [OK] Production configuration (.env.production)"
echo "  [OK] Integration test suite"
echo "  [OK] Documentation (README, DEPLOYMENT_GUIDE)"
echo "  [OK] Backend structure"
echo "  [OK] Frontend structure"
echo ""
echo "FileOrganizer v1.0.0 Alpha Release Ready!"
