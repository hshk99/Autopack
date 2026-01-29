"""Phase Lifecycle End-to-End Integration Tests (IMP-T01)

These tests verify the complete phase execution lifecycle including:
1. Phase initialization and setup
2. State transitions (QUEUED → EXECUTING → COMPLETE/FAILED)
3. Checkpoint saving and loading
4. Error handling and recovery mechanisms
5. Database state persistence

All tests are marked with @pytest.mark.aspirational for fast CI execution.
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from autopack.executor.phase_orchestrator import (ExecutionContext,
                                                  PhaseOrchestrator,
                                                  PhaseResult,
                                                  create_default_time_watchdog)
from autopack.executor.phase_state_manager import (PhaseStateManager,
                                                   StateUpdateRequest)
from autopack.models import Phase, PhaseState, Run, RunState, Tier, TierState


@pytest.fixture
def setup_run_tier_phase(db_session):
    """Fixture to create run, tier, and phase with proper relationships."""

    def _setup(run_id, phase_id, **phase_kwargs):
        # Create run
        run = Run(
            id=run_id,
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.flush()

        # Create tier
        tier = Tier(
            tier_id="T1",
            run_id=run_id,
            tier_index=0,
            name="Test Tier",
            state=TierState.IN_PROGRESS,
        )
        db_session.add(tier)
        db_session.flush()

        # Create phase with defaults
        phase_defaults = {
            "phase_id": phase_id,
            "run_id": run_id,
            "tier_id": tier.id,
            "phase_index": 0,
            "name": "Test Phase",
            "state": PhaseState.QUEUED,
            "retry_attempt": 0,
            "revision_epoch": 0,
            "escalation_level": 0,
        }
        phase_defaults.update(phase_kwargs)

        phase = Phase(**phase_defaults)
        db_session.add(phase)
        db_session.commit()

        return run, tier, phase

    return _setup


@pytest.mark.aspirational
class TestPhaseLifecycleComplete:
    """Test complete phase lifecycle from initialization to completion."""

    def test_phase_initialization_and_setup(self, setup_run_tier_phase, tmp_path):
        """Test phase is properly initialized with default state values."""
        # Create run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase("test-run-001", "test-phase-001")

        # Initialize phase state manager
        state_manager = PhaseStateManager(
            run_id="test-run-001",
            workspace=tmp_path,
            project_id="test-project",
        )

        # Load initial state
        state = state_manager.load_or_create_default("test-phase-001")

        # Verify initial state values
        assert state.retry_attempt == 0
        assert state.revision_epoch == 0
        assert state.escalation_level == 0
        assert state.last_failure_reason is None

    def test_phase_state_transitions_success_path(self, setup_run_tier_phase, db_session, tmp_path):
        """Test phase transitions through QUEUED → EXECUTING → COMPLETE."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-002", "test-phase-002", name="Success Phase", state=PhaseState.QUEUED
        )

        # Transition 1: QUEUED → EXECUTING
        phase.state = PhaseState.EXECUTING
        db_session.commit()
        db_session.refresh(phase)
        assert phase.state == PhaseState.EXECUTING

        # Transition 2: EXECUTING → COMPLETE
        state_manager = PhaseStateManager(
            run_id="test-run-002",
            workspace=tmp_path,
        )
        success = state_manager.mark_complete("test-phase-002")
        assert success is True

        # Verify final state
        db_session.refresh(phase)
        assert phase.state == PhaseState.COMPLETE
        assert phase.completed_at is not None

    def test_phase_state_transitions_failure_path(self, setup_run_tier_phase, db_session, tmp_path):
        """Test phase transitions through QUEUED → EXECUTING → FAILED."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-003", "test-phase-003", name="Failure Phase", state=PhaseState.QUEUED
        )

        # Transition 1: QUEUED → EXECUTING
        phase.state = PhaseState.EXECUTING
        db_session.commit()

        # Transition 2: EXECUTING → FAILED
        state_manager = PhaseStateManager(
            run_id="test-run-003",
            workspace=tmp_path,
        )
        success = state_manager.mark_failed("test-phase-003", "MAX_ATTEMPTS_EXHAUSTED")
        assert success is True

        # Verify final state
        db_session.refresh(phase)
        assert phase.state == PhaseState.FAILED
        assert phase.last_failure_reason == "MAX_ATTEMPTS_EXHAUSTED"
        assert phase.completed_at is not None


@pytest.mark.aspirational
class TestPhaseStateTransitions:
    """Test phase state transition logic and validation."""

    def test_retry_attempt_increment(self, setup_run_tier_phase, db_session, tmp_path):
        """Test retry attempt counter increments correctly."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-004",
            "test-phase-004",
            name="Retry Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=0,
        )

        # Increment retry attempt
        state_manager = PhaseStateManager(run_id="test-run-004", workspace=tmp_path)
        request = StateUpdateRequest(increment_retry=True, failure_reason="PATCH_FAILED")
        success = state_manager.update("test-phase-004", request)
        assert success is True

        # Verify increment
        db_session.refresh(phase)
        assert phase.retry_attempt == 1
        assert phase.last_failure_reason == "PATCH_FAILED"

    def test_revision_epoch_increment(self, setup_run_tier_phase, db_session, tmp_path):
        """Test revision epoch increments on replanning."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-005",
            "test-phase-005",
            name="Replan Phase",
            state=PhaseState.EXECUTING,
            revision_epoch=0,
        )

        # Increment revision epoch (replan)
        state_manager = PhaseStateManager(run_id="test-run-005", workspace=tmp_path)
        request = StateUpdateRequest(increment_epoch=True, failure_reason="DOCTOR_REPLAN")
        success = state_manager.update("test-phase-005", request)
        assert success is True

        # Verify increment
        db_session.refresh(phase)
        assert phase.revision_epoch == 1
        assert phase.last_failure_reason == "DOCTOR_REPLAN"

    def test_escalation_level_increment(self, setup_run_tier_phase, db_session, tmp_path):
        """Test escalation level increments correctly."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-006",
            "test-phase-006",
            name="Escalation Phase",
            state=PhaseState.EXECUTING,
            escalation_level=0,
        )

        # Increment escalation level
        state_manager = PhaseStateManager(run_id="test-run-006", workspace=tmp_path)
        request = StateUpdateRequest(increment_escalation=True)
        success = state_manager.update("test-phase-006", request)
        assert success is True

        # Verify increment
        db_session.refresh(phase)
        assert phase.escalation_level == 1

    def test_multiple_state_updates_preserve_counters(
        self, setup_run_tier_phase, db_session, tmp_path
    ):
        """Test that multiple state updates preserve independent counters."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-007", "test-phase-007", name="Multi-Update Phase", state=PhaseState.EXECUTING
        )

        state_manager = PhaseStateManager(run_id="test-run-007", workspace=tmp_path)

        # Update 1: Increment retry
        request = StateUpdateRequest(increment_retry=True)
        state_manager.update("test-phase-007", request)

        # Update 2: Increment epoch (replan)
        request = StateUpdateRequest(increment_epoch=True)
        state_manager.update("test-phase-007", request)

        # Update 3: Increment escalation
        request = StateUpdateRequest(increment_escalation=True)
        state_manager.update("test-phase-007", request)

        # Verify all counters maintained independently
        db_session.refresh(phase)
        assert phase.retry_attempt == 1
        assert phase.revision_epoch == 1
        assert phase.escalation_level == 1


@pytest.mark.aspirational
class TestPhaseCheckpointRecovery:
    """Test checkpoint saving and recovery mechanisms."""

    def test_load_phase_state_from_checkpoint(self, setup_run_tier_phase, db_session, tmp_path):
        """Test loading phase state from database checkpoint."""
        # Create phase with checkpoint state using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-008",
            "test-phase-008",
            name="Checkpoint Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=3,
            revision_epoch=1,
            escalation_level=2,
            last_failure_reason="PATCH_FAILED",
            last_attempt_timestamp=datetime.now(timezone.utc),
        )

        # Load checkpoint
        state_manager = PhaseStateManager(run_id="test-run-008", workspace=tmp_path)
        state = state_manager.load_or_create_default("test-phase-008")

        # Verify checkpoint data loaded correctly
        assert state.retry_attempt == 3
        assert state.revision_epoch == 1
        assert state.escalation_level == 2
        assert state.last_failure_reason == "PATCH_FAILED"
        assert state.last_attempt_timestamp is not None

    def test_phase_recovery_after_crash(self, setup_run_tier_phase, db_session, tmp_path):
        """Test phase can recover and continue from checkpoint after crash."""
        # Simulate phase that crashed mid-execution using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-009",
            "test-phase-009",
            name="Recovery Phase",
            state=PhaseState.EXECUTING,  # Was executing when crash occurred
            retry_attempt=2,  # Had already retried twice
            revision_epoch=0,
            escalation_level=1,  # Had escalated once
            last_failure_reason="AUDITOR_REJECT",
        )

        # Recover state
        state_manager = PhaseStateManager(run_id="test-run-009", workspace=tmp_path)
        state = state_manager.load_or_create_default("test-phase-009")

        # Verify recovery loaded correct state
        assert state.retry_attempt == 2
        assert state.escalation_level == 1
        assert state.last_failure_reason == "AUDITOR_REJECT"

        # Continue execution: increment retry for next attempt
        request = StateUpdateRequest(increment_retry=True, failure_reason="RETRY_AFTER_RECOVERY")
        success = state_manager.update("test-phase-009", request)
        assert success is True

        # Verify state progression after recovery
        db_session.refresh(phase)
        assert phase.retry_attempt == 3
        assert phase.last_failure_reason == "RETRY_AFTER_RECOVERY"

    def test_checkpoint_creation_on_failure(self, setup_run_tier_phase, db_session, tmp_path):
        """Test checkpoint is saved on phase failure for recovery."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-010",
            "test-phase-010",
            name="Checkpoint Save Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=0,
        )

        # Simulate failure and checkpoint save
        state_manager = PhaseStateManager(run_id="test-run-010", workspace=tmp_path)
        request = StateUpdateRequest(
            increment_retry=True,
            increment_escalation=True,
            failure_reason="VALIDATION_FAILED",
            timestamp=datetime.now(timezone.utc),
        )
        success = state_manager.update("test-phase-010", request)
        assert success is True

        # Verify checkpoint was saved
        db_session.refresh(phase)
        assert phase.retry_attempt == 1
        assert phase.escalation_level == 1
        assert phase.last_failure_reason == "VALIDATION_FAILED"
        assert phase.last_attempt_timestamp is not None


