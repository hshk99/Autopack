"""Tests for executor crash recovery (IMP-REL-015).

Tests the crash recovery mechanism that allows the executor to detect
interrupted runs and resume from the last checkpointed state.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.executor.run_checkpoint import (
    ExecutorState,
    ExecutorStateCheckpoint,
)


class TestExecutorState:
    """Tests for ExecutorState dataclass."""

    def test_create_state(self):
        """Can create an executor state."""
        state = ExecutorState(run_id="test-run-001")
        assert state.run_id == "test-run-001"
        assert state.status == "in_progress"
        assert state.current_wave == 0
        assert state.completed_phases == []
        assert state.pending_phases == []
        assert state.in_progress_phase is None

    def test_state_with_phases(self):
        """Can create state with phase tracking."""
        state = ExecutorState(
            run_id="test-run-002",
            current_wave=2,
            completed_phases=["phase-1", "phase-2"],
            pending_phases=["phase-3", "phase-4"],
            in_progress_phase="phase-3",
            iteration_count=15,
            phases_executed=2,
            phases_failed=0,
        )
        assert state.current_wave == 2
        assert len(state.completed_phases) == 2
        assert len(state.pending_phases) == 2
        assert state.in_progress_phase == "phase-3"
        assert state.iteration_count == 15

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = ExecutorState(
            run_id="test-run-003",
            status="in_progress",
            current_wave=1,
            completed_phases=["phase-1"],
            pending_phases=["phase-2", "phase-3"],
            in_progress_phase="phase-2",
            iteration_count=5,
            phases_executed=1,
            phases_failed=0,
            timestamp="2026-01-30T10:00:00",
        )

        data = original.to_dict()
        restored = ExecutorState.from_dict(data)

        assert restored.run_id == original.run_id
        assert restored.status == original.status
        assert restored.current_wave == original.current_wave
        assert restored.completed_phases == original.completed_phases
        assert restored.pending_phases == original.pending_phases
        assert restored.in_progress_phase == original.in_progress_phase
        assert restored.iteration_count == original.iteration_count
        assert restored.timestamp == original.timestamp


class TestExecutorStateCheckpoint:
    """Tests for ExecutorStateCheckpoint class."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def checkpoint(self, temp_workspace):
        """Create a checkpoint manager with temp workspace."""
        return ExecutorStateCheckpoint(run_id="test-run", workspace=temp_workspace)

    def test_checkpoint_path(self, checkpoint, temp_workspace):
        """Checkpoint file path is correct."""
        expected = temp_workspace / ".autopack" / "executor_state.json"
        assert checkpoint.checkpoint_path == expected

    def test_save_state_creates_file(self, checkpoint):
        """save_state creates checkpoint file."""
        state = ExecutorState(run_id="test-run", iteration_count=5)

        result = checkpoint.save_state(state)

        assert result is True
        assert checkpoint.checkpoint_path.exists()

    def test_save_state_content(self, checkpoint):
        """save_state writes correct content."""
        state = ExecutorState(
            run_id="test-run",
            current_wave=2,
            completed_phases=["p1", "p2"],
            in_progress_phase="p3",
        )

        checkpoint.save_state(state)

        saved_data = json.loads(checkpoint.checkpoint_path.read_text())
        assert saved_data["run_id"] == "test-run"
        assert saved_data["current_wave"] == 2
        assert saved_data["completed_phases"] == ["p1", "p2"]
        assert saved_data["in_progress_phase"] == "p3"
        assert saved_data["status"] == "in_progress"

    def test_recover_interrupted_run_no_file(self, checkpoint):
        """recover_interrupted_run returns None when no checkpoint file."""
        result = checkpoint.recover_interrupted_run()
        assert result is None

    def test_recover_interrupted_run_completed(self, checkpoint):
        """recover_interrupted_run returns None for completed runs."""
        # Create a completed checkpoint
        checkpoint.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.checkpoint_path.write_text(
            json.dumps(
                {
                    "run_id": "test-run",
                    "status": "completed",
                    "current_wave": 3,
                    "completed_phases": ["p1", "p2", "p3"],
                    "pending_phases": [],
                    "in_progress_phase": None,
                    "iteration_count": 20,
                    "phases_executed": 3,
                    "phases_failed": 0,
                    "timestamp": "2026-01-30T10:00:00",
                }
            )
        )

        result = checkpoint.recover_interrupted_run()
        assert result is None

    def test_recover_interrupted_run_in_progress(self, checkpoint):
        """recover_interrupted_run returns state for interrupted runs."""
        # Create an in-progress checkpoint (simulating crash)
        checkpoint.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.checkpoint_path.write_text(
            json.dumps(
                {
                    "run_id": "test-run",
                    "status": "in_progress",
                    "current_wave": 2,
                    "completed_phases": ["p1", "p2"],
                    "pending_phases": ["p3", "p4"],
                    "in_progress_phase": "p3",
                    "iteration_count": 10,
                    "phases_executed": 2,
                    "phases_failed": 0,
                    "timestamp": "2026-01-30T10:00:00",
                }
            )
        )

        result = checkpoint.recover_interrupted_run()

        assert result is not None
        assert result.run_id == "test-run"
        assert result.status == "in_progress"
        assert result.current_wave == 2
        assert result.completed_phases == ["p1", "p2"]
        assert result.in_progress_phase == "p3"

    def test_recover_interrupted_run_different_run_id(self, checkpoint):
        """recover_interrupted_run returns None for different run ID."""
        # Create checkpoint for different run
        checkpoint.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.checkpoint_path.write_text(
            json.dumps(
                {
                    "run_id": "different-run",
                    "status": "in_progress",
                    "current_wave": 1,
                    "completed_phases": [],
                    "pending_phases": [],
                    "in_progress_phase": None,
                    "iteration_count": 1,
                    "phases_executed": 0,
                    "phases_failed": 0,
                    "timestamp": "2026-01-30T10:00:00",
                }
            )
        )

        result = checkpoint.recover_interrupted_run()
        assert result is None

    def test_mark_completed(self, checkpoint):
        """mark_completed updates status to completed."""
        # First save an in-progress state
        state = ExecutorState(run_id="test-run", iteration_count=10)
        checkpoint.save_state(state)

        # Now mark as completed
        result = checkpoint.mark_completed()

        assert result is True
        saved_data = json.loads(checkpoint.checkpoint_path.read_text())
        assert saved_data["status"] == "completed"

    def test_mark_completed_no_file(self, checkpoint):
        """mark_completed returns True when no file exists."""
        result = checkpoint.mark_completed()
        assert result is True

    def test_mark_completed_different_run(self, checkpoint):
        """mark_completed doesn't modify checkpoints for different runs."""
        # Create checkpoint for different run
        checkpoint.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.checkpoint_path.write_text(
            json.dumps(
                {
                    "run_id": "different-run",
                    "status": "in_progress",
                    "current_wave": 1,
                    "completed_phases": [],
                    "pending_phases": [],
                    "in_progress_phase": None,
                    "iteration_count": 1,
                    "phases_executed": 0,
                    "phases_failed": 0,
                    "timestamp": "2026-01-30T10:00:00",
                }
            )
        )

        result = checkpoint.mark_completed()

        assert result is True
        # Status should remain in_progress since it's a different run
        saved_data = json.loads(checkpoint.checkpoint_path.read_text())
        assert saved_data["status"] == "in_progress"

    def test_clear_checkpoint(self, checkpoint):
        """clear_checkpoint removes checkpoint file."""
        # First save a state
        state = ExecutorState(run_id="test-run")
        checkpoint.save_state(state)
        assert checkpoint.checkpoint_path.exists()

        # Now clear it
        result = checkpoint.clear_checkpoint()

        assert result is True
        assert not checkpoint.checkpoint_path.exists()

    def test_clear_checkpoint_no_file(self, checkpoint):
        """clear_checkpoint returns True when no file exists."""
        result = checkpoint.clear_checkpoint()
        assert result is True

    def test_corrupted_checkpoint_file(self, checkpoint):
        """recover_interrupted_run handles corrupted checkpoint gracefully."""
        checkpoint.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.checkpoint_path.write_text("not valid json {{{")

        result = checkpoint.recover_interrupted_run()
        assert result is None


