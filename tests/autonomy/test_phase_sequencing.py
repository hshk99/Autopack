"""Comprehensive tests for PhaseStateMachine (IMP-LIFECYCLE-002).

These tests verify the phase state machine for autopilot sequencing:
1. Valid state transitions
2. Invalid transition rejection
3. Phase dependency validation
4. Phase ordering constraints (research → build → deploy → monetize → postlaunch)
5. Rollback and retry capability
6. Integration with AutopilotController

Test coverage targets (25+ tests):
- State transition validation
- Dependency checking
- Ordering constraints
- Rollback/retry flows
- Edge cases and error handling
"""

import pytest

from autopack.autonomy.autopilot import (
    AutopilotController,
    InvalidTransitionError,
    PhaseDependencyError,
    PhaseExecutionState,
    PhaseStateMachine,
    PhaseType,
)


class TestPhaseExecutionState:
    """Test PhaseExecutionState enum."""

    def test_all_states_defined(self):
        """Test all required states are defined."""
        assert PhaseExecutionState.PENDING.value == "pending"
        assert PhaseExecutionState.READY.value == "ready"
        assert PhaseExecutionState.IN_PROGRESS.value == "in_progress"
        assert PhaseExecutionState.COMPLETED.value == "completed"
        assert PhaseExecutionState.FAILED.value == "failed"
        assert PhaseExecutionState.ROLLED_BACK.value == "rolled_back"

    def test_state_count(self):
        """Test correct number of states."""
        assert len(PhaseExecutionState) == 6


class TestPhaseType:
    """Test PhaseType enum."""

    def test_all_types_defined(self):
        """Test all required phase types are defined."""
        assert PhaseType.RESEARCH.value == "research"
        assert PhaseType.BUILD.value == "build"
        assert PhaseType.DEPLOY.value == "deploy"
        assert PhaseType.MONETIZE.value == "monetize"
        assert PhaseType.POSTLAUNCH.value == "postlaunch"

    def test_order_property(self):
        """Test phase ordering is correct."""
        assert PhaseType.RESEARCH.order == 0
        assert PhaseType.BUILD.order == 1
        assert PhaseType.DEPLOY.order == 2
        assert PhaseType.MONETIZE.order == 3
        assert PhaseType.POSTLAUNCH.order == 4

    def test_ordering_sequence(self):
        """Test phases are ordered correctly."""
        phases = [
            PhaseType.POSTLAUNCH,
            PhaseType.RESEARCH,
            PhaseType.DEPLOY,
            PhaseType.BUILD,
            PhaseType.MONETIZE,
        ]
        sorted_phases = sorted(phases, key=lambda p: p.order)
        expected = [
            PhaseType.RESEARCH,
            PhaseType.BUILD,
            PhaseType.DEPLOY,
            PhaseType.MONETIZE,
            PhaseType.POSTLAUNCH,
        ]
        assert sorted_phases == expected

    def test_get_dependencies_research(self):
        """Test research has no dependencies."""
        deps = PhaseType.get_dependencies(PhaseType.RESEARCH)
        assert deps == []

    def test_get_dependencies_build(self):
        """Test build requires research."""
        deps = PhaseType.get_dependencies(PhaseType.BUILD)
        assert deps == [PhaseType.RESEARCH]

    def test_get_dependencies_deploy(self):
        """Test deploy requires research and build."""
        deps = PhaseType.get_dependencies(PhaseType.DEPLOY)
        assert PhaseType.RESEARCH in deps
        assert PhaseType.BUILD in deps

    def test_get_dependencies_monetize(self):
        """Test monetize requires all prior phases."""
        deps = PhaseType.get_dependencies(PhaseType.MONETIZE)
        assert PhaseType.RESEARCH in deps
        assert PhaseType.BUILD in deps
        assert PhaseType.DEPLOY in deps

    def test_get_dependencies_postlaunch(self):
        """Test postlaunch requires all prior phases."""
        deps = PhaseType.get_dependencies(PhaseType.POSTLAUNCH)
        assert len(deps) == 4
        assert PhaseType.RESEARCH in deps
        assert PhaseType.BUILD in deps
        assert PhaseType.DEPLOY in deps
        assert PhaseType.MONETIZE in deps


