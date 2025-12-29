"""
Test AUTOPACK_SKIP_CI=1 flag behavior.

Verifies that setting AUTOPACK_SKIP_CI=1 causes _run_ci_checks to return None,
preventing PhaseFinalizer from running collection error detection.
"""

import os
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_executor():
    """Create a mock executor with _run_ci_checks method."""
    # Import here to avoid import-time issues
    from autopack.autonomous_executor import AutonomousExecutor

    # Create a minimal mock executor
    executor = Mock(spec=AutonomousExecutor)
    executor.workspace = "/tmp/test"
    executor.run_id = "test-run"

    # Bind the real _run_ci_checks method
    from autopack.autonomous_executor import AutonomousExecutor
    executor._run_ci_checks = AutonomousExecutor._run_ci_checks.__get__(executor, AutonomousExecutor)

    return executor


def test_skip_ci_flag_returns_none(mock_executor, monkeypatch):
    """Test that AUTOPACK_SKIP_CI=1 causes _run_ci_checks to return None."""
    # Set the environment variable
    monkeypatch.setenv("AUTOPACK_SKIP_CI", "1")

    # Create a dummy phase
    phase = {
        "phase_id": "test-phase",
        "scope": {}
    }

    # Call _run_ci_checks
    result = mock_executor._run_ci_checks("test-phase", phase)

    # Should return None when AUTOPACK_SKIP_CI=1
    assert result is None, "Expected None when AUTOPACK_SKIP_CI=1, but got a result"


def test_skip_ci_flag_not_set(mock_executor, monkeypatch):
    """Test that _run_ci_checks runs normally when AUTOPACK_SKIP_CI is not set."""
    # Ensure AUTOPACK_SKIP_CI is not set
    monkeypatch.delenv("AUTOPACK_SKIP_CI", raising=False)

    # Create a phase with CI skip set in ci_spec (should still skip)
    phase = {
        "phase_id": "test-phase",
        "scope": {},
        "ci": {
            "skip": True,
            "reason": "Test skip"
        }
    }

    # Call _run_ci_checks
    result = mock_executor._run_ci_checks("test-phase", phase)

    # Should return a skip result dict (not None)
    assert result is not None, "Expected a result dict when ci.skip=True"
    assert result.get("status") == "skipped", "Expected status='skipped'"
    assert result.get("passed") is True, "Expected passed=True for skipped CI"


def test_skip_ci_flag_zero_string(mock_executor, monkeypatch):
    """Test that AUTOPACK_SKIP_CI=0 does NOT skip CI."""
    # Set to "0" (should not skip)
    monkeypatch.setenv("AUTOPACK_SKIP_CI", "0")

    # Create a phase with CI skip set in ci_spec
    phase = {
        "phase_id": "test-phase",
        "scope": {},
        "ci": {
            "skip": True,
            "reason": "Test skip"
        }
    }

    # Call _run_ci_checks
    result = mock_executor._run_ci_checks("test-phase", phase)

    # Should return skip result dict (because ci.skip=True), not None
    assert result is not None, "Expected a result dict when ci.skip=True"
    assert result.get("status") == "skipped", "Expected status='skipped'"
