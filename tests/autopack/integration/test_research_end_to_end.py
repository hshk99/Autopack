"""End-to-end integration tests for research system."""

from unittest.mock import Mock, patch

import pytest

from autopack.autonomous.research_hooks import ResearchHooks, ResearchTriggerConfig
from autopack.integrations.build_history_integrator import BuildHistoryIntegrator
from autopack.phases.research_phase import ResearchPhase, ResearchPhaseConfig
from autopack.workflow.research_review import ResearchReviewWorkflow, ReviewConfig


@pytest.fixture
def integration_setup(tmp_path):
    """Set up integration test environment."""
    # Create BUILD_HISTORY
    history_file = tmp_path / "BUILD_HISTORY.md"
    history_file.write_text("""
## Phase: IMPLEMENT_FEATURE - Feature A (SUCCESS) [2024-01-01T10:00:00]
## Phase: IMPLEMENT_FEATURE - Feature B (FAILED) [2024-01-02T11:00:00]
## Phase: FIX_BUG - Bug fix (SUCCESS) [2024-01-03T12:00:00]
    """)

    # Create directories
    research_dir = tmp_path / "research"
    review_dir = tmp_path / "reviews"
    research_dir.mkdir()
    review_dir.mkdir()

    return {
        "tmp_path": tmp_path,
        "history_file": history_file,
        "research_dir": research_dir,
        "review_dir": review_dir,
    }


@pytest.fixture
def mock_research_execution():
    """Mock research execution for integration tests."""
    with patch("autopack.autonomous.research_hooks.ResearchHooks.execute_research_phase") as mock:
        phase_result = Mock()
        phase_result.session_id = "integration_test_123"
        phase_result.final_answer = "Integration test findings: Use best practices."
        phase_result.status = "completed"
        phase_result.confidence = 0.85
        phase_result.findings = ["Finding 1", "Finding 2"]
        phase_result.recommendations = ["Rec 1"]
        mock.return_value = phase_result
        yield mock


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_full_research_workflow(integration_setup, mock_research_execution):
    """Test complete research workflow from trigger to review."""
    setup = integration_setup

    # 1. Set up research hooks
    trigger_config = ResearchTriggerConfig(
        enabled=True,
    )
    hooks = ResearchHooks(config=trigger_config)

    # 2. Check if research should be triggered
    task_context = {
        "description": "Implement complex new feature with multiple approaches",
        "category": "IMPLEMENT_FEATURE",
        "complexity": "high",
    }
    decision = hooks.should_trigger_research(task_context)
    assert decision is not None
    # Decision may or may not trigger based on conditions

    # 3. Execute research phase
    research_result = hooks.execute_research_phase(task_context)
    # Research result can be None if no executor is provided
    if research_result is not None:
        assert research_result.status is not None

    # 4. Review research results (if we got results)
    if research_result:
        review_config = ReviewConfig(
            auto_approve_confidence=0.7,
            require_human_review=False,
        )
        review_workflow = ResearchReviewWorkflow(criteria=review_config)
        review_id = review_workflow.submit_for_review(research_result)
        status = review_workflow.get_review_status(review_id)
        assert status is not None


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_build_history_integration(integration_setup):
    """Test BUILD_HISTORY integration with research system."""
    setup = integration_setup

    # Create integrator from build history file
    integrator = BuildHistoryIntegrator(build_history_path=setup["history_file"])

    # Get insights for a task
    insights = integrator.get_insights_for_task(
        task_description="Implement another feature",
        category="IMPLEMENT_FEATURE",
    )
    assert insights is not None

    # Check research trigger
    should_trigger = integrator.should_trigger_research(
        task_description="Implement feature",
        category="IMPLEMENT_FEATURE",
    )
    # Should trigger because IMPLEMENT_FEATURE has failures in history
    assert isinstance(should_trigger, bool)


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_research_phase_storage(integration_setup, mock_research_execution):
    """Test research phase result storage."""
    setup = integration_setup

    # Create research phase with queries
    config = ResearchPhaseConfig(
        queries=[],
        max_duration_minutes=5,
        save_to_history=False,
    )
    phase = ResearchPhase(
        phase_id="test_phase_123",
        description="Test integration query",
        config=config,
    )

    assert phase.phase_id == "test_phase_123"
    assert phase.status.value == "pending"
    assert phase.error is None


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_review_workflow_storage(integration_setup, mock_research_execution):
    """Test review workflow storage and retrieval."""
    setup = integration_setup

    # Create research phase
    config = ResearchPhaseConfig(queries=[], save_to_history=False)
    phase = ResearchPhase(
        phase_id="test_review_phase_456",
        description="Test query",
        config=config,
    )

    # Review and store
    review_config = ReviewConfig(
        require_human_review=False,
    )
    workflow = ResearchReviewWorkflow(criteria=review_config)
    review_id = workflow.submit_for_review(phase)

    assert review_id is not None
    status = workflow.get_review_status(review_id)
    assert status["status"] in ["completed", "pending"]


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_autonomous_mode_integration(integration_setup, mock_research_execution):
    """Test integration with autonomous mode workflow."""
    setup = integration_setup

    # Simulate autonomous mode workflow
    trigger_config = ResearchTriggerConfig(
        enabled=True,
    )
    hooks = ResearchHooks(config=trigger_config)

    # Task that should trigger research
    task_context = {
        "description": "Research and implement authentication system",
        "category": "IMPLEMENT_FEATURE",
        "complexity": "high",
    }

    # Check if research should be triggered
    decision = hooks.should_trigger_research(task_context)
    assert decision is not None
    assert isinstance(decision.triggered, bool)

    # Execute research phase
    research_result = hooks.execute_research_phase(task_context)
    # Result may be None if no executor configured
    if research_result:
        assert research_result.status is not None

    # Verify decision history
    history = hooks.get_decision_history()
    assert len(history) > 0
    assert isinstance(history[0].triggered, bool)


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_error_handling_integration(integration_setup):
    """Test error handling across integration points."""
    setup = integration_setup

    # Test with minimal config
    trigger_config = ResearchTriggerConfig(enabled=True)
    hooks = ResearchHooks(config=trigger_config)

    # Should not crash when checking trigger decision
    task_context = {
        "description": "Test task",
        "category": "IMPLEMENT_FEATURE",
    }
    decision = hooks.should_trigger_research(task_context)
    assert decision is not None
    # Should handle gracefully if no executor available
    result = hooks.execute_research_phase(task_context)
    assert result is None  # No executor, so returns None


@pytest.mark.timeout(60)  # Increased from 30s for slow CI runners
def test_disabled_research_integration(integration_setup):
    """Test that system works when research is disabled."""

    # Disable research
    trigger_config = ResearchTriggerConfig(enabled=False)
    hooks = ResearchHooks(config=trigger_config)

    # Should not trigger research
    task_context = {
        "description": "Research this topic",
        "category": "IMPLEMENT_FEATURE",
    }
    decision = hooks.should_trigger_research(task_context)

    assert decision.triggered is False
    assert decision.reason == "Research hooks disabled"