class TestPhaseStateMachineBasics:
    """Test basic PhaseStateMachine functionality."""

    def test_init_default(self):
        """Test default initialization."""
        machine = PhaseStateMachine()
        assert machine._enforce_ordering is True
        assert len(machine._phases) == 0

    def test_init_no_ordering(self):
        """Test initialization without ordering enforcement."""
        machine = PhaseStateMachine(enforce_ordering=False)
        assert machine._enforce_ordering is False

    def test_register_phase(self):
        """Test registering a new phase."""
        machine = PhaseStateMachine()
        entry = machine.register_phase("research-001", PhaseType.RESEARCH)

        assert entry.phase_id == "research-001"
        assert entry.phase_type == PhaseType.RESEARCH
        assert entry.state == PhaseExecutionState.PENDING

    def test_register_phase_duplicate_raises(self):
        """Test registering duplicate phase raises error."""
        machine = PhaseStateMachine()
        machine.register_phase("test-001", PhaseType.RESEARCH)

        with pytest.raises(ValueError, match="already registered"):
            machine.register_phase("test-001", PhaseType.BUILD)

    def test_get_phase(self):
        """Test getting a registered phase."""
        machine = PhaseStateMachine()
        machine.register_phase("test-001", PhaseType.RESEARCH)

        entry = machine.get_phase("test-001")
        assert entry is not None
        assert entry.phase_id == "test-001"

    def test_get_phase_not_found(self):
        """Test getting non-existent phase returns None."""
        machine = PhaseStateMachine()
        assert machine.get_phase("nonexistent") is None

    def test_get_phase_state(self):
        """Test getting phase state."""
        machine = PhaseStateMachine()
        machine.register_phase("test-001", PhaseType.RESEARCH)

        state = machine.get_phase_state("test-001")
        assert state == PhaseExecutionState.PENDING


class TestValidTransitions:
    """Test valid state transitions."""

    def test_pending_to_ready(self):
        """Test PENDING → READY transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        # Research has no dependencies, can go to READY
        transition = machine.mark_ready("research-001")

        assert transition.from_state == PhaseExecutionState.PENDING
        assert transition.to_state == PhaseExecutionState.READY
        assert machine.get_phase_state("research-001") == PhaseExecutionState.READY

    def test_ready_to_in_progress(self):
        """Test READY → IN_PROGRESS transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")

        transition = machine.start_phase("research-001")

        assert transition.from_state == PhaseExecutionState.READY
        assert transition.to_state == PhaseExecutionState.IN_PROGRESS
        assert machine.get_phase_state("research-001") == PhaseExecutionState.IN_PROGRESS

    def test_in_progress_to_completed(self):
        """Test IN_PROGRESS → COMPLETED transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")

        transition = machine.complete_phase("research-001")

        assert transition.from_state == PhaseExecutionState.IN_PROGRESS
        assert transition.to_state == PhaseExecutionState.COMPLETED
        assert machine.get_phase_state("research-001") == PhaseExecutionState.COMPLETED

    def test_in_progress_to_failed(self):
        """Test IN_PROGRESS → FAILED transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")

        transition = machine.fail_phase("research-001", "Test error")

        assert transition.from_state == PhaseExecutionState.IN_PROGRESS
        assert transition.to_state == PhaseExecutionState.FAILED
        assert machine.get_phase_state("research-001") == PhaseExecutionState.FAILED
        assert machine.get_phase("research-001").error == "Test error"

    def test_failed_to_rolled_back(self):
        """Test FAILED → ROLLED_BACK transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "Test error")

        transition = machine.rollback_phase("research-001")

        assert transition.from_state == PhaseExecutionState.FAILED
        assert transition.to_state == PhaseExecutionState.ROLLED_BACK
        assert machine.get_phase("research-001").rollback_count == 1

    def test_rolled_back_to_ready(self):
        """Test ROLLED_BACK → READY transition for retry."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "Test error")
        machine.rollback_phase("research-001")

        transition = machine.mark_ready("research-001")

        assert transition.from_state == PhaseExecutionState.ROLLED_BACK
        assert transition.to_state == PhaseExecutionState.READY


