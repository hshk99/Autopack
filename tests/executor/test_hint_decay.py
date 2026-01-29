"""
Tests for IMP-MEM-004: Apply decay score during hint retrieval

Tests the integration of calculate_decay_score() into hint retrieval,
ensuring old hints are filtered out and fresh hints are prioritized.
"""

import time

from autopack.executor.learning_pipeline import LearningHint, LearningPipeline


class TestGetHintsWithDecayFiltering:
    """Test get_hints_for_phase() with decay filtering"""

    def test_fresh_hints_included(self):
        """Test fresh hints pass decay threshold"""
        pipeline = LearningPipeline(run_id="test-run")

        # Record fresh hint
        phase = {"phase_id": "test-phase", "task_category": "refactoring"}
        pipeline.record_hint(phase, "ci_fail", "Fresh hint details")

        # Retrieve hints - fresh should pass default threshold (0.3)
        hints = pipeline.get_hints_for_phase(phase)
        assert len(hints) == 1
        assert "Fresh hint" in hints[0]

    def test_old_hints_filtered_out(self):
        """Test old hints below decay threshold are filtered"""
        pipeline = LearningPipeline(run_id="test-run")

        # Create an old hint directly (2 weeks old)
        two_weeks_ago = time.time() - (336 * 3600)
        old_hint = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Old hint that should be filtered",
            source_issue_keys=[],
            recorded_at=two_weeks_ago,
            confidence=0.5,
        )
        pipeline._hints.append(old_hint)

        # Also add a fresh hint
        fresh_hint = LearningHint(
            phase_id="test-phase",
            hint_type="auditor_reject",
            hint_text="Fresh hint that should remain",
            source_issue_keys=[],
            recorded_at=time.time(),
            confidence=0.5,
        )
        pipeline._hints.append(fresh_hint)

        phase = {"phase_id": "test-phase"}
        hints = pipeline.get_hints_for_phase(phase)

        # Only fresh hint should remain
        assert len(hints) == 1
        assert "Fresh hint" in hints[0]
        assert "Old hint" not in str(hints)

    def test_custom_decay_threshold(self):
        """Test custom decay threshold parameter"""
        pipeline = LearningPipeline(run_id="test-run")

        # Create hint at half-life (84 hours, decay ~0.5)
        half_week_ago = time.time() - (84 * 3600)
        mid_age_hint = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Mid-age hint",
            source_issue_keys=[],
            recorded_at=half_week_ago,
            confidence=1.0,
        )
        pipeline._hints.append(mid_age_hint)

        phase = {"phase_id": "test-phase"}

        # With default threshold (0.3), should be included
        hints_default = pipeline.get_hints_for_phase(phase, decay_threshold=0.3)
        assert len(hints_default) == 1

        # With high threshold (0.7), should be filtered
        hints_high = pipeline.get_hints_for_phase(phase, decay_threshold=0.7)
        assert len(hints_high) == 0

    def test_hints_sorted_by_decay_score(self):
        """Test hints are sorted by decay score, not just confidence"""
        pipeline = LearningPipeline(run_id="test-run")

        # Create old hint with high confidence
        one_week_ago = time.time() - (168 * 3600)
        old_high_conf = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Old but high confidence",
            source_issue_keys=[],
            recorded_at=one_week_ago,
            confidence=1.0,  # High confidence but old
        )
        pipeline._hints.append(old_high_conf)

        # Create fresh hint with lower confidence
        fresh_low_conf = LearningHint(
            phase_id="test-phase",
            hint_type="auditor_reject",
            hint_text="Fresh but lower confidence",
            source_issue_keys=[],
            recorded_at=time.time(),
            confidence=0.5,  # Lower confidence but fresh
        )
        pipeline._hints.append(fresh_low_conf)

        phase = {"phase_id": "test-phase"}
        hints = pipeline.get_hints_for_phase(phase, decay_threshold=0.05)

        # Fresh hint should come first despite lower confidence
        # because decay score prioritizes recency
        assert len(hints) == 2
        assert "Fresh" in hints[0]

    def test_decay_threshold_zero_returns_all(self):
        """Test decay threshold of 0 returns all hints"""
        pipeline = LearningPipeline(run_id="test-run")

        # Create very old hint
        very_old = time.time() - (500 * 3600)
        old_hint = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Very old hint",
            source_issue_keys=[],
            recorded_at=very_old,
            confidence=0.5,
        )
        pipeline._hints.append(old_hint)

        phase = {"phase_id": "test-phase"}
        hints = pipeline.get_hints_for_phase(phase, decay_threshold=0.0)

        # Should include hint even though very old
        assert len(hints) == 1


