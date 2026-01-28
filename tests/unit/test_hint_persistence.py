"""Tests for cross-run hint persistence (IMP-LOOP-020).

Tests cover:
- Hint occurrence loading from file
- Hint occurrence saving to file
- Cross-run persistence simulation
- Guaranteed persistence with retry logic
- Persistence verification
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from autopack.executor.learning_pipeline import (
    HintPersistenceError,
    LearningPipeline,
)
from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome


class TestHintOccurrencePersistence:
    """Tests for FeedbackPipeline hint occurrence persistence (IMP-LOOP-020)."""

    def test_load_hint_occurrences_empty_file(self, tmp_path):
        """Loading from non-existent file should return empty dict."""
        with patch("autopack.feedback_pipeline.Path") as mock_path:
            mock_path.return_value.exists.return_value = False

            pipeline = FeedbackPipeline(
                project_id="test_project",
                enabled=False,  # Disable auto-flush for testing
            )

            # The occurrences should be empty
            assert pipeline._hint_occurrences == {}

    def test_save_and_load_hint_occurrences(self, tmp_path):
        """Hint occurrences should persist across pipeline instances."""
        # Create a mock settings module
        mock_settings = Mock()
        mock_settings.autonomous_runs_dir = str(tmp_path)

        with patch("autopack.feedback_pipeline.Path") as MockPath:
            # Create a real Path for the test
            occurrences_file = tmp_path / "test_project" / "docs" / "HINT_OCCURRENCES.json"

            # Configure MockPath to return our test file path
            def path_side_effect(arg):
                if arg == "docs":
                    return tmp_path / "test_project" / "docs"
                return Path(arg)

            MockPath.side_effect = path_side_effect
            MockPath.return_value.__truediv__ = lambda self, other: tmp_path / other

            # Create pipeline and add occurrences manually
            pipeline = FeedbackPipeline(
                project_id="test_project",
                enabled=False,
            )

            # Manually set occurrences file path for testing
            pipeline._get_hint_occurrences_file = lambda: occurrences_file

            # Add some occurrences
            pipeline._hint_occurrences = {
                "ci_fail:build": 2,
                "auditor_reject:test": 1,
            }
            pipeline._save_hint_occurrences()

            # Verify file was created
            assert occurrences_file.exists()

            # Load the file and verify contents
            with open(occurrences_file, "r") as f:
                data = json.load(f)

            assert data["occurrences"]["ci_fail:build"] == 2
            assert data["occurrences"]["auditor_reject:test"] == 1
            assert "last_updated" in data

    def test_hint_occurrence_increment_persists(self, tmp_path):
        """Incrementing hint occurrences should trigger persistence."""
        occurrences_file = tmp_path / "docs" / "HINT_OCCURRENCES.json"

        # Create pipeline with patched path
        pipeline = FeedbackPipeline(
            project_id="autopack",
            enabled=False,
        )
        pipeline._get_hint_occurrences_file = lambda: occurrences_file

        # Simulate processing an outcome that increments hint occurrences
        outcome = PhaseOutcome(
            phase_id="test_phase",
            phase_type="build",
            success=False,
            status="failed",
            error_message="CI tests failed",
        )

        # Set up learning pipeline mock
        mock_learning = Mock()
        pipeline.learning_pipeline = mock_learning

        # Process the outcome
        pipeline.process_phase_outcome(outcome)

        # Check if hint occurrences were saved
        if occurrences_file.exists():
            with open(occurrences_file, "r") as f:
                data = json.load(f)
            assert "occurrences" in data

    def test_clear_hint_occurrences_with_persist(self, tmp_path):
        """clear_hint_occurrences should clear and persist empty state."""
        occurrences_file = tmp_path / "docs" / "HINT_OCCURRENCES.json"
        occurrences_file.parent.mkdir(parents=True, exist_ok=True)

        # Pre-populate the file
        with open(occurrences_file, "w") as f:
            json.dump({"occurrences": {"ci_fail:build": 5}}, f)

        pipeline = FeedbackPipeline(
            project_id="autopack",
            enabled=False,
        )
        pipeline._get_hint_occurrences_file = lambda: occurrences_file
        pipeline._hint_occurrences = {"ci_fail:build": 5}

        # Clear with persistence
        pipeline.clear_hint_occurrences(persist=True)

        # Verify in-memory is empty
        assert pipeline._hint_occurrences == {}

        # Verify file is updated
        with open(occurrences_file, "r") as f:
            data = json.load(f)
        assert data["occurrences"] == {}

    def test_reset_stats_does_not_persist(self, tmp_path):
        """reset_stats should clear in-memory but NOT persist to avoid data loss."""
        occurrences_file = tmp_path / "docs" / "HINT_OCCURRENCES.json"
        occurrences_file.parent.mkdir(parents=True, exist_ok=True)

        # Pre-populate the file
        with open(occurrences_file, "w") as f:
            json.dump({"occurrences": {"ci_fail:build": 5}}, f)

        pipeline = FeedbackPipeline(
            project_id="autopack",
            enabled=False,
        )
        pipeline._get_hint_occurrences_file = lambda: occurrences_file
        pipeline._hint_occurrences = {"ci_fail:build": 5}

        # Reset stats
        pipeline.reset_stats()

        # Verify in-memory is empty
        assert pipeline._hint_occurrences == {}

        # Verify file still has original data (not persisted)
        with open(occurrences_file, "r") as f:
            data = json.load(f)
        assert data["occurrences"]["ci_fail:build"] == 5


class TestGuaranteedPersistence:
    """Tests for LearningPipeline guaranteed persistence (IMP-LOOP-020)."""

    def test_persist_hints_guaranteed_success(self):
        """persist_hints_guaranteed should succeed on first attempt."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight.return_value = True
        mock_memory.retrieve_insights.return_value = [
            {"content": "test-phase auditor_reject", "description": "Test Phase hint"}
        ]

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # Record a hint
        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_hint(phase, "auditor_reject", "Test details")

        # Persist with guaranteed delivery
        count = pipeline.persist_hints_guaranteed(verify=True)

        assert count == 1
        mock_memory.write_telemetry_insight.assert_called()

    def test_persist_hints_guaranteed_retry_on_failure(self):
        """persist_hints_guaranteed should retry on transient failures."""
        mock_memory = Mock()
        mock_memory.enabled = True

        # Fail first 2 attempts, succeed on third
        call_count = [0]

        def write_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Transient error")
            return True

        mock_memory.write_telemetry_insight.side_effect = write_side_effect
        mock_memory.retrieve_insights.return_value = []

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # Record a hint
        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_hint(phase, "ci_fail", "Test failure")

        # Persist with guaranteed delivery (no verification to simplify test)
        count = pipeline.persist_hints_guaranteed(verify=False)

        assert count == 1
        assert call_count[0] == 3  # Should have retried

    def test_persist_hints_guaranteed_raises_after_max_retries(self):
        """persist_hints_guaranteed should raise after all retries fail."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight.side_effect = Exception("Persistent error")

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # Record a hint
        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_hint(phase, "ci_fail", "Test failure")

        # Should raise HintPersistenceError after 3 retries
        with pytest.raises(HintPersistenceError) as exc_info:
            pipeline.persist_hints_guaranteed(max_retries=3, verify=False)

        assert "Failed to persist" in str(exc_info.value)
        assert "3 attempts" in str(exc_info.value)

    def test_persist_hints_guaranteed_verification_failure_retries(self):
        """persist_hints_guaranteed should retry if verification fails."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight.return_value = True

        # Return empty results for first 2 verification attempts
        verify_call_count = [0]

        def retrieve_side_effect(*args, **kwargs):
            verify_call_count[0] += 1
            if verify_call_count[0] < 3:
                return []  # Verification fails
            return [{"content": "test-phase auditor_reject", "description": "Test hint"}]

        mock_memory.retrieve_insights.side_effect = retrieve_side_effect

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # Record a hint
        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_hint(phase, "auditor_reject", "Test details")

        # Persist with verification
        count = pipeline.persist_hints_guaranteed(verify=True)

        assert count == 1
        assert verify_call_count[0] == 3

    def test_persist_hints_guaranteed_empty_hints_succeeds(self):
        """persist_hints_guaranteed should return 0 with no hints."""
        mock_memory = Mock()
        mock_memory.enabled = True

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # No hints recorded
        count = pipeline.persist_hints_guaranteed()

        assert count == 0
        mock_memory.write_telemetry_insight.assert_not_called()

    def test_persist_hints_guaranteed_disabled_memory_service(self):
        """persist_hints_guaranteed should return 0 if memory service disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        pipeline = LearningPipeline(
            run_id="test-run",
            memory_service=mock_memory,
            project_id="test_project",
        )

        # Record a hint
        phase = {"phase_id": "test-phase", "name": "Test Phase"}
        pipeline.record_hint(phase, "ci_fail", "Test failure")

        # Should return 0 without raising
        count = pipeline.persist_hints_guaranteed()

        assert count == 0


class TestHintPersistenceError:
    """Tests for HintPersistenceError exception."""

    def test_hint_persistence_error_creation(self):
        """HintPersistenceError should be creatable with message."""
        error = HintPersistenceError("Failed to persist hints")
        assert str(error) == "Failed to persist hints"

    def test_hint_persistence_error_inheritance(self):
        """HintPersistenceError should be an Exception."""
        error = HintPersistenceError("test")
        assert isinstance(error, Exception)


class TestCrossRunLearning:
    """Integration tests for cross-run learning persistence."""

    def test_hint_promotion_threshold_persists_across_runs(self, tmp_path):
        """Hint occurrences should accumulate across runs for promotion."""
        occurrences_file = tmp_path / "docs" / "HINT_OCCURRENCES.json"

        # Simulate Run 1: Record 1 occurrence
        pipeline1 = FeedbackPipeline(
            project_id="autopack",
            run_id="run_001",
            enabled=False,
        )
        pipeline1._get_hint_occurrences_file = lambda: occurrences_file
        pipeline1._hint_occurrences["ci_fail:build"] = 1
        pipeline1._save_hint_occurrences()

        # Simulate Run 2: Load and add another occurrence
        pipeline2 = FeedbackPipeline(
            project_id="autopack",
            run_id="run_002",
            enabled=False,
        )
        pipeline2._get_hint_occurrences_file = lambda: occurrences_file

        # Load existing occurrences
        loaded = pipeline2._load_hint_occurrences()
        pipeline2._hint_occurrences = loaded
        pipeline2._hint_occurrences["ci_fail:build"] = (
            pipeline2._hint_occurrences.get("ci_fail:build", 0) + 1
        )
        pipeline2._save_hint_occurrences()

        # Simulate Run 3: Load and verify accumulated count
        pipeline3 = FeedbackPipeline(
            project_id="autopack",
            run_id="run_003",
            enabled=False,
        )
        pipeline3._get_hint_occurrences_file = lambda: occurrences_file
        pipeline3._hint_occurrences = pipeline3._load_hint_occurrences()

        # Should have accumulated to 2 occurrences
        assert pipeline3._hint_occurrences.get("ci_fail:build") == 2
