"""Tests for executor state persistence (BUILD-041)."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autopack.executor.state_persistence import (
    AttemptRecord,
    ExecutorState,
    ExecutorStateManager,
    PhaseState,
    PhaseStatus,
)


class TestPhaseStatus:
    """Tests for PhaseStatus enum."""

    def test_all_statuses_exist(self):
        """All expected statuses exist."""
        assert PhaseStatus.PENDING
        assert PhaseStatus.IN_PROGRESS
        assert PhaseStatus.COMPLETED
        assert PhaseStatus.FAILED
        assert PhaseStatus.SKIPPED
        assert PhaseStatus.BLOCKED


class TestAttemptRecord:
    """Tests for AttemptRecord."""

    def test_create_attempt(self):
        """Can create an attempt record."""
        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id="test-attempt-0",
            attempt_number=0,
            started_at=now,
        )
        assert attempt.attempt_id == "test-attempt-0"
        assert attempt.attempt_number == 0
        assert attempt.status == PhaseStatus.IN_PROGRESS

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        now = datetime.now(timezone.utc)
        original = AttemptRecord(
            attempt_id="attempt-123",
            attempt_number=2,
            started_at=now,
            completed_at=now + timedelta(minutes=5),
            status=PhaseStatus.COMPLETED,
            error_message=None,
            side_effects_attempted=["effect-1", "effect-2"],
            idempotency_keys=["key-1"],
            checkpoint={"step": 5},
        )

        data = original.to_dict()
        restored = AttemptRecord.from_dict(data)

        assert restored.attempt_id == original.attempt_id
        assert restored.attempt_number == original.attempt_number
        assert restored.status == original.status
        assert restored.side_effects_attempted == original.side_effects_attempted
        assert restored.checkpoint == original.checkpoint


class TestPhaseState:
    """Tests for PhaseState."""

    def test_create_phase(self):
        """Can create a phase state."""
        phase = PhaseState(
            phase_id="phase-1",
            phase_number=0,
            name="Setup",
        )
        assert phase.phase_id == "phase-1"
        assert phase.status == PhaseStatus.PENDING
        assert phase.attempt_count == 0

    def test_can_retry_with_attempts_remaining(self):
        """can_retry returns True when attempts remain."""
        phase = PhaseState(
            phase_id="phase-1",
            phase_number=0,
            name="Test",
            max_attempts=3,
        )
        phase.attempts.append(
            AttemptRecord(
                attempt_id="a-0",
                attempt_number=0,
                started_at=datetime.now(timezone.utc),
                status=PhaseStatus.FAILED,
            )
        )
        assert phase.can_retry is True

    def test_can_retry_exhausted(self):
        """can_retry returns False when attempts exhausted."""
        phase = PhaseState(
            phase_id="phase-1",
            phase_number=0,
            name="Test",
            max_attempts=2,
        )
        for i in range(2):
            phase.attempts.append(
                AttemptRecord(
                    attempt_id=f"a-{i}",
                    attempt_number=i,
                    started_at=datetime.now(timezone.utc),
                    status=PhaseStatus.FAILED,
                )
            )
        assert phase.can_retry is False

    def test_can_retry_false_when_completed(self):
        """can_retry returns False when phase is completed."""
        phase = PhaseState(
            phase_id="phase-1",
            phase_number=0,
            name="Test",
            status=PhaseStatus.COMPLETED,
        )
        assert phase.can_retry is False

    def test_last_attempt(self):
        """last_attempt returns the most recent attempt."""
        phase = PhaseState(
            phase_id="phase-1",
            phase_number=0,
            name="Test",
        )
        assert phase.last_attempt is None

        phase.attempts.append(
            AttemptRecord(
                attempt_id="a-0",
                attempt_number=0,
                started_at=datetime.now(timezone.utc),
            )
        )
        phase.attempts.append(
            AttemptRecord(
                attempt_id="a-1",
                attempt_number=1,
                started_at=datetime.now(timezone.utc),
            )
        )
        assert phase.last_attempt.attempt_id == "a-1"

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = PhaseState(
            phase_id="phase-xyz",
            phase_number=2,
            name="Execute",
            status=PhaseStatus.IN_PROGRESS,
            max_attempts=5,
            dependencies=["phase-1"],
            side_effects_committed=["effect-1"],
        )

        data = original.to_dict()
        restored = PhaseState.from_dict(data)

        assert restored.phase_id == original.phase_id
        assert restored.name == original.name
        assert restored.status == original.status
        assert restored.dependencies == original.dependencies


class TestExecutorState:
    """Tests for ExecutorState."""

    def test_create_state(self):
        """Can create executor state."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-123",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
        )
        assert state.run_id == "run-123"
        assert state.status == "pending"
        assert state.is_complete is True  # No phases = complete

    def test_current_phase(self):
        """current_phase returns correct phase."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-1",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(phase_id="p-0", phase_number=0, name="Setup"),
                PhaseState(phase_id="p-1", phase_number=1, name="Execute"),
            ],
            current_phase_index=1,
        )
        assert state.current_phase.name == "Execute"

    def test_is_complete(self):
        """is_complete returns True when all phases done."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-1",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(
                    phase_id="p-0", phase_number=0, name="Setup", status=PhaseStatus.COMPLETED
                ),
                PhaseState(
                    phase_id="p-1", phase_number=1, name="Execute", status=PhaseStatus.SKIPPED
                ),
            ],
        )
        assert state.is_complete is True

    def test_is_complete_false(self):
        """is_complete returns False when phases remain."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-1",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(
                    phase_id="p-0", phase_number=0, name="Setup", status=PhaseStatus.COMPLETED
                ),
                PhaseState(
                    phase_id="p-1", phase_number=1, name="Execute", status=PhaseStatus.PENDING
                ),
            ],
        )
        assert state.is_complete is False

    def test_get_next_executable_phase(self):
        """get_next_executable_phase returns correct phase."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-1",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(
                    phase_id="p-0", phase_number=0, name="Setup", status=PhaseStatus.COMPLETED
                ),
                PhaseState(
                    phase_id="p-1", phase_number=1, name="Execute", status=PhaseStatus.PENDING
                ),
                PhaseState(
                    phase_id="p-2", phase_number=2, name="Cleanup", status=PhaseStatus.PENDING
                ),
            ],
        )
        next_phase = state.get_next_executable_phase()
        assert next_phase.phase_id == "p-1"

    def test_get_next_executable_phase_with_dependencies(self):
        """get_next_executable_phase respects dependencies."""
        now = datetime.now(timezone.utc)
        state = ExecutorState(
            run_id="run-1",
            project_id="proj-1",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(
                    phase_id="p-0", phase_number=0, name="Setup", status=PhaseStatus.PENDING
                ),
                PhaseState(
                    phase_id="p-1",
                    phase_number=1,
                    name="Execute",
                    status=PhaseStatus.PENDING,
                    dependencies=["p-0"],
                ),
            ],
        )
        # p-1 depends on p-0, so p-0 should be returned
        next_phase = state.get_next_executable_phase()
        assert next_phase.phase_id == "p-0"

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        now = datetime.now(timezone.utc)
        original = ExecutorState(
            run_id="run-abc",
            project_id="proj-xyz",
            created_at=now,
            updated_at=now,
            phases=[
                PhaseState(phase_id="p-0", phase_number=0, name="Test"),
            ],
            status="running",
            config_hash="abc123",
            metadata={"key": "value"},
        )

        data = original.to_dict()
        restored = ExecutorState.from_dict(data)

        assert restored.run_id == original.run_id
        assert restored.status == original.status
        assert restored.config_hash == original.config_hash
        assert restored.metadata == original.metadata


