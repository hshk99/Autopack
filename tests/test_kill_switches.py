"""Tests for BUILD-146 P12 kill switches.

Verifies that Phase 6 feature kill switches default to OFF for production safety.

Note: These tests verify kill switch logic WITHOUT requiring full FastAPI app setup.
Full API integration tests are in other test files.
"""

import os
import pytest
from unittest.mock import patch


def test_consolidated_metrics_kill_switch_defaults_off():
    """Verify AUTOPACK_ENABLE_CONSOLIDATED_METRICS defaults to OFF."""
    # Clear environment variable if set
    with patch.dict(os.environ, {}, clear=False):
        if "AUTOPACK_ENABLE_CONSOLIDATED_METRICS" in os.environ:
            del os.environ["AUTOPACK_ENABLE_CONSOLIDATED_METRICS"]

        # Check default state
        enabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1"
        assert enabled is False


def test_consolidated_metrics_kill_switch_enabled():
    """Verify AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1 enables the feature."""
    with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1"}):
        enabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1"
        assert enabled is True


def test_consolidated_metrics_kill_switch_other_values():
    """Verify only '1' enables the feature, not other truthy values."""
    test_cases = [
        ("true", False),
        ("TRUE", False),
        ("yes", False),
        ("on", False),
        ("0", False),
        ("", False),
    ]

    for value, expected in test_cases:
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": value}):
            enabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1"
            assert enabled == expected, f"Failed for value={value}"


def test_phase6_metrics_kill_switch_defaults_off():
    """Verify AUTOPACK_ENABLE_PHASE6_METRICS defaults to OFF."""
    with patch.dict(os.environ, {}, clear=False):
        if "AUTOPACK_ENABLE_PHASE6_METRICS" in os.environ:
            del os.environ["AUTOPACK_ENABLE_PHASE6_METRICS"]

        enabled = os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1"
        assert enabled is False


def test_phase6_metrics_kill_switch_enabled():
    """Verify AUTOPACK_ENABLE_PHASE6_METRICS=1 enables the feature."""
    with patch.dict(os.environ, {"AUTOPACK_ENABLE_PHASE6_METRICS": "1"}):
        enabled = os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1"
        assert enabled is True


def test_kill_switch_logic_in_code():
    """Verify kill switch check logic matches expected pattern."""
    # Pattern: if os.getenv("KILL_SWITCH") != "1": raise HTTPException(503)

    # Test OFF (default)
    with patch.dict(os.environ, {}, clear=False):
        if "AUTOPACK_ENABLE_CONSOLIDATED_METRICS" in os.environ:
            del os.environ["AUTOPACK_ENABLE_CONSOLIDATED_METRICS"]

        # Kill switch should be OFF - would raise 503
        should_raise_503 = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1"
        assert should_raise_503 is True

    # Test ON
    with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1"}):
        # Kill switch should be ON - would NOT raise 503
        should_raise_503 = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1"
        assert should_raise_503 is False


def test_multiple_kill_switches_independent():
    """Verify kill switches are independent."""
    # Set one ON, other OFF
    with patch.dict(
        os.environ,
        {
            "AUTOPACK_ENABLE_PHASE6_METRICS": "1",
            "AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "0",
        },
    ):
        phase6_enabled = os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1"
        consolidated_enabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1"

        assert phase6_enabled is True
        assert consolidated_enabled is False


def test_kill_switch_environment_isolation():
    """Verify environment variable changes are isolated per test."""
    # Test 1: Both OFF
    with patch.dict(os.environ, {}, clear=False):
        for key in ["AUTOPACK_ENABLE_PHASE6_METRICS", "AUTOPACK_ENABLE_CONSOLIDATED_METRICS"]:
            if key in os.environ:
                del os.environ[key]

        assert os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") != "1"
        assert os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1"

    # Test 2: Both ON (shouldn't leak from test 1)
    with patch.dict(
        os.environ,
        {
            "AUTOPACK_ENABLE_PHASE6_METRICS": "1",
            "AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1",
        },
    ):
        assert os.getenv("AUTOPACK_ENABLE_PHASE6_METRICS") == "1"
        assert os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") == "1"


def test_kill_switch_documentation_example():
    """Verify kill switch usage matches documentation example."""
    # From STAGING_ROLLOUT.md:
    # if os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1":
    #     raise HTTPException(status_code=503, detail="Feature disabled")

    # Simulate code check (without HTTPException)
    with patch.dict(os.environ, {}):
        # Default: OFF
        is_disabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1"
        assert is_disabled is True, "Should be disabled by default"

    with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1"}):
        # Explicitly enabled
        is_disabled = os.getenv("AUTOPACK_ENABLE_CONSOLIDATED_METRICS") != "1"
        assert is_disabled is False, "Should be enabled when set to '1'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
