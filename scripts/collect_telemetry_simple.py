"""
Simple Telemetry Collection Script

Runs the test_token_telemetry.py script multiple times with varying
estimated token values to collect diverse [TokenEstimation] telemetry data.

This is a simpler approach than creating full autonomous runs - we just
vary the _estimated_output_tokens parameter to gather telemetry samples.

Usage:
    python scripts/collect_telemetry_simple.py
"""

import os
import sys
import logging
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set up logging to see telemetry
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from autopack.anthropic_clients import AnthropicBuilderClient

# Test scenarios. We intentionally do NOT inject a manual token estimate:
# the goal is to collect telemetry for the real TokenEstimator.
TEST_SCENARIOS = [
    {
        "name": "small-util",
        "goal": "Create a simple string utility function that capitalizes first letter of each word",
        "deliverables": ["src/utils/string_helper.py"],
        "complexity": "low",
    },
    {
        "name": "medium-util",
        "goal": "Create a data validator with email and phone number validation",
        "deliverables": ["src/utils/validator.py"],
        "complexity": "medium",
    },
    {
        "name": "config-parser",
        "goal": "Create a JSON config parser with schema validation and error handling",
        "deliverables": ["src/utils/config_parser.py"],
        "complexity": "medium",
    },
    {
        "name": "multi-file",
        "goal": "Create a cache module with tests - in-memory cache with TTL support",
        "deliverables": ["src/utils/cache.py", "tests/test_cache.py"],
        "complexity": "medium",
    },
    {
        "name": "simple-test",
        "goal": "Create a test fixture helper that generates sample user data",
        "deliverables": ["tests/fixtures/user_data.py"],
        "complexity": "low",
    },
]


def run_telemetry_test(api_key: str, scenario: dict, run_num: int, total: int):
    """Run a single telemetry collection test.

    Args:
        api_key: Anthropic API key
        scenario: Test scenario configuration
        run_num: Current run number
        total: Total number of runs
    """
    print(f"\n{'='*70}")
    print(f"[{run_num}/{total}] {scenario['name']}")
    print(f"Complexity: {scenario['complexity']}")
    print(f"{'='*70}")

    client = AnthropicBuilderClient(api_key=api_key)

    phase_spec = {
        "phase_id": f"telemetry-test-{run_num}",
        "goal": scenario["goal"],
        "deliverables": scenario["deliverables"],
        "scope": {"paths": ["src/utils/", "tests/"], "read_only_context": []},
        "complexity": scenario["complexity"],
    }

    file_context = {"existing_files": {}}

    try:
        result = client.execute_phase(phase_spec=phase_spec, file_context=file_context)

        print(f"✓ Completed - success={result.success}, tokens={result.tokens_used}")

        # Brief delay between requests
        time.sleep(2)

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        print("Set it with: export ANTHROPIC_API_KEY=your_key_here")
        return 1

    print(f"\n{'='*70}")
    print("TOKEN ESTIMATION TELEMETRY COLLECTION")
    print(f"{'='*70}")
    print(f"Running {len(TEST_SCENARIOS)} test scenarios")
    print("Objective: Collect [TokenEstimation] telemetry for BUILD-129 validation")
    print("Target: <30% mean error rate")
    print(f"{'='*70}\n")

    results = []
    for i, scenario in enumerate(TEST_SCENARIOS, 1):
        success = run_telemetry_test(api_key, scenario, i, len(TEST_SCENARIOS))
        results.append(success)

    # Summary
    print(f"\n{'='*70}")
    print("COLLECTION SUMMARY")
    print(f"{'='*70}")
    print(f"Total scenarios: {len(TEST_SCENARIOS)}")
    print(f"Successful: {sum(results)}")
    print(f"Failed: {len(results) - sum(results)}")
    print("\nTelemetry data logged to backend.log and console above")
    print("\nNext steps:")
    print(
        "1. Run: python scripts/analyze_token_telemetry.py --output reports/baseline_telemetry.md"
    )
    print("2. Review the baseline error rate")
    print("3. Tune TokenEstimator coefficients if error rate >30%")
    print(f"{'='*70}\n")

    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