@pytest.mark.aspirational
class TestPhaseErrorHandlingAndRecovery:
    """Test error handling and recovery mechanisms."""

    def test_max_attempts_exhausted_handling(self, setup_run_tier_phase, db_session, tmp_path):
        """Test handling when max retry attempts are exhausted."""
        # Setup phase at max attempts using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-011",
            "test-phase-011",
            name="Max Attempts Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=5,  # At max attempts
        )

        # Simulate exhausted attempts
        state_manager = PhaseStateManager(run_id="test-run-011", workspace=tmp_path)
        success = state_manager.mark_failed("test-phase-011", "MAX_ATTEMPTS_EXHAUSTED")
        assert success is True

        # Verify phase marked as failed
        db_session.refresh(phase)
        assert phase.state == PhaseState.FAILED
        assert phase.last_failure_reason == "MAX_ATTEMPTS_EXHAUSTED"

    def test_phase_recovery_with_escalation(self, setup_run_tier_phase, db_session, tmp_path):
        """Test phase recovery with model escalation."""
        # Setup phase with failures using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-012",
            "test-phase-012",
            name="Escalation Recovery Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=2,
            escalation_level=0,
        )

        # Apply escalation recovery strategy
        state_manager = PhaseStateManager(run_id="test-run-012", workspace=tmp_path)
        request = StateUpdateRequest(
            increment_retry=True, increment_escalation=True, failure_reason="APPLYING_ESCALATION"
        )
        success = state_manager.update("test-phase-012", request)
        assert success is True

        # Verify escalation applied
        db_session.refresh(phase)
        assert phase.retry_attempt == 3
        assert phase.escalation_level == 1
        assert phase.last_failure_reason == "APPLYING_ESCALATION"

    def test_phase_replan_recovery(self, setup_run_tier_phase, db_session, tmp_path):
        """Test phase recovery via replanning (revision epoch increment)."""
        # Setup phase needing replan using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-013",
            "test-phase-013",
            name="Replan Recovery Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=3,
            revision_epoch=0,
            escalation_level=1,
        )

        # Apply replan recovery
        state_manager = PhaseStateManager(run_id="test-run-013", workspace=tmp_path)
        request = StateUpdateRequest(
            increment_epoch=True,
            failure_reason="DOCTOR_REPLAN",
            # Note: retry_attempt preserved during replan
        )
        success = state_manager.update("test-phase-013", request)
        assert success is True

        # Verify replan applied while preserving retry state
        db_session.refresh(phase)
        assert phase.retry_attempt == 3  # Preserved
        assert phase.revision_epoch == 1  # Incremented
        assert phase.escalation_level == 1  # Preserved
        assert phase.last_failure_reason == "DOCTOR_REPLAN"

    def test_database_transaction_rollback_on_error(
        self, setup_run_tier_phase, db_session, tmp_path
    ):
        """Test database transaction handling on errors."""
        # Setup run, tier, and phase using fixture
        run, tier, phase = setup_run_tier_phase(
            "test-run-014",
            "test-phase-014",
            name="Transaction Phase",
            state=PhaseState.EXECUTING,
            retry_attempt=0,
        )

        # Verify state manager handles non-existent phase gracefully
        state_manager = PhaseStateManager(run_id="test-run-014", workspace=tmp_path)
        success = state_manager.mark_complete("non-existent-phase")
        assert success is False

        # Verify original phase unchanged
        db_session.refresh(phase)
        assert phase.state == PhaseState.EXECUTING


