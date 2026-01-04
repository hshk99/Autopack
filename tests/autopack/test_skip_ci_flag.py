"""
Test AUTOPACK_SKIP_CI=1 flag behavior.

Verifies that setting AUTOPACK_SKIP_CI=1 causes _run_ci_checks to return None
for telemetry runs, preventing PhaseFinalizer from running collection error detection.

Also verifies that the guardrail prevents CI skip for non-telemetry runs.
"""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_executor():
    """Create a mock executor with _run_ci_checks method and telemetry run_id."""
    # Import here to avoid import-time issues
    from autopack.autonomous_executor import AutonomousExecutor

    # Create a minimal mock executor with telemetry run_id
    executor = Mock(spec=AutonomousExecutor)
    executor.workspace = "/tmp/test"
    executor.run_id = "telemetry-collection-v4"

    # Bind the real _run_ci_checks method
    from autopack.autonomous_executor import AutonomousExecutor
    executor._run_ci_checks = AutonomousExecutor._run_ci_checks.__get__(executor, AutonomousExecutor)

    return executor


@pytest.fixture
def mock_executor_non_telemetry():
    """Create a mock executor with _run_ci_checks method and non-telemetry run_id."""
    # Import here to avoid import-time issues
    from autopack.autonomous_executor import AutonomousExecutor

    # Create a minimal mock executor with non-telemetry run_id
    executor = Mock(spec=AutonomousExecutor)
    executor.workspace = "/tmp/test"
    executor.run_id = "production-build-141"

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


def test_skip_ci_flag_non_telemetry_run_ignores_flag(mock_executor_non_telemetry, monkeypatch):
    """Test that AUTOPACK_SKIP_CI=1 is IGNORED for non-telemetry runs (guardrail)."""
    # Set the environment variable
    monkeypatch.setenv("AUTOPACK_SKIP_CI", "1")

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
    result = mock_executor_non_telemetry._run_ci_checks("test-phase", phase)

    # Should return skip result dict (because ci.skip=True), NOT None
    # The AUTOPACK_SKIP_CI=1 should be ignored because run_id is not telemetry
    assert result is not None, "Expected a result dict when ci.skip=True (flag should be ignored)"
    assert result.get("status") == "skipped", "Expected status='skipped'"


def test_skip_ci_flag_telemetry_run_honors_flag(mock_executor, monkeypatch):
    """Test that AUTOPACK_SKIP_CI=1 is HONORED for telemetry runs."""
    # Set the environment variable
    monkeypatch.setenv("AUTOPACK_SKIP_CI", "1")

    # Create a phase WITHOUT ci.skip (normal phase)
    phase = {
        "phase_id": "telemetry-p1-test",
        "scope": {}
    }

    # Call _run_ci_checks
    result = mock_executor._run_ci_checks("telemetry-p1-test", phase)

    # Should return None because run_id is telemetry and AUTOPACK_SKIP_CI=1
    assert result is None, "Expected None for telemetry run with AUTOPACK_SKIP_CI=1"