class TestGetHintsWithDecayScores:
    """Test get_hints_with_decay_scores() method"""

    def test_returns_tuples_with_scores(self):
        """Test method returns (hint_text, decay_score) tuples"""
        pipeline = LearningPipeline(run_id="test-run")

        fresh_hint = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Test hint",
            source_issue_keys=[],
            recorded_at=time.time(),
            confidence=0.8,
        )
        pipeline._hints.append(fresh_hint)

        phase = {"phase_id": "test-phase"}
        hints_with_scores = pipeline.get_hints_with_decay_scores(phase)

        assert len(hints_with_scores) == 1
        hint_text, score = hints_with_scores[0]
        assert "Test hint" in hint_text
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_scores_reflect_decay(self):
        """Test decay scores accurately reflect hint age"""
        pipeline = LearningPipeline(run_id="test-run")

        # Fresh hint
        fresh_hint = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Fresh",
            source_issue_keys=[],
            recorded_at=time.time(),
            confidence=1.0,
        )
        pipeline._hints.append(fresh_hint)

        # Older hint
        half_week_ago = time.time() - (84 * 3600)
        older_hint = LearningHint(
            phase_id="test-phase",
            hint_type="auditor_reject",
            hint_text="Older",
            source_issue_keys=[],
            recorded_at=half_week_ago,
            confidence=1.0,
        )
        pipeline._hints.append(older_hint)

        phase = {"phase_id": "test-phase"}
        hints_with_scores = pipeline.get_hints_with_decay_scores(phase, decay_threshold=0.0)

        # Find scores by hint text
        {text: score for text, score in hints_with_scores}
        assert "Fresh" in str(hints_with_scores)
        assert "Older" in str(hints_with_scores)

        # Fresh hint should have higher score
        fresh_score = next(s for t, s in hints_with_scores if "Fresh" in t)
        older_score = next(s for t, s in hints_with_scores if "Older" in t)
        assert fresh_score > older_score

    def test_empty_hints_returns_empty_list(self):
        """Test empty pipeline returns empty list"""
        pipeline = LearningPipeline(run_id="test-run")
        phase = {"phase_id": "test-phase"}

        hints_with_scores = pipeline.get_hints_with_decay_scores(phase)
        assert hints_with_scores == []


class TestDecayFilteringIntegration:
    """Integration tests for decay filtering in hint retrieval"""

    def test_category_matching_with_decay(self):
        """Test category matching still works with decay filtering"""
        pipeline = LearningPipeline(run_id="test-run")

        # Add hint with task_category
        hint = LearningHint(
            phase_id="other-phase",
            hint_type="ci_fail",
            hint_text="Category-matched hint",
            source_issue_keys=[],
            recorded_at=time.time(),
            task_category="refactoring",
            confidence=0.7,
        )
        pipeline._hints.append(hint)

        # Query with matching category
        phase = {"phase_id": "test-phase", "task_category": "refactoring"}
        hints = pipeline.get_hints_for_phase(phase)

        assert len(hints) == 1
        assert "Category-matched" in hints[0]

    def test_max_hints_limit_applies(self):
        """Test max hints limit (10) still applies after decay filtering"""
        pipeline = LearningPipeline(run_id="test-run")

        # Add 15 fresh hints
        for i in range(15):
            hint = LearningHint(
                phase_id="test-phase",
                hint_type="ci_fail",
                hint_text=f"Hint {i}",
                source_issue_keys=[],
                recorded_at=time.time(),
                confidence=0.8,
            )
            pipeline._hints.append(hint)

        phase = {"phase_id": "test-phase"}
        hints = pipeline.get_hints_for_phase(phase)

        # Should be limited to 10
        assert len(hints) == 10

    def test_validation_failures_affect_filtering(self):
        """Test hints with many validation failures get lower scores"""
        pipeline = LearningPipeline(run_id="test-run")

        # Fresh hint with failures
        hint_with_failures = LearningHint(
            phase_id="test-phase",
            hint_type="ci_fail",
            hint_text="Hint with failures",
            source_issue_keys=[],
            recorded_at=time.time(),
            confidence=0.5,
            validation_failures=5,  # 0.5 penalty
        )
        pipeline._hints.append(hint_with_failures)

        phase = {"phase_id": "test-phase"}

        # With threshold 0.3, hint with 0.5 conf and 0.5 penalty = 0.0 should be filtered
        hints = pipeline.get_hints_for_phase(phase, decay_threshold=0.1)
        assert len(hints) == 0
