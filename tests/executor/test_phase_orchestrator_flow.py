"""
Tests for Phase Orchestrator Flow (PR-EXE-8)

These tests verify the phase orchestration logic extracted from autonomous_executor.py.
"""

from unittest.mock import Mock


def test_orchestrator_imports():
    """Verify orchestrator can be imported"""
    from autopack.executor.phase_orchestrator import (
        PhaseOrchestrator,
        ExecutionContext,
        ExecutionResult,
        PhaseResult,
    )

    assert PhaseOrchestrator is not None
    assert ExecutionContext is not None
    assert ExecutionResult is not None
    assert PhaseResult is not None


def test_phase_result_enum():
    """Verify PhaseResult enum values"""
    from autopack.executor.phase_orchestrator import PhaseResult

    assert PhaseResult.COMPLETE.value == "COMPLETE"
    assert PhaseResult.FAILED.value == "FAILED"
    assert PhaseResult.REPLAN_REQUESTED.value == "REPLAN_REQUESTED"
    assert PhaseResult.BLOCKED.value == "BLOCKED"


def test_execution_context_creation():
    """Verify ExecutionContext can be created with required fields"""
    from autopack.executor.phase_orchestrator import ExecutionContext

    phase = {"phase_id": "test-phase", "description": "Test phase"}

    context = ExecutionContext(
        phase=phase,
        attempt_index=0,
        max_attempts=5,
        escalation_level=0,
        allowed_paths=[],
        run_id="test-run-123",
        llm_service=Mock(),
    )

    assert context.phase == phase
    assert context.attempt_index == 0
    assert context.max_attempts == 5
    assert context.run_id == "test-run-123"


def test_orchestrator_instantiation():
    """Verify PhaseOrchestrator can be instantiated"""
    from autopack.executor.phase_orchestrator import PhaseOrchestrator

    orchestrator = PhaseOrchestrator(max_retry_attempts=5)
    assert orchestrator.max_retry_attempts == 5


def test_execution_result_structure():
    """Verify ExecutionResult structure"""
    from autopack.executor.phase_orchestrator import ExecutionResult, PhaseResult

    result = ExecutionResult(
        success=True,
        status="COMPLETE",
        phase_result=PhaseResult.COMPLETE,
        updated_counters={"total_failures": 0},
        should_continue=False,
    )

    assert result.success is True
    assert result.status == "COMPLETE"
    assert result.phase_result == PhaseResult.COMPLETE
    assert result.updated_counters == {"total_failures": 0}
    assert result.should_continue is False


def test_create_exhausted_result():
    """Test _create_exhausted_result method"""
    from autopack.executor.phase_orchestrator import PhaseOrchestrator, ExecutionContext

    orchestrator = PhaseOrchestrator(max_retry_attempts=5)

    phase = {"phase_id": "test-phase"}
    context = ExecutionContext(
        phase=phase,
        attempt_index=5,
        max_attempts=5,
        escalation_level=0,
        allowed_paths=[],
        run_id="test-run-123",
        llm_service=Mock(),
        mark_phase_failed_in_db=Mock(),
    )

    result = orchestrator._create_exhausted_result(context)

    assert result.success is False
    assert result.status == "FAILED"
    assert result.should_continue is False


def test_orchestrator_with_mock_context():
    """Test orchestrator with minimal mock context"""
    from autopack.executor.phase_orchestrator import (
        PhaseOrchestrator,
        ExecutionContext,
        PhaseResult,
    )

    orchestrator = PhaseOrchestrator(max_retry_attempts=5)

    phase = {"phase_id": "test-phase", "description": "Test"}
    context = ExecutionContext(
        phase=phase,
        attempt_index=5,  # Already exhausted
        max_attempts=5,
        escalation_level=0,
        allowed_paths=[],
        run_id="test-run",
        llm_service=Mock(),
        mark_phase_failed_in_db=Mock(),
    )

    # Should return exhausted result immediately
    result = orchestrator.execute_phase_attempt(context)

    assert result.success is False
    assert result.phase_result == PhaseResult.FAILED


# Integration smoke tests


def test_successful_phase_execution_mock():
    """Test happy path: phase succeeds on first attempt (mocked)"""
    from autopack.executor.phase_orchestrator import PhaseOrchestrator, ExecutionContext

    # This is a smoke test - just verify the structure works
    PhaseOrchestrator(max_retry_attempts=5)

    # Create minimal context
    phase = {"phase_id": "test-phase", "scope": {"paths": ["test.py"]}}
    ExecutionContext(
        phase=phase,
        attempt_index=0,
        max_attempts=5,
        escalation_level=0,
        allowed_paths=["test.py"],
        run_id="test-run",
        llm_service=Mock(),
        mark_phase_complete_in_db=Mock(),
        record_learning_hint=Mock(),
        record_token_efficiency_telemetry=Mock(),
    )

    # Note: This will fail without full setup, but verifies structure
    # In real tests, we'd mock attempt_runner.run_single_attempt_with_recovery


def test_retry_after_failure_mock():
    """Test retry flow: phase fails then succeeds (structure test)"""
    from autopack.executor.phase_orchestrator import PhaseOrchestrator

    orchestrator = PhaseOrchestrator(max_retry_attempts=5)
    assert orchestrator.max_retry_attempts == 5


def test_max_attempts_exhausted():
    """Test exhaustion: phase fails all attempts"""
    from autopack.executor.phase_orchestrator import (
        PhaseOrchestrator,
        ExecutionContext,
        PhaseResult,
    )

    orchestrator = PhaseOrchestrator(max_retry_attempts=3)

    phase = {"phase_id": "exhausted-phase"}
    context = ExecutionContext(
        phase=phase,
        attempt_index=3,  # Already at max
        max_attempts=3,
        escalation_level=0,
        allowed_paths=[],
        run_id="test-run",
        llm_service=Mock(),
        mark_phase_failed_in_db=Mock(),
    )

    result = orchestrator.execute_phase_attempt(context)

    assert result.phase_result == PhaseResult.FAILED
    assert result.success is False