class TestCrashRecoveryIntegration:
    """Integration tests for crash recovery flow."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_full_recovery_cycle(self, temp_workspace):
        """Test complete save -> crash -> recover -> complete cycle."""
        run_id = "integration-test-run"

        # Phase 1: Executor starts and saves checkpoint
        checkpoint1 = ExecutorStateCheckpoint(run_id=run_id, workspace=temp_workspace)
        state1 = ExecutorState(
            run_id=run_id,
            current_wave=1,
            completed_phases=["phase-1"],
            pending_phases=["phase-2", "phase-3"],
            in_progress_phase="phase-2",
            iteration_count=5,
        )
        checkpoint1.save_state(state1)

        # Phase 2: Simulate crash - new executor starts and recovers
        checkpoint2 = ExecutorStateCheckpoint(run_id=run_id, workspace=temp_workspace)
        recovered = checkpoint2.recover_interrupted_run()

        assert recovered is not None
        assert recovered.run_id == run_id
        assert recovered.completed_phases == ["phase-1"]
        assert recovered.in_progress_phase == "phase-2"

        # Phase 3: Executor continues and completes
        state2 = ExecutorState(
            run_id=run_id,
            current_wave=1,
            completed_phases=["phase-1", "phase-2", "phase-3"],
            pending_phases=[],
            in_progress_phase=None,
            iteration_count=15,
            phases_executed=3,
        )
        checkpoint2.save_state(state2)
        checkpoint2.mark_completed()

        # Phase 4: Verify no recovery needed on next start
        checkpoint3 = ExecutorStateCheckpoint(run_id=run_id, workspace=temp_workspace)
        should_be_none = checkpoint3.recover_interrupted_run()
        assert should_be_none is None

    def test_atomic_save(self, temp_workspace):
        """Test that saves are atomic (temp file then rename)."""
        run_id = "atomic-test-run"
        checkpoint = ExecutorStateCheckpoint(run_id=run_id, workspace=temp_workspace)

        # Save state
        state = ExecutorState(run_id=run_id, iteration_count=1)
        checkpoint.save_state(state)

        # Verify no temp file remains
        temp_path = checkpoint.checkpoint_path.with_suffix(".tmp")
        assert not temp_path.exists()
        assert checkpoint.checkpoint_path.exists()
