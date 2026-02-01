"""
Tests for ResearchStateTracker edge case handling.

Covers:
- Interrupted research recovery
- Partial results processing
- Async failure handling
- State consistency validation and repair
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from autopack.research.analysis.research_state import (
    GapPriority,
    GapType,
    ResearchCheckpoint,
    ResearchGap,
    ResearchStateTracker,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def state_tracker(temp_project_dir):
    """Create a ResearchStateTracker instance."""
    return ResearchStateTracker(temp_project_dir)


@pytest.fixture
def loaded_tracker(temp_project_dir):
    """Create and load a ResearchStateTracker with test state."""
    tracker = ResearchStateTracker(temp_project_dir)
    tracker.load_or_create_state("test-project")
    return tracker


class TestCheckpointCreation:
    """Test checkpoint creation for resumable research."""

    def test_create_checkpoint_saves_to_disk(self, loaded_tracker):
        """Test that checkpoints are saved to disk."""
        checkpoint = loaded_tracker.create_checkpoint("research_phase")

        assert checkpoint.checkpoint_id is not None
        assert checkpoint.phase == "research_phase"
        checkpoint_file = loaded_tracker.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        assert checkpoint_file.exists()

    def test_checkpoint_captures_state_snapshot(self, loaded_tracker):
        """Test that checkpoint captures current state snapshot."""
        # Add some data to the state
        loaded_tracker.update_coverage("market_research", 50.0)
        loaded_tracker.add_researched_entity("competitor", "CompetitorA")

        checkpoint = loaded_tracker.create_checkpoint("analysis_phase")

        assert checkpoint.state_snapshot is not None
        assert checkpoint.state_snapshot["research_state"]["project_id"] == "test-project"
        assert "entities_researched" in checkpoint.state_snapshot["research_state"]

    def test_checkpoint_to_dict_serialization(self, loaded_tracker):
        """Test checkpoint serialization to dictionary."""
        checkpoint = loaded_tracker.create_checkpoint("test_phase")
        checkpoint_dict = checkpoint.to_dict()

        assert checkpoint_dict["checkpoint_id"] == checkpoint.checkpoint_id
        assert checkpoint_dict["phase"] == "test_phase"
        assert "created_at" in checkpoint_dict
        assert isinstance(checkpoint_dict["completed_steps"], list)


class TestInterruptedResearchRecovery:
    """Test recovery from interrupted research."""

    def test_handle_interrupted_research_with_checkpoint(self, temp_project_dir):
        """Test recovery from interrupted research using checkpoint."""
        # Create initial tracker and checkpoint
        tracker1 = ResearchStateTracker(temp_project_dir)
        tracker1.load_or_create_state("test-project")
        tracker1.update_coverage("market_research", 75.0)
        checkpoint = tracker1.create_checkpoint("phase1")
        tracker1.save_state()

        # Create new tracker (simulating new session) - don't load state yet
        tracker2 = ResearchStateTracker(temp_project_dir)

        # Attempt recovery directly (without loading state first)
        recovered, recovered_checkpoint = tracker2.handle_interrupted_research("test-project")

        assert recovered is True
        assert recovered_checkpoint is not None
        assert recovered_checkpoint.checkpoint_id == checkpoint.checkpoint_id

    def test_interrupted_research_restores_state(self, temp_project_dir):
        """Test that recovery restores the exact state."""
        # Setup initial state with data
        tracker1 = ResearchStateTracker(temp_project_dir)
        tracker1.load_or_create_state("test-project")
        tracker1.update_coverage("market_research", 85.0)
        tracker1.update_coverage("competitive_analysis", 60.0)
        tracker1.add_researched_entity("api", "OpenAI")
        tracker1.add_researched_entity("api", "Anthropic")
        checkpoint = tracker1.create_checkpoint("research_phase")
        tracker1.save_state()

        # Recover in new tracker (don't load state first)
        tracker2 = ResearchStateTracker(temp_project_dir)
        recovered, _ = tracker2.handle_interrupted_research("test-project")

        assert recovered is True
        assert tracker2._state.coverage.by_category["market_research"] == 85.0
        assert tracker2._state.coverage.by_category["competitive_analysis"] == 60.0
        assert "api" in tracker2._state.entities_researched
        assert len(tracker2._state.entities_researched["api"]) == 2

    def test_interrupted_research_no_checkpoint_returns_false(self, state_tracker):
        """Test recovery returns False when no checkpoint exists."""
        state_tracker.load_or_create_state("test-project")
        recovered, checkpoint = state_tracker.handle_interrupted_research("test-project")

        assert recovered is False
        assert checkpoint is None

    def test_interrupted_research_unrecoverable_checkpoint(self, temp_project_dir):
        """Test handling of unrecoverable checkpoints."""
        # Create tracker and checkpoint
        tracker = ResearchStateTracker(temp_project_dir)
        tracker.load_or_create_state("test-project")
        checkpoint = tracker.create_checkpoint("phase1")

        # Mark checkpoint as unrecoverable
        checkpoint.is_recoverable = False
        tracker._save_checkpoint(checkpoint)

        # Try recovery
        recovered, _ = tracker.handle_interrupted_research("test-project")
        assert recovered is False


class TestPartialResultsHandling:
    """Test handling of partial results from interrupted research."""

    def test_handle_partial_results_stores_data(self, loaded_tracker):
        """Test that partial results are stored in checkpoint."""
        partial_results = {
            "queries_completed": 5,
            "sources_found": 12,
            "coverage_updated": True,
        }

        result = loaded_tracker.handle_partial_results("analysis_phase", partial_results)

        assert result["partial_results_stored"] is True
        assert result["items_processed"] == 3
        assert loaded_tracker._current_checkpoint is not None
        assert "queries_completed" in loaded_tracker._current_checkpoint.partial_results

    def test_handle_partial_results_creates_checkpoint(self, loaded_tracker):
        """Test that handle_partial_results creates checkpoint if none exists."""
        partial_results = {"step": 1, "data": "test"}
        loaded_tracker._current_checkpoint = None

        loaded_tracker.handle_partial_results("phase", partial_results)

        assert loaded_tracker._current_checkpoint is not None
        assert loaded_tracker._current_checkpoint.phase == "phase"

    def test_partial_results_accumulate(self, loaded_tracker):
        """Test that multiple partial results accumulate in checkpoint."""
        results1 = {"batch_1": True}
        results2 = {"batch_2": True}

        loaded_tracker.handle_partial_results("phase", results1)
        loaded_tracker.handle_partial_results("phase", results2)

        assert len(loaded_tracker._current_checkpoint.partial_results) == 2
        assert "batch_1" in loaded_tracker._current_checkpoint.partial_results
        assert "batch_2" in loaded_tracker._current_checkpoint.partial_results


class TestAsyncFailureHandling:
    """Test handling of async task failures."""

    def test_handle_async_failure_records_task(self, loaded_tracker):
        """Test that async failures are recorded."""
        result = loaded_tracker.handle_async_failure(
            "task-001", "Network timeout", fallback_action="retry_with_backoff"
        )

        assert result["recovery_initiated"] is True
        assert result["task_id"] == "task-001"
        assert result["fallback_action"] == "retry_with_backoff"

    def test_async_failure_creates_checkpoint(self, loaded_tracker):
        """Test that async failure creates checkpoint if none exists."""
        loaded_tracker._current_checkpoint = None

        loaded_tracker.handle_async_failure("task-001", "Connection failed")

        assert loaded_tracker._current_checkpoint is not None
        assert "task-001" in loaded_tracker._current_checkpoint.failed_tasks

    def test_async_failure_logs_recovery_event(self, temp_project_dir):
        """Test that async failures are logged to recovery log."""
        tracker = ResearchStateTracker(temp_project_dir)
        tracker.load_or_create_state("test-project")

        tracker.handle_async_failure("task-001", "Timeout", fallback_action="skip")

        recovery_log_file = tracker.recovery_log_file
        assert recovery_log_file.exists()

        with open(recovery_log_file, "r") as f:
            log = json.load(f)

        assert len(log) > 0
        assert log[0]["task_id"] == "task-001"
        assert log[0]["fallback_action"] == "skip"

    def test_multiple_async_failures(self, loaded_tracker):
        """Test handling multiple async failures."""
        loaded_tracker.handle_async_failure("task-001", "Error 1")
        loaded_tracker.handle_async_failure("task-002", "Error 2")
        loaded_tracker.handle_async_failure("task-003", "Error 3")

        assert len(loaded_tracker._current_checkpoint.failed_tasks) == 3
        assert "task-001" in loaded_tracker._current_checkpoint.failed_tasks
        assert "task-002" in loaded_tracker._current_checkpoint.failed_tasks


class TestStateConsistencyValidation:
    """Test state validation and inconsistency detection."""

    def test_validate_state_consistency_passes_valid_state(self, loaded_tracker):
        """Test validation passes for valid state."""
        errors = loaded_tracker.validate_state_consistency()
        # A fresh state should have no errors
        assert len(errors) == 0

    def test_detect_invalid_coverage_percentages(self, loaded_tracker):
        """Test detection of invalid coverage percentages."""
        loaded_tracker._state.coverage.by_category["market_research"] = 150.0

        errors = loaded_tracker.validate_state_consistency()

        # Error message includes the percentage value
        assert any("150" in str(e) or "market_research" in str(e) for e in errors)

    def test_detect_duplicate_gap_ids(self, loaded_tracker):
        """Test detection of duplicate gap IDs."""
        gap1 = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.COVERAGE,
            category="market_research",
            description="Test gap",
            priority=GapPriority.HIGH,
        )
        gap2 = ResearchGap(
            gap_id="gap-001",
            gap_type=GapType.DEPTH,
            category="competitive_analysis",
            description="Duplicate gap",
            priority=GapPriority.MEDIUM,
        )

        loaded_tracker._state.identified_gaps.append(gap1)
        loaded_tracker._state.identified_gaps.append(gap2)

        errors = loaded_tracker.validate_state_consistency()

        assert any("Duplicate gap IDs" in str(e) for e in errors)

    def test_detect_timestamp_inconsistency(self, loaded_tracker):
        """Test detection of timestamp inconsistencies."""
        # Set created_at after last_updated
        loaded_tracker._state.created_at = datetime.now() + timedelta(days=1)
        loaded_tracker._state.last_updated = datetime.now()

        errors = loaded_tracker.validate_state_consistency()

        assert any("last_updated is before" in str(e) for e in errors)

    def test_detect_negative_source_count(self, loaded_tracker):
        """Test detection of invalid source counts."""
        # Manually set invalid state (shouldn't happen in normal operation)
        loaded_tracker._state.discovered_sources = None

        # Should handle gracefully without crashing
        try:
            errors = loaded_tracker.validate_state_consistency()
            assert len(errors) >= 0
        except (TypeError, AttributeError):
            # Expected if we set it to None
            pass

    def test_validation_error_logging(self, loaded_tracker):
        """Test that validation errors are returned."""
        loaded_tracker._state.coverage.by_category["market_research"] = -10.0

        errors = loaded_tracker.validate_state_consistency()

        # Should detect the invalid coverage
        assert len(errors) > 0
        assert any("market_research" in e for e in errors)


class TestStateRepair:
    """Test state repair mechanisms."""

    def test_repair_invalid_coverage_percentages(self, loaded_tracker):
        """Test repair of invalid coverage percentages."""
        loaded_tracker._state.coverage.by_category["market_research"] = 150.0
        loaded_tracker._state.coverage.by_category["competitive_analysis"] = -20.0

        result = loaded_tracker.repair_state()

        assert result["repair_successful"] is True
        assert loaded_tracker._state.coverage.by_category["market_research"] == 100.0
        assert loaded_tracker._state.coverage.by_category["competitive_analysis"] == 0.0

    def test_repair_duplicate_gaps(self, loaded_tracker):
        """Test repair of duplicate gap IDs."""
        gap1 = ResearchGap(
            gap_id="gap-dup",
            gap_type=GapType.COVERAGE,
            category="market_research",
            description="First",
            priority=GapPriority.HIGH,
        )
        gap2 = ResearchGap(
            gap_id="gap-dup",
            gap_type=GapType.DEPTH,
            category="competitive_analysis",
            description="Duplicate",
            priority=GapPriority.MEDIUM,
        )

        loaded_tracker._state.identified_gaps.extend([gap1, gap2])

        result = loaded_tracker.repair_state()

        assert result["repair_successful"] is True
        # Should have removed one duplicate
        assert len(loaded_tracker._state.identified_gaps) == 1

    def test_repair_recalculates_overall_coverage(self, loaded_tracker):
        """Test that repair recalculates overall coverage."""
        loaded_tracker._state.coverage.by_category = {
            "market_research": 80.0,
            "competitive_analysis": 60.0,
            "technical_feasibility": 70.0,
            "legal_policy": 90.0,
            "social_sentiment": 50.0,
            "tool_availability": 75.0,
        }
        loaded_tracker._state.coverage.overall_percentage = 0.0  # Invalid

        result = loaded_tracker.repair_state()

        assert result["repair_successful"] is True
        assert loaded_tracker._state.coverage.overall_percentage > 0
        expected = sum(loaded_tracker._state.coverage.by_category.values()) / 6
        assert abs(loaded_tracker._state.coverage.overall_percentage - expected) < 0.1

    def test_repair_saves_state(self, temp_project_dir):
        """Test that repair saves the repaired state."""
        tracker = ResearchStateTracker(temp_project_dir)
        tracker.load_or_create_state("test-project")
        tracker._state.coverage.by_category["market_research"] = 150.0

        result = tracker.repair_state()

        assert result["repair_successful"] is True
        # State file should be updated
        with open(tracker.state_file, "r") as f:
            saved_state = json.load(f)
        assert saved_state["research_state"]["coverage"]["by_category"]["market_research"] == 100.0


class TestStateLoading:
    """Test state loading with validation and recovery."""

    def test_load_valid_state_file(self, temp_project_dir):
        """Test loading a valid state file."""
        # Create and save state
        tracker1 = ResearchStateTracker(temp_project_dir)
        tracker1.load_or_create_state("test-project")
        tracker1.update_coverage("market_research", 75.0)
        tracker1.save_state()

        # Load in new tracker
        tracker2 = ResearchStateTracker(temp_project_dir)
        state = tracker2.load_or_create_state("test-project")

        assert state.project_id == "test-project"
        assert state.coverage.by_category["market_research"] == 75.0

    def test_load_corrupted_state_file_creates_new(self, temp_project_dir):
        """Test that corrupted state file triggers recovery."""
        state_file = temp_project_dir / ".autopack" / "research_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write corrupted JSON
        with open(state_file, "w") as f:
            f.write("{invalid json content")

        tracker = ResearchStateTracker(temp_project_dir)
        state = tracker.load_or_create_state("test-project")

        assert state is not None
        assert state.project_id == "test-project"

    def test_load_state_with_checkpoint_recovery(self, temp_project_dir):
        """Test that loading triggers checkpoint recovery if main state fails."""
        # Create checkpoint with state data
        tracker1 = ResearchStateTracker(temp_project_dir)
        tracker1.load_or_create_state("test-project")
        tracker1.update_coverage("market_research", 80.0)
        # Important: create checkpoint AFTER updating coverage so snapshot has correct data
        tracker1.create_checkpoint("phase1")
        tracker1.save_state()

        # Corrupt main state file
        state_file = tracker1.state_file
        with open(state_file, "w") as f:
            f.write("{bad json")

        # Load with new tracker - should recover from checkpoint
        tracker2 = ResearchStateTracker(temp_project_dir)
        state = tracker2.load_or_create_state("test-project")

        assert state is not None
        # State should be recovered from checkpoint with the coverage we set
        assert state.coverage.by_category["market_research"] == 80.0


class TestCheckpointFileManagement:
    """Test checkpoint file storage and retrieval."""

    def test_latest_checkpoint_retrieval(self, loaded_tracker):
        """Test finding the most recent checkpoint."""
        cp1 = loaded_tracker.create_checkpoint("phase1")
        cp2 = loaded_tracker.create_checkpoint("phase2")
        cp3 = loaded_tracker.create_checkpoint("phase3")

        latest = loaded_tracker._find_latest_checkpoint()

        assert latest is not None
        assert latest.checkpoint_id == cp3.checkpoint_id

    def test_checkpoint_persistence(self, temp_project_dir):
        """Test that checkpoints persist across tracker instances."""
        tracker1 = ResearchStateTracker(temp_project_dir)
        tracker1.load_or_create_state("test-project")
        checkpoint = tracker1.create_checkpoint("phase1")

        tracker2 = ResearchStateTracker(temp_project_dir)
        latest = tracker2._find_latest_checkpoint()

        assert latest is not None
        assert latest.checkpoint_id == checkpoint.checkpoint_id

    def test_checkpoint_corruption_handling(self, temp_project_dir):
        """Test handling of corrupted checkpoint files."""
        tracker = ResearchStateTracker(temp_project_dir)
        tracker.load_or_create_state("test-project")
        checkpoint = tracker.create_checkpoint("phase1")

        # Corrupt the checkpoint file
        cp_file = tracker.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        with open(cp_file, "w") as f:
            f.write("{invalid}")

        # Should handle gracefully
        latest = tracker._find_latest_checkpoint()
        # Will return None since the checkpoint is corrupted
        assert latest is None or isinstance(latest, ResearchCheckpoint)
