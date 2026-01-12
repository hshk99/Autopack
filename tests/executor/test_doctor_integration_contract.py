"""
Tests for Doctor Integration Contract (PR-EXE-8)

These tests verify the Doctor invocation and budget tracking logic.
"""

from unittest.mock import Mock


def test_doctor_integration_imports():
    """Verify doctor integration can be imported"""
    from autopack.executor.doctor_integration import DoctorIntegration

    assert DoctorIntegration is not None


def test_doctor_integration_instantiation():
    """Verify DoctorIntegration can be instantiated with defaults"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()
    assert doctor.max_doctor_calls_per_phase == 2
    assert doctor.max_doctor_calls_per_run == 10
    assert doctor.max_doctor_strong_calls_per_run == 5
    assert doctor.max_doctor_infra_calls_per_run == 3


def test_doctor_integration_custom_limits():
    """Verify DoctorIntegration can be instantiated with custom limits"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration(
        max_doctor_calls_per_phase=3,
        max_doctor_calls_per_run=15,
        max_doctor_strong_calls_per_run=8,
        max_doctor_infra_calls_per_run=5,
    )
    assert doctor.max_doctor_calls_per_phase == 3
    assert doctor.max_doctor_calls_per_run == 15


def test_should_invoke_doctor_min_attempts():
    """Test that Doctor is not invoked before minimum attempts"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    # Should not invoke with only 1 attempt (min is 2)
    should_invoke = doctor.should_invoke_doctor(
        phase_id="test-phase",
        builder_attempts=1,
        error_category="auditor_reject",
        health_budget={"total_failures": 1, "max_total_failures": 10},
        doctor_calls_by_phase={},
        run_doctor_calls=0,
    )

    assert should_invoke is False


def test_should_invoke_doctor_after_min_attempts():
    """Test that Doctor is invoked after minimum attempts"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    # Should invoke with 2+ attempts
    should_invoke = doctor.should_invoke_doctor(
        phase_id="test-phase",
        builder_attempts=2,
        error_category="auditor_reject",
        health_budget={"total_failures": 2, "max_total_failures": 10},
        doctor_calls_by_phase={},
        run_doctor_calls=0,
    )

    assert should_invoke is True


def test_should_invoke_doctor_per_phase_limit():
    """Test per-phase Doctor call limit"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration(max_doctor_calls_per_phase=2)

    # Already called 2 times for this phase
    doctor_calls_by_phase = {"test-run:test-phase": 2}

    should_invoke = doctor.should_invoke_doctor(
        phase_id="test-phase",
        builder_attempts=3,
        error_category="auditor_reject",
        health_budget={"total_failures": 3, "max_total_failures": 10},
        doctor_calls_by_phase=doctor_calls_by_phase,
        run_doctor_calls=2,
        run_id="test-run",
    )

    assert should_invoke is False


def test_should_invoke_doctor_run_level_limit():
    """Test run-level Doctor call limit"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration(max_doctor_calls_per_run=10)

    # Already called 10 times in this run
    should_invoke = doctor.should_invoke_doctor(
        phase_id="test-phase",
        builder_attempts=3,
        error_category="auditor_reject",
        health_budget={"total_failures": 3, "max_total_failures": 10},
        doctor_calls_by_phase={},
        run_doctor_calls=10,
    )

    assert should_invoke is False


def test_should_invoke_doctor_infra_errors():
    """Test that infra errors bypass minimum attempts"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    # Infra error should invoke even on first attempt
    should_invoke = doctor.should_invoke_doctor(
        phase_id="test-phase",
        builder_attempts=1,
        error_category="infra_error",
        health_budget={"total_failures": 1, "max_total_failures": 10},
        doctor_calls_by_phase={},
        run_doctor_calls=0,
    )

    assert should_invoke is True


def test_build_doctor_context():
    """Test building Doctor context summary"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    distinct_error_cats = {}
    last_responses = {}

    context = doctor.build_doctor_context(
        phase_id="test-phase",
        error_category="auditor_reject",
        run_id="test-run",
        distinct_error_cats_by_phase=distinct_error_cats,
        last_doctor_response_by_phase=last_responses,
    )

    assert context.distinct_error_categories_for_phase == 1
    assert "test-run:test-phase" in distinct_error_cats
    assert "auditor_reject" in distinct_error_cats["test-run:test-phase"]


def test_invoke_doctor_no_llm_service():
    """Test that invoke_doctor returns None when llm_service is not available"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    response = doctor.invoke_doctor(
        phase={"phase_id": "test-phase"},
        error_category="auditor_reject",
        builder_attempts=3,
        last_patch=None,
        patch_errors=[],
        logs_excerpt="Test error",
        llm_service=None,  # No LLM service
        run_id="test-run",
        doctor_calls_by_phase={},
        run_doctor_calls=0,
    )

    assert response is None


def test_handle_doctor_action_retry_with_fix():
    """Test handling retry_with_fix action"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    # Mock response
    class MockResponse:
        action = "retry_with_fix"
        builder_hint = "Try a different approach"
        rationale = "Previous approach failed"
        confidence = 0.8
        disable_providers = None

    builder_hints = {}
    action, should_continue = doctor.handle_doctor_action(
        phase={"phase_id": "test-phase"},
        response=MockResponse(),
        attempt_index=2,
        llm_service=Mock(),
        builder_hint_by_phase=builder_hints,
    )

    assert action == "retry_with_hint"
    assert should_continue is True
    assert "test-phase" in builder_hints


def test_handle_doctor_action_skip_phase():
    """Test handling skip_phase action"""
    from autopack.executor.doctor_integration import DoctorIntegration

    doctor = DoctorIntegration()

    class MockResponse:
        action = "skip_phase"
        rationale = "Phase is not feasible"
        confidence = 0.9
        disable_providers = None

    skipped = set()
    action, should_continue = doctor.handle_doctor_action(
        phase={"phase_id": "test-phase"},
        response=MockResponse(),
        attempt_index=2,
        llm_service=Mock(),
        skipped_phases=skipped,
    )

    assert action == "skip"
    assert should_continue is False
    assert "test-phase" in skipped
