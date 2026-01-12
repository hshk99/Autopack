#!/bin/bash
# Compose Smoke Test Runner (Item 1.7)
#
# Usage:
#   ./scripts/smoke_test_compose.sh [--no-cleanup]
#
# Options:
#   --no-cleanup    Don't tear down compose stack after test (useful for debugging)
#
# Exit codes:
#   0 - All tests passed
#   1 - Tests failed or error occurred

set -e

# Configuration
CLEANUP=true
WAIT_TIMEOUT=120

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cleanup)
            CLEANUP=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--no-cleanup]"
            exit 1
            ;;
    esac
done

# Cleanup function
cleanup() {
    if [ "$CLEANUP" = true ]; then
        echo ""
        echo "🧹 Cleaning up compose stack..."
        docker compose down -v --remove-orphans 2>/dev/null || true
    else
        echo ""
        echo "⚠️  Skipping cleanup (--no-cleanup flag set)"
        echo "   To manually cleanup: docker compose down -v"
    fi
}

# Set trap for cleanup
trap cleanup EXIT

echo "🚀 Starting Autopack compose stack..."
echo ""

# Start compose stack
docker compose up -d --wait --wait-timeout "$WAIT_TIMEOUT"

echo ""
echo "⏳ Waiting for services to initialize..."
sleep 10

echo ""
echo "🔬 Running smoke tests..."
echo ""

# Run Python smoke test script
python3 scripts/smoke_test_compose.py

# Capture exit code
TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ All smoke tests passed!"
else
    echo ""
    echo "❌ Smoke tests failed!"
    echo ""
    echo "📋 Service logs (last 50 lines):"
    echo "================================"
    docker compose logs --tail=50
fi

exit $TEST_EXIT_CODE
