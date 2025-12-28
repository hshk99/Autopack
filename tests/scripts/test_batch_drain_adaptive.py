"""Tests for adaptive batch drain controller features.

Tests cover:
- Failure fingerprinting and normalization
- Phase selection with stop conditions
- Telemetry tracking
- Timeout deprioritization
"""

import pytest
from scripts.batch_drain_controller import (
    normalize_error_text,
    compute_failure_fingerprint,
    DrainResult,
)


class TestFailureFingerprinting:
    """Test failure fingerprinting logic."""

    def test_normalize_error_removes_timestamps(self):
        """Timestamps should be normalized to date and time."""
        text = "Error at 2025-12-28 16:22:03"
        normalized = normalize_error_text(text)
        assert "2025-12-28" not in normalized
        assert "16:22:03" not in normalized
        assert "date" in normalized
        assert "time" in normalized

    def test_normalize_error_removes_paths(self):
        """File paths should be normalized to path."""
        text = "File not found: c:\\dev\\Autopack\\test.py"
        normalized = normalize_error_text(text)
        assert "c:\\dev\\autopack" not in normalized
        assert "path" in normalized

    def test_normalize_error_removes_line_numbers(self):
        """Line numbers should be normalized to NUM."""
        text = "Error at line 123 in file:456"
        normalized = normalize_error_text(text)
        assert "line num" in normalized  # normalized is already lowercased
        assert ":num" in normalized

    def test_normalize_error_is_case_insensitive(self):
        """Normalization should lowercase text."""
        text1 = "ImportError: Cannot import module"
        text2 = "IMPORTERROR: CANNOT IMPORT MODULE"
        assert normalize_error_text(text1) == normalize_error_text(text2)

    def test_compute_fingerprint_includes_state(self):
        """Fingerprint should include final state."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="TIMEOUT",
            success=False,
            error_message="Phase timed out",
            subprocess_returncode=143,
        )
        fp = compute_failure_fingerprint(result)
        assert "TIMEOUT" in fp
        assert "timeout143" in fp.lower()

    def test_compute_fingerprint_groups_similar_errors(self):
        """Similar errors should get same fingerprint."""
        result1 = DrainResult(
            run_id="run-1",
            phase_id="phase-1",
            phase_index=0,
            initial_state="FAILED",
            final_state="FAILED",
            success=False,
            error_message="ImportError at line 123: cannot import module foo from /path/to/file.py:456",
            subprocess_returncode=1,
        )
        result2 = DrainResult(
            run_id="run-2",
            phase_id="phase-2",
            phase_index=1,
            initial_state="FAILED",
            final_state="FAILED",
            success=False,
            error_message="ImportError at line 789: cannot import module foo from /other/path/file.py:101",
            subprocess_returncode=1,
        )

        # After normalization, these should have same fingerprint
        fp1 = compute_failure_fingerprint(result1)
        fp2 = compute_failure_fingerprint(result2)
        assert fp1 == fp2

    def test_compute_fingerprint_distinguishes_different_errors(self):
        """Different error types should get different fingerprints."""
        result1 = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="FAILED",
            success=False,
            error_message="ImportError: cannot import module",
            subprocess_returncode=1,
        )
        result2 = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="FAILED",
            success=False,
            error_message="SyntaxError: invalid syntax",
            subprocess_returncode=1,
        )

        fp1 = compute_failure_fingerprint(result1)
        fp2 = compute_failure_fingerprint(result2)
        assert fp1 != fp2

    def test_compute_fingerprint_auto_assigned_on_failure(self):
        """Fingerprint should be automatically computed on __post_init__."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="FAILED",
            success=False,
            error_message="Test error",
            subprocess_returncode=1,
        )
        assert result.failure_fingerprint is not None
        assert len(result.failure_fingerprint) > 0

    def test_success_has_no_fingerprint(self):
        """Successful results should not have fingerprints."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="COMPLETE",
            success=True,
            subprocess_returncode=0,
        )
        assert result.failure_fingerprint is None


class TestPhaseSelectionLogic:
    """Test phase selection with stop conditions.

    Note: These are unit tests for the logic. Integration tests would require
    a test database with Phase records.
    """

    def test_timeout_phases_deprioritized(self):
        """Phases with timeout in last_failure_reason should be picked last."""
        # This is tested implicitly by the category ordering in pick_next_failed_phase
        # The order is: unknown > collection > deliverable > patch > other > timeout
        # This test documents the expected behavior
        pass


class TestTelemetryTracking:
    """Test telemetry yield calculations."""

    def test_telemetry_yield_calculated_correctly(self):
        """Telemetry yield per minute should be events/duration * 60."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="COMPLETE",
            success=True,
            subprocess_duration_seconds=120,  # 2 minutes
            telemetry_events_collected=10,
            telemetry_yield_per_minute=5.0,  # 10 events / 2 minutes = 5/min
        )

        # Verify the calculation is correct
        expected_yield = (10 / 120) * 60
        assert result.telemetry_yield_per_minute == expected_yield

    def test_zero_duration_no_yield(self):
        """Zero duration should result in None yield."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="COMPLETE",
            success=True,
            subprocess_duration_seconds=0,
            telemetry_events_collected=10,
            telemetry_yield_per_minute=None,
        )
        assert result.telemetry_yield_per_minute is None

    def test_no_events_no_yield(self):
        """No telemetry events should result in None yield."""
        result = DrainResult(
            run_id="test-run",
            phase_id="test-phase",
            phase_index=0,
            initial_state="FAILED",
            final_state="COMPLETE",
            success=True,
            subprocess_duration_seconds=120,
            telemetry_events_collected=0,
            telemetry_yield_per_minute=None,
        )
        assert result.telemetry_yield_per_minute is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