class TestInvalidTransitions:
    """Test invalid state transitions are rejected."""

    def test_pending_to_in_progress_invalid(self):
        """Test PENDING → IN_PROGRESS is invalid."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        with pytest.raises(InvalidTransitionError):
            machine.start_phase("research-001")

    def test_pending_to_completed_invalid(self):
        """Test PENDING → COMPLETED is invalid."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        with pytest.raises(InvalidTransitionError):
            machine.complete_phase("research-001")

    def test_ready_to_completed_invalid(self):
        """Test READY → COMPLETED is invalid (must go through IN_PROGRESS)."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")

        with pytest.raises(InvalidTransitionError):
            machine.complete_phase("research-001")

    def test_completed_to_any_invalid(self):
        """Test COMPLETED is terminal - cannot transition."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        with pytest.raises(InvalidTransitionError):
            machine.start_phase("research-001")

    def test_failed_to_ready_invalid(self):
        """Test FAILED → READY is invalid (must rollback first)."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "Test error")

        with pytest.raises(InvalidTransitionError):
            machine.mark_ready("research-001")


class TestDependencyValidation:
    """Test phase dependency validation."""

    def test_build_cannot_start_without_research(self):
        """Test build phase cannot start without completed research."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        with pytest.raises(PhaseDependencyError) as exc_info:
            machine.mark_ready("build-001")

        assert PhaseType.RESEARCH in exc_info.value.missing_dependencies

    def test_build_can_start_after_research(self):
        """Test build phase can start after research completes."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        # Complete research
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        # Now build can start
        machine.mark_ready("build-001")
        assert machine.get_phase_state("build-001") == PhaseExecutionState.READY

    def test_deploy_requires_research_and_build(self):
        """Test deploy requires both research and build."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)
        machine.register_phase("deploy-001", PhaseType.DEPLOY)

        # Complete only research
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        # Deploy should fail - missing build
        with pytest.raises(PhaseDependencyError) as exc_info:
            machine.mark_ready("deploy-001")

        assert PhaseType.BUILD in exc_info.value.missing_dependencies

    def test_full_lifecycle_sequence(self):
        """Test full lifecycle execution sequence."""
        machine = PhaseStateMachine()

        # Register all phases
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)
        machine.register_phase("deploy-001", PhaseType.DEPLOY)
        machine.register_phase("monetize-001", PhaseType.MONETIZE)
        machine.register_phase("postlaunch-001", PhaseType.POSTLAUNCH)

        # Execute in order
        for phase_id in [
            "research-001",
            "build-001",
            "deploy-001",
            "monetize-001",
            "postlaunch-001",
        ]:
            machine.mark_ready(phase_id)
            machine.start_phase(phase_id)
            machine.complete_phase(phase_id)

        assert machine.are_all_phases_complete() is True

    def test_dependencies_disabled(self):
        """Test dependencies can be disabled."""
        machine = PhaseStateMachine(enforce_ordering=False)
        machine.register_phase("deploy-001", PhaseType.DEPLOY)

        # Should work without dependencies when disabled
        machine.mark_ready("deploy-001")
        assert machine.get_phase_state("deploy-001") == PhaseExecutionState.READY


class TestRollbackAndRetry:
    """Test rollback and retry functionality."""

    def test_rollback_increments_count(self):
        """Test rollback increments rollback count."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "Error 1")
        machine.rollback_phase("research-001")

        entry = machine.get_phase("research-001")
        assert entry.rollback_count == 1

        # Retry and fail again
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "Error 2")
        machine.rollback_phase("research-001")

        assert entry.rollback_count == 2

    def test_retry_after_rollback(self):
        """Test full retry cycle after rollback."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        # First attempt - fail
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.fail_phase("research-001", "First error")
        machine.rollback_phase("research-001")

        # Retry - succeed
        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        assert machine.get_phase_state("research-001") == PhaseExecutionState.COMPLETED


