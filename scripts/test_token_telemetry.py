"""
Quick test script to verify token estimation telemetry works.

This script creates a minimal test run to trigger the token estimation
telemetry logging added in BUILD-129 Phase 1 validation.
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Set up logging to see telemetry
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from autopack.anthropic_clients import AnthropicBuilderClient

def test_telemetry():
    """Test that token estimation telemetry logs correctly."""

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set, skipping test")
        return

    # Create client
    client = AnthropicBuilderClient(api_key=api_key)

    # Create a minimal phase spec with token estimation
    phase_spec = {
        "phase_id": "test-token-telemetry",
        "goal": "Create a simple hello world function",
        "deliverables": ["src/hello.py"],
        "_estimated_output_tokens": 500,  # Estimated token count
        "scope": {
            "paths": ["src/"],
            "read_only_context": []
        },
        "complexity": "low"
    }

    # Minimal file context
    file_context = {
        "existing_files": {}
    }

    print("\n=== Testing Token Estimation Telemetry ===")
    print(f"Estimated output tokens: {phase_spec['_estimated_output_tokens']}")
    print("Running Builder...")

    try:
        # Execute phase
        result = client.execute_phase(
            phase_spec=phase_spec,
            file_context=file_context
        )

        print(f"\nResult: success={result.success}")
        print(f"Tokens used: {result.tokens_used}")
        print("\n=== Check logs above for [TokenEstimation] line ===")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_telemetry()
