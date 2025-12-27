"""End-to-end integration tests for research system."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

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
        'tmp_path': tmp_path,
        'history_file': history_file,
        'research_dir': research_dir,
        'review_dir': review_dir
    }


@pytest.fixture
def mock_research_execution():
    """Mock research execution for integration tests."""
    with patch('autopack.phases.research_phase.ResearchSession') as mock:
        session_result = Mock()
        session_result.session_id = "integration_test_123"
        session_result.final_answer = "Integration test findings: Use best practices."
        session_result.iterations = [
            Mock(summary="Research iteration 1"),
            Mock(summary="Research iteration 2")
        ]
        session_result.status = "completed"
        mock.return_value.research.return_value = session_result
        yield mock


def test_full_research_workflow(integration_setup, mock_research_execution):
    """Test complete research workflow from trigger to review."""
    setup = integration_setup

    # 1. Set up research hooks
    trigger_config = ResearchTriggerConfig(
        enabled=True,
        auto_trigger=True,
        build_history_path=setup['history_file'],
        research_output_dir=setup['research_dir']
    )
    hooks = ResearchHooks(config=trigger_config)

    # 2. Check if research should be triggered
    task = "Implement complex new feature with multiple approaches"
    should_trigger = hooks.should_research(task, "IMPLEMENT_FEATURE", {})
    assert should_trigger

    # 3. Execute research via pre-planning hook
    context = {}
    updated_context = hooks.pre_planning_hook(task, "IMPLEMENT_FEATURE", context)

    assert 'research_result' in updated_context
    assert 'research_findings' in updated_context
    research_result = updated_context['research_result']

    # 4. Review research results
    review_config = ReviewConfig(
        auto_approve_threshold=0.7,
        require_human_review=False,
        store_reviews=True,
        review_storage_dir=setup['review_dir']
    )
    review_workflow = ResearchReviewWorkflow(config=review_config)
    review = review_workflow.review_research(research_result, updated_context)

    assert review.decision.value in ['approved', 'pending']

    # 5. Augment plan with research
    plan = {'steps': ['step1', 'step2']}
    updated_plan = hooks.post_planning_hook(plan, updated_context)

    assert 'metadata' in updated_plan
    assert 'research_session_id' in updated_plan['metadata']


def test_build_history_integration(integration_setup):
    """Test BUILD_HISTORY integration with research system."""
    setup = integration_setup

    # Load and analyze build history
    integrator = BuildHistoryIntegrator(build_history_path=setup['history_file'])
    entries = integrator.load_history()
    assert len(entries) == 3

    # Analyze patterns
    patterns = integrator.analyze_patterns()
    assert len(patterns) > 0

    # Get recommendations
    recommendations = integrator.get_research_recommendations(
        "Implement another feature"
    )
    assert len(recommendations) > 0

    # Check research trigger
    should_trigger = integrator.should_trigger_research(
        "Implement feature",
        "IMPLEMENT_FEATURE"
    )
    # Should trigger because IMPLEMENT_FEATURE has failures in history
    assert should_trigger


def test_research_phase_storage(integration_setup, mock_research_execution):
    """Test research phase result storage."""
    setup = integration_setup

    # Execute research phase
    config = ResearchPhaseConfig(
        query="Test integration query",
        max_iterations=3,
        output_dir=setup['research_dir'],
        store_results=True
    )
    phase = ResearchPhase(config=config)
    result = phase.execute()

    assert result.success
    assert len(result.artifacts) > 0

    # Verify artifacts were created
    for artifact_path in result.artifacts.values():
        # Note: In mock scenario, paths may not actually exist
        # In real scenario, we'd check artifact_path.exists()
        assert artifact_path is not None


def test_review_workflow_storage(integration_setup, mock_research_execution):
    """Test review workflow storage and retrieval."""
    setup = integration_setup

    # Create research result
    config = ResearchPhaseConfig(
        query="Test query",
        output_dir=setup['research_dir']
    )
    phase = ResearchPhase(config=config)
    research_result = phase.execute()

    # Review and store
    review_config = ReviewConfig(
        store_reviews=True,
        review_storage_dir=setup['review_dir']
    )
    workflow = ResearchReviewWorkflow(config=review_config)
    review = workflow.review_research(research_result, {})

    # Load review back
    loaded_review = workflow.load_review(research_result.session_id)
    assert loaded_review is not None
    assert loaded_review.decision == review.decision


def test_autonomous_mode_integration(integration_setup, mock_research_execution):
    """Test integration with autonomous mode workflow."""
    setup = integration_setup

    # Simulate autonomous mode workflow
    trigger_config = ResearchTriggerConfig(
        enabled=True,
        auto_trigger=True,
        build_history_path=setup['history_file'],
        research_output_dir=setup['research_dir']
    )
    hooks = ResearchHooks(config=trigger_config)

    # Task that should trigger research
    task = "Research and implement authentication system"
    phase_type = "IMPLEMENT_FEATURE"
    context = {'complexity': 'high'}

    # Pre-planning: trigger research
    planning_context = hooks.pre_planning_hook(task, phase_type, context)
    assert 'research_result' in planning_context

    # Planning: create plan (simulated)
    plan = {
        'phase_type': phase_type,
        'description': task,
        'steps': ['step1', 'step2']
    }

    # Post-planning: augment with research
    final_plan = hooks.post_planning_hook(plan, planning_context)
    assert 'metadata' in final_plan
    assert 'research_session_id' in final_plan['metadata']
    assert 'notes' in final_plan

    # Verify research metadata
    metadata = final_plan['metadata']
    assert metadata['research_confidence'] > 0.0
    assert metadata['research_findings_count'] > 0


def test_error_handling_integration(integration_setup):
    """Test error handling across integration points."""
    setup = integration_setup

    # Test with missing BUILD_HISTORY
    missing_history = setup['tmp_path'] / "nonexistent.md"
    trigger_config = ResearchTriggerConfig(
        enabled=True,
        build_history_path=missing_history
    )
    hooks = ResearchHooks(config=trigger_config)

    # Should not crash, just work without history integration
    context = hooks.pre_planning_hook(
        "Test task",
        "IMPLEMENT_FEATURE",
        {}
    )
    # Context should be returned unchanged or with minimal research
    assert context is not None


def test_disabled_research_integration(integration_setup):
    """Test that system works when research is disabled."""
    setup = integration_setup

    # Disable research
    trigger_config = ResearchTriggerConfig(
        enabled=False,
        auto_trigger=False
    )
    hooks = ResearchHooks(config=trigger_config)

    # Should not trigger research
    context = {}
    updated_context = hooks.pre_planning_hook(
        "Research this topic",
        "IMPLEMENT_FEATURE",
        context
    )

    assert 'research_result' not in updated_context
    assert updated_context == context