class TestCompletionStatus:
    """Test completion status checking."""

    def test_are_all_complete_empty(self):
        """Test empty machine returns False."""
        machine = PhaseStateMachine()
        assert machine.are_all_phases_complete() is False

    def test_are_all_complete_partial(self):
        """Test partial completion returns False."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        # Build is still pending
        assert machine.are_all_phases_complete() is False

    def test_get_completion_status(self):
        """Test get_completion_status returns correct data."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        status = machine.get_completion_status()

        assert status["total_phases"] == 2
        assert status["completed_count"] == 1
        assert status["pending_count"] == 1
        assert status["all_complete"] is False

    def test_get_phases_by_state(self):
        """Test getting phases by state."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)
        machine.register_phase("deploy-001", PhaseType.DEPLOY)

        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        machine.mark_ready("build-001")

        pending = machine.get_phases_by_state(PhaseExecutionState.PENDING)
        ready = machine.get_phases_by_state(PhaseExecutionState.READY)
        completed = machine.get_phases_by_state(PhaseExecutionState.COMPLETED)

        assert "deploy-001" in pending
        assert "build-001" in ready
        assert "research-001" in completed


class TestTransitionHistory:
    """Test transition history tracking."""

    def test_transitions_recorded(self):
        """Test transitions are recorded."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")

        entry = machine.get_phase("research-001")
        assert len(entry.transitions) == 3

    def test_get_transition_history(self):
        """Test get_transition_history returns correct data."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")

        history = machine.get_transition_history("research-001")

        assert len(history) == 2
        assert history[0]["from_state"] == "pending"
        assert history[0]["to_state"] == "ready"
        assert history[1]["from_state"] == "ready"
        assert history[1]["to_state"] == "in_progress"

    def test_global_transition_history(self):
        """Test global transition history across phases."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        machine.mark_ready("research-001")
        machine.start_phase("research-001")
        machine.complete_phase("research-001")
        machine.mark_ready("build-001")

        history = machine.get_transition_history()  # No phase_id = global

        assert len(history) == 4


class TestCanPhaseStart:
    """Test can_phase_start method."""

    def test_can_start_pending_phase(self):
        """Test pending phase cannot start directly."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)

        can_start, reason = machine.can_phase_start("research-001")

        assert can_start is False
        assert "must be 'ready'" in reason

    def test_can_start_ready_phase(self):
        """Test ready phase can start."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")

        can_start, reason = machine.can_phase_start("research-001")

        assert can_start is True

    def test_can_start_with_missing_deps(self):
        """Test phase with missing deps cannot start."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase(
            "build-001", PhaseType.BUILD, initial_state=PhaseExecutionState.READY
        )

        can_start, reason = machine.can_phase_start("build-001")

        assert can_start is False
        assert "dependencies" in reason.lower()


class TestGetNextExecutablePhases:
    """Test get_next_executable_phases method."""

    def test_empty_machine(self):
        """Test empty machine returns empty list."""
        machine = PhaseStateMachine()
        assert machine.get_next_executable_phases() == []

    def test_only_ready_phases_returned(self):
        """Test only ready phases with satisfied deps are returned."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        machine.mark_ready("research-001")

        executable = machine.get_next_executable_phases()

        assert "research-001" in executable
        assert "build-001" not in executable