class TestExecutorStateManager:
    """Tests for ExecutorStateManager."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_storage):
        """Create manager with temp storage."""
        return ExecutorStateManager(storage_dir=temp_storage)

    def test_create_state(self, manager):
        """create_state creates and persists state."""
        state = manager.create_state(
            run_id="run-001",
            project_id="proj-1",
            phase_names=["Setup", "Execute", "Cleanup"],
        )

        assert state.run_id == "run-001"
        assert len(state.phases) == 3
        assert state.phases[0].name == "Setup"

    def test_load_state(self, manager):
        """load_state retrieves persisted state."""
        manager.create_state(
            run_id="run-002",
            project_id="proj-1",
            phase_names=["Test"],
        )

        loaded = manager.load_state("run-002")
        assert loaded is not None
        assert loaded.run_id == "run-002"

    def test_load_state_not_found(self, manager):
        """load_state returns None for missing state."""
        loaded = manager.load_state("nonexistent")
        assert loaded is None

    def test_start_phase(self, manager):
        """start_phase creates new attempt."""
        state = manager.create_state(
            run_id="run-003",
            project_id="proj-1",
            phase_names=["Phase1"],
        )

        attempt = manager.start_phase(state, state.phases[0].phase_id)

        assert attempt.attempt_number == 0
        assert state.phases[0].status == PhaseStatus.IN_PROGRESS
        assert len(state.phases[0].attempts) == 1

    def test_complete_phase_success(self, manager):
        """complete_phase marks phase as completed."""
        state = manager.create_state(
            run_id="run-004",
            project_id="proj-1",
            phase_names=["Phase1"],
        )
        phase_id = state.phases[0].phase_id
        manager.start_phase(state, phase_id)

        manager.complete_phase(state, phase_id, success=True)

        assert state.phases[0].status == PhaseStatus.COMPLETED
        assert state.phases[0].last_attempt.status == PhaseStatus.COMPLETED

    def test_complete_phase_failure_with_retry(self, manager):
        """complete_phase allows retry on failure."""
        state = manager.create_state(
            run_id="run-005",
            project_id="proj-1",
            phase_names=["Phase1"],
        )
        phase_id = state.phases[0].phase_id
        manager.start_phase(state, phase_id)

        manager.complete_phase(
            state,
            phase_id,
            success=False,
            error_message="Test error",
        )

        assert state.phases[0].status == PhaseStatus.PENDING  # Can retry
        assert state.phases[0].last_attempt.status == PhaseStatus.FAILED

    def test_save_checkpoint(self, manager):
        """save_checkpoint persists checkpoint data."""
        state = manager.create_state(
            run_id="run-006",
            project_id="proj-1",
            phase_names=["Phase1"],
        )
        phase_id = state.phases[0].phase_id
        manager.start_phase(state, phase_id)

        manager.save_checkpoint(state, phase_id, {"step": 5, "data": [1, 2, 3]})

        assert state.phases[0].current_checkpoint == {"step": 5, "data": [1, 2, 3]}

    def test_register_idempotency_key_new(self, manager):
        """register_idempotency_key returns True for new keys."""
        state = manager.create_state(
            run_id="run-007",
            project_id="proj-1",
            phase_names=["Phase1"],
        )
        phase_id = state.phases[0].phase_id
        manager.start_phase(state, phase_id)

        result = manager.register_idempotency_key(state, phase_id, "key-new")

        assert result is True
        assert "key-new" in state.phases[0].last_attempt.idempotency_keys

    def test_register_idempotency_key_duplicate(self, manager):
        """register_idempotency_key returns False for used keys."""
        state = manager.create_state(
            run_id="run-008",
            project_id="proj-1",
            phase_names=["Phase1"],
        )
        phase_id = state.phases[0].phase_id

        # First attempt with key
        manager.start_phase(state, phase_id)
        manager.register_idempotency_key(state, phase_id, "key-dup")
        manager.complete_phase(state, phase_id, success=False)

        # Second attempt - key should be rejected
        manager.start_phase(state, phase_id)
        result = manager.register_idempotency_key(state, phase_id, "key-dup")

        assert result is False

    def test_get_run_summary(self, manager):
        """get_run_summary returns summary info."""
        state = manager.create_state(
            run_id="run-009",
            project_id="proj-1",
            phase_names=["Setup", "Execute"],
        )
        state.phases[0].status = PhaseStatus.COMPLETED
        manager.save_state(state)

        summary = manager.get_run_summary("run-009")

        assert summary is not None
        assert summary["run_id"] == "run-009"
        assert len(summary["phases"]) == 2
        assert summary["phases"][0]["status"] == "completed"

    def test_list_runs(self, manager):
        """list_runs returns all run IDs."""
        manager.create_state("run-a", "proj-1", ["P1"])
        manager.create_state("run-b", "proj-1", ["P1"])
        manager.create_state("run-c", "proj-1", ["P1"])

        runs = manager.list_runs()

        assert len(runs) == 3
        assert "run-a" in runs
        assert "run-b" in runs
        assert "run-c" in runs

    def test_delete_state(self, manager):
        """delete_state removes state files."""
        manager.create_state("run-delete", "proj-1", ["P1"])
        assert manager.load_state("run-delete") is not None

        result = manager.delete_state("run-delete")

        assert result is True
        assert manager.load_state("run-delete") is None

    def test_persistence_across_managers(self, temp_storage):
        """State persists across manager instances."""
        # Create with first manager
        manager1 = ExecutorStateManager(storage_dir=temp_storage)
        state = manager1.create_state("run-persist", "proj-1", ["Phase1", "Phase2"])
        manager1.start_phase(state, state.phases[0].phase_id)
        manager1.complete_phase(state, state.phases[0].phase_id, success=True)

        # Load with new manager
        manager2 = ExecutorStateManager(storage_dir=temp_storage)
        loaded = manager2.load_state("run-persist")

        assert loaded is not None
        assert loaded.phases[0].status == PhaseStatus.COMPLETED
        assert loaded.phases[1].status == PhaseStatus.PENDING

    def test_backup_recovery(self, manager, temp_storage):
        """State can be recovered from backup."""
        state = manager.create_state("run-backup", "proj-1", ["P1"])

        # Make first save (creates initial backup on subsequent saves)
        state.phases[0].status = PhaseStatus.IN_PROGRESS
        manager.save_state(state)

        # Second save - now backup contains IN_PROGRESS
        state.phases[0].status = PhaseStatus.COMPLETED
        manager.save_state(state)

        # Third save - backup now contains COMPLETED
        state.metadata["extra"] = "data"
        manager.save_state(state)

        # Corrupt primary state file
        state_path = temp_storage / "run-backup" / "executor_state.json"
        state_path.write_text("corrupted", encoding="utf-8")

        # Should recover from backup (previous save = COMPLETED)
        loaded = manager.load_state("run-backup")

        assert loaded is not None
        assert loaded.phases[0].status == PhaseStatus.COMPLETED

    def test_config_hash(self, manager):
        """Config hash is computed correctly."""
        config = {"key": "value", "nested": {"a": 1}}
        state = manager.create_state(
            run_id="run-hash",
            project_id="proj-1",
            phase_names=["P1"],
            config=config,
        )

        assert state.config_hash is not None
        assert len(state.config_hash) == 16  # Truncated SHA256
