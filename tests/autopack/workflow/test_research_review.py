"""Tests for research review workflow."""

import pytest

from autopack.phases.research_phase import ResearchPhaseResult
from autopack.workflow.research_review import (ResearchReviewWorkflow,
                                               ReviewConfig, ReviewDecision)


@pytest.fixture
def review_config(tmp_path):
    """Create review configuration."""
    return ReviewConfig(
        auto_approve_threshold=0.9,
        require_human_review=False,
        review_timeout_seconds=60,
        store_reviews=True,
        review_storage_dir=tmp_path / "reviews",
    )


@pytest.fixture
def high_confidence_research():
    """Create high-confidence research result."""
    return ResearchPhaseResult(
        success=True,
        session_id="high_conf_123",
        query="test query",
        findings=["Finding 1", "Finding 2", "Finding 3"],
        recommendations=["Rec 1"],
        confidence_score=0.95,
        iterations_used=3,
        duration_seconds=10.0,
    )


@pytest.fixture
def low_confidence_research():
    """Create low-confidence research result."""
    return ResearchPhaseResult(
        success=True,
        session_id="low_conf_123",
        query="test query",
        findings=["Finding 1"],
        recommendations=[],
        confidence_score=0.5,
        iterations_used=2,
        duration_seconds=5.0,
    )


def test_auto_approve_high_confidence(review_config, high_confidence_research):
    """Test auto-approval of high-confidence research."""
    workflow = ResearchReviewWorkflow(config=review_config)
    review = workflow.review_research(high_confidence_research, {})

    assert review.decision == ReviewDecision.APPROVED
    assert review.reviewer == "auto"
    assert len(review.approved_findings) == 3


def test_no_auto_approve_low_confidence(review_config, low_confidence_research):
    """Test that low-confidence research is not auto-approved."""
    workflow = ResearchReviewWorkflow(config=review_config)
    review = workflow.review_research(low_confidence_research, {})

    assert review.decision != ReviewDecision.APPROVED


def test_require_human_review(review_config, high_confidence_research):
    """Test human review requirement."""
    review_config.require_human_review = True
    workflow = ResearchReviewWorkflow(config=review_config)
    review = workflow.review_research(high_confidence_research, {})

    assert review.decision == ReviewDecision.PENDING
    assert len(review.additional_questions) > 0


def test_store_review(review_config, high_confidence_research):
    """Test review storage."""
    workflow = ResearchReviewWorkflow(config=review_config)
    workflow.review_research(high_confidence_research, {})

    # Check that review was stored
    review_file = (
        review_config.review_storage_dir / f"{high_confidence_research.session_id}_review.json"
    )
    assert review_file.exists()


def test_load_review(review_config, high_confidence_research):
    """Test loading stored review."""
    workflow = ResearchReviewWorkflow(config=review_config)

    # Store a review
    original_review = workflow.review_research(high_confidence_research, {})

    # Load it back
    loaded_review = workflow.load_review(high_confidence_research.session_id)

    assert loaded_review is not None
    assert loaded_review.decision == original_review.decision
    assert loaded_review.research_session_id == original_review.research_session_id


def test_submit_review(review_config):
    """Test submitting a human review."""
    workflow = ResearchReviewWorkflow(config=review_config)

    review = workflow.submit_review(
        session_id="test_123",
        decision=ReviewDecision.APPROVED,
        reviewer="john_doe",
        comments="Looks good to me",
        approved_findings=["Finding 1", "Finding 2"],
    )

    assert review.decision == ReviewDecision.APPROVED
    assert review.reviewer == "john_doe"
    assert len(review.approved_findings) == 2


def test_generate_review_questions(review_config, low_confidence_research):
    """Test generation of review questions."""
    workflow = ResearchReviewWorkflow(config=review_config)
    questions = workflow._generate_review_questions(low_confidence_research)

    assert len(questions) > 0
    assert any("confidence" in q.lower() for q in questions)


def test_should_auto_approve_criteria(review_config):
    """Test auto-approval criteria."""
    workflow = ResearchReviewWorkflow(config=review_config)

    # High confidence, sufficient findings, success
    good_result = ResearchPhaseResult(
        success=True,
        session_id="good_123",
        query="test",
        findings=["F1", "F2", "F3"],
        recommendations=[],
        confidence_score=0.95,
        iterations_used=3,
        duration_seconds=10.0,
    )
    assert workflow._should_auto_approve(good_result)

    # Low confidence
    low_conf_result = ResearchPhaseResult(
        success=True,
        session_id="low_123",
        query="test",
        findings=["F1", "F2"],
        recommendations=[],
        confidence_score=0.6,
        iterations_used=3,
        duration_seconds=10.0,
    )
    assert not workflow._should_auto_approve(low_conf_result)

    # Insufficient findings
    few_findings_result = ResearchPhaseResult(
        success=True,
        session_id="few_123",
        query="test",
        findings=["F1"],
        recommendations=[],
        confidence_score=0.95,
        iterations_used=3,
        duration_seconds=10.0,
    )
    assert not workflow._should_auto_approve(few_findings_result)

    # Not successful
    failed_result = ResearchPhaseResult(
        success=False,
        session_id="fail_123",
        query="test",
        findings=["F1", "F2"],
        recommendations=[],
        confidence_score=0.95,
        iterations_used=3,
        duration_seconds=10.0,
    )
    assert not workflow._should_auto_approve(failed_result)