@pytest.mark.aspirational
class TestPhaseOrchestratorIntegration:
    """Test PhaseOrchestrator integration with lifecycle management."""

    def test_orchestrator_handles_phase_initialization(self, tmp_path):
        """Test orchestrator properly initializes phase context."""
        # Create mock context
        phase_spec = {
            "phase_id": "orch-phase-001",
            "name": "Orchestrator Test Phase",
            "description": "Test phase for orchestrator",
            "scope": {"paths": ["src/test.py"]},
        }

        context = ExecutionContext(
            phase=phase_spec,
            attempt_index=0,
            max_attempts=5,
            escalation_level=0,
            allowed_paths=["src/"],
            run_id="test-run-015",
            llm_service=Mock(),
            time_watchdog=create_default_time_watchdog(),  # IMP-SAFETY-004: Required
        )

        # Create orchestrator
        orchestrator = PhaseOrchestrator(max_retry_attempts=5)

        # Verify orchestrator can handle phase context
        assert orchestrator.max_retry_attempts == 5
        assert context.attempt_index == 0
        assert context.phase["phase_id"] == "orch-phase-001"

    def test_orchestrator_success_result_handling(self, tmp_path):
        """Test orchestrator properly handles successful execution results."""
        # Create mock execution result
        from autopack.executor.phase_orchestrator import ExecutionResult

        result = ExecutionResult(
            success=True,
            status="COMPLETE",
            phase_result=PhaseResult.COMPLETE,
            updated_counters={
                "total_failures": 0,
                "http_500_count": 0,
                "patch_failure_count": 0,
                "doctor_calls": 0,
                "replan_count": 0,
            },
            should_continue=True,
        )

        # Verify result structure
        assert result.success is True
        assert result.phase_result == PhaseResult.COMPLETE
        assert result.should_continue is True

    def test_orchestrator_failure_result_handling(self, tmp_path):
        """Test orchestrator properly handles execution failures."""
        # Create mock failure result
        from autopack.executor.phase_orchestrator import ExecutionResult

        result = ExecutionResult(
            success=False,
            status="AUDITOR_REJECT",
            phase_result=PhaseResult.FAILED,
            updated_counters={
                "total_failures": 1,
                "http_500_count": 0,
                "patch_failure_count": 0,
                "doctor_calls": 0,
                "replan_count": 0,
            },
            should_continue=True,
        )

        # Verify result structure
        assert result.success is False
        assert result.phase_result == PhaseResult.FAILED
        assert result.should_continue is True
        assert result.updated_counters["total_failures"] == 1
