"""
Tests for ROAD-A: Phase Outcome Telemetry

Validates invariant enforcement: no duplicates, stable IDs, bounded payloads.
"""

import pytest
from src.autopack.telemetry_outcomes import (
    PhaseOutcome,
    PhaseOutcomeRecorder,
    record_phase_outcome,
)


class TestPhaseOutcomeRecorder:
    """Test phase outcome recording with invariant enforcement."""

    def setup_method(self):
        """Create fresh recorder for each test."""
        self.recorder = PhaseOutcomeRecorder()

    def test_record_success(self):
        """Test recording successful phase completion."""
        event = self.recorder.record_success("phase-001")

        assert event["phase_id"] == "phase-001"
        assert event["outcome"] == "SUCCESS"
        assert event["stop_reason"] == "completed"
        assert "timestamp" in event

    def test_record_failure_with_reason(self):
        """Test recording phase failure with stop reason."""
        event = self.recorder.record_failure(
            "phase-002",
            stop_reason="builder_crash",
            decision_rationale="Builder encountered unrecoverable exception",
        )

        assert event["phase_id"] == "phase-002"
        assert event["outcome"] == "FAILED"
        assert event["stop_reason"] == "builder_crash"
        assert "decision_rationale" not in event  # Field name is stuck_decision_rationale
        assert event["stuck_decision_rationale"] == "Builder encountered unrecoverable exception"

    def test_record_stuck_with_rationale(self):
        """Test recording stuck phase with decision rationale."""
        rationale = "Phase attempted 5 times. All attempts failed with auth errors."
        event = self.recorder.record_stuck(
            "phase-003",
            decision_rationale=rationale,
            stop_reason="max_revisions",
        )

        assert event["phase_id"] == "phase-003"
        assert event["outcome"] == "STUCK"
        assert event["stop_reason"] == "max_revisions"
        assert event["stuck_decision_rationale"] == rationale

    def test_no_duplicate_events(self):
        """Test invariant: prevent duplicate events for same phase_id."""
        self.recorder.record_success("phase-dup")

        # Attempting to record same event should raise error
        with pytest.raises(ValueError, match="Duplicate event detected"):
            self.recorder.record_success("phase-dup")

    def test_stable_phase_ids(self):
        """Test invariant: phase_ids must be stable and bounded."""
        # Empty phase_id should fail
        with pytest.raises(ValueError, match="Invalid phase_id"):
            self.recorder.record_success("")

        # Very long phase_id should fail
        long_id = "x" * 300
        with pytest.raises(ValueError, match="Invalid phase_id"):
            self.recorder.record_success(long_id)

        # Valid phase_id should succeed
        event = self.recorder.record_success("valid-phase-001")
        assert event["phase_id"] == "valid-phase-001"

    def test_bounded_payload_sizes(self):
        """Test invariant: payload sizes must be bounded."""
        # Rationale > 10000 chars should fail
        huge_rationale = "x" * 10001
        with pytest.raises(ValueError, match="Rationale too large"):
            self.recorder.record_stuck(
                "phase-004",
                decision_rationale=huge_rationale,
            )

        # Stop reason > 256 chars should fail
        huge_reason = "x" * 257
        with pytest.raises(ValueError, match="Stop reason too large"):
            self.recorder.record_failure(
                "phase-005",
                stop_reason=huge_reason,
            )

        # Valid sizes should succeed
        event = self.recorder.record_stuck(
            "phase-006",
            decision_rationale="x" * 1000,  # Valid
            stop_reason="x" * 100,  # Valid
        )
        assert len(event["stuck_decision_rationale"]) == 1000

    def test_metadata_preservation(self):
        """Test that metadata is preserved in events."""
        metadata = {
            "duration_seconds": 45.2,
            "tokens_used": 12345,
            "attempt_number": 2,
        }
        event = self.recorder.record_failure(
            "phase-007",
            stop_reason="timeout",
            metadata=metadata,
        )

        assert event["metadata"] == metadata

    def test_global_recorder(self):
        """Test that global recorder works."""
        event = record_phase_outcome(
            "global-phase-001",
            PhaseOutcome.SUCCESS,
            metadata={"global": True},
        )

        assert event["phase_id"] == "global-phase-001"
        assert event["outcome"] == "SUCCESS"
        assert event["metadata"]["global"] is True


class TestPhaseOutcomeEnum:
    """Test PhaseOutcome enum values."""

    def test_outcome_values(self):
        """Test that all outcome types are defined."""
        assert PhaseOutcome.SUCCESS.value == "SUCCESS"
        assert PhaseOutcome.FAILED.value == "FAILED"
        assert PhaseOutcome.TIMEOUT.value == "TIMEOUT"
        assert PhaseOutcome.STUCK.value == "STUCK"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