class TestAutopilotControllerIntegration:
    """Test PhaseStateMachine integration with AutopilotController."""

    @pytest.fixture
    def controller(self, tmp_path):
        """Create an AutopilotController instance."""
        return AutopilotController(
            workspace_root=tmp_path,
            project_id="test-project",
            run_id="test-run",
            enabled=True,
        )

    def test_initialize_phase_state_machine(self, controller):
        """Test initializing phase state machine on controller."""
        machine = controller.initialize_phase_state_machine()

        assert machine is not None
        assert controller.get_phase_state_machine() is machine

    def test_register_lifecycle_phase(self, controller):
        """Test registering lifecycle phase."""
        entry = controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)

        assert entry is not None
        assert entry.phase_id == "research-001"

    def test_start_lifecycle_phase(self, controller):
        """Test starting lifecycle phase."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)

        result = controller.start_lifecycle_phase("research-001")

        assert result is True
        machine = controller.get_phase_state_machine()
        assert machine.get_phase_state("research-001") == PhaseExecutionState.IN_PROGRESS

    def test_complete_lifecycle_phase(self, controller):
        """Test completing lifecycle phase."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.start_lifecycle_phase("research-001")

        result = controller.complete_lifecycle_phase("research-001")

        assert result is True
        machine = controller.get_phase_state_machine()
        assert machine.get_phase_state("research-001") == PhaseExecutionState.COMPLETED

    def test_fail_lifecycle_phase(self, controller):
        """Test failing lifecycle phase."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.start_lifecycle_phase("research-001")

        result = controller.fail_lifecycle_phase("research-001", "Test error")

        assert result is True
        machine = controller.get_phase_state_machine()
        assert machine.get_phase_state("research-001") == PhaseExecutionState.FAILED

    def test_rollback_lifecycle_phase(self, controller):
        """Test rolling back lifecycle phase."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.start_lifecycle_phase("research-001")
        controller.fail_lifecycle_phase("research-001", "Test error")

        result = controller.rollback_lifecycle_phase("research-001")

        assert result is True
        machine = controller.get_phase_state_machine()
        assert machine.get_phase_state("research-001") == PhaseExecutionState.ROLLED_BACK

    def test_retry_lifecycle_phase(self, controller):
        """Test retrying lifecycle phase."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.start_lifecycle_phase("research-001")
        controller.fail_lifecycle_phase("research-001", "Test error")
        controller.rollback_lifecycle_phase("research-001")

        result = controller.retry_lifecycle_phase("research-001")

        assert result is True
        machine = controller.get_phase_state_machine()
        assert machine.get_phase_state("research-001") == PhaseExecutionState.IN_PROGRESS

    def test_get_next_lifecycle_phases(self, controller):
        """Test getting next executable phases."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.register_lifecycle_phase("build-001", PhaseType.BUILD)

        # Mark research ready
        machine = controller.get_phase_state_machine()
        machine.mark_ready("research-001")

        next_phases = controller.get_next_lifecycle_phases()

        assert "research-001" in next_phases
        assert "build-001" not in next_phases

    def test_get_lifecycle_phase_status(self, controller):
        """Test getting lifecycle phase status."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)
        controller.start_lifecycle_phase("research-001")
        controller.complete_lifecycle_phase("research-001")

        status = controller.get_lifecycle_phase_status()

        assert status["initialized"] is True
        assert "phases" in status
        assert "research-001" in status["phases"]

    def test_are_all_lifecycle_phases_complete(self, controller):
        """Test checking if all phases are complete."""
        controller.register_lifecycle_phase("research-001", PhaseType.RESEARCH)

        assert controller.are_all_lifecycle_phases_complete() is False

        controller.start_lifecycle_phase("research-001")
        controller.complete_lifecycle_phase("research-001")

        assert controller.are_all_lifecycle_phases_complete() is True


class TestPhaseStateMachineReset:
    """Test reset functionality."""

    def test_reset_clears_phases(self):
        """Test reset clears all registered phases."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.register_phase("build-001", PhaseType.BUILD)

        machine.reset()

        assert len(machine._phases) == 0
        assert len(machine._global_transitions) == 0


class TestPhaseStateMachineToDict:
    """Test to_dict serialization."""

    def test_to_dict_includes_all_data(self):
        """Test to_dict includes all relevant data."""
        machine = PhaseStateMachine()
        machine.register_phase("research-001", PhaseType.RESEARCH)
        machine.mark_ready("research-001")
        machine.start_phase("research-001")

        result = machine.to_dict()

        assert "enforce_ordering" in result
        assert "phases" in result
        assert "research-001" in result["phases"]
        assert "completion_status" in result
        assert "recent_transitions" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
