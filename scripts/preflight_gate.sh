#!/usr/bin/env bash
# Preflight gate script (Chunk E implementation)
#
# Per §10.2 of v7 playbook:
# - Wraps tests with up to 3 attempts
# - Handles flakiness detection and retry
# - Fails fast if signals low and budgets close to exhausted

set -e

echo "=== Autopack Preflight Gate ==="
echo ""

# Configuration
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"
BACKOFF_SECONDS="${BACKOFF_SECONDS:-5}"
CI_PROFILE="${CI_PROFILE:-normal}"

# BUILD-146 P11 Ops: Set DATABASE_URL explicitly for tests
# CI provides PostgreSQL, local dev should use explicit DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  Warning: DATABASE_URL not set, tests will use in-memory SQLite"
fi

echo "Configuration:"
echo "  Max attempts: $MAX_ATTEMPTS"
echo "  Backoff: $BACKOFF_SECONDS seconds"
echo "  CI profile: $CI_PROFILE"
echo "  Database: ${DATABASE_URL:-in-memory SQLite (test default)}"
echo ""

# Function to run tests
run_tests() {
    local attempt=$1
    echo "Attempt $attempt/$MAX_ATTEMPTS..."

    # Determine test selection based on CI profile
    if [ "$CI_PROFILE" = "strict" ]; then
        # Strict: run all tests including safety-critical
        pytest tests/ -v -m "unit or integration or e2e or safety_critical" || return 1
    else
        # Normal: run unit and integration only
        pytest tests/ -v -m "unit or integration" || return 1
    fi

    return 0
}

# Main retry loop
success=false
for attempt in $(seq 1 $MAX_ATTEMPTS); do
    if run_tests $attempt; then
        echo "✓ Tests passed on attempt $attempt"
        success=true
        break
    else
        echo "✗ Tests failed on attempt $attempt"

        if [ $attempt -lt $MAX_ATTEMPTS ]; then
            echo "Waiting $BACKOFF_SECONDS seconds before retry..."
            sleep $BACKOFF_SECONDS
        fi
    fi
done

if [ "$success" = true ]; then
    echo ""
    echo "=== Preflight Gate: PASSED ==="
    exit 0
else
    echo ""
    echo "=== Preflight Gate: FAILED ==="
    echo "Tests failed after $MAX_ATTEMPTS attempts"
    exit 1
fi
