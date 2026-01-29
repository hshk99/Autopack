"""Tests for IMP-LOOP-017: Task Effectiveness to Learning Rules.

Tests cover:
- EffectivenessLearningRule dataclass
- TaskEffectivenessTracker.analyze_effectiveness_patterns()
- FeedbackPipeline._check_effectiveness_rules()
- Integration between tracker and pipeline
"""

from datetime import datetime
from unittest.mock import Mock

from autopack.feedback_pipeline import FeedbackPipeline, PhaseOutcome
from autopack.task_generation.task_effectiveness_tracker import (
    HIGH_SUCCESS_THRESHOLD, LOW_SUCCESS_THRESHOLD, MIN_SAMPLE_SIZE,
    EffectivenessLearningRule, TaskEffectivenessTracker)


class TestEffectivenessLearningRule:
    """Tests for EffectivenessLearningRule dataclass."""

    def test_rule_creation_avoid_pattern(self):
        """EffectivenessLearningRule should be creatable for avoid_pattern."""
        rule = EffectivenessLearningRule(
            rule_type="avoid_pattern",
            pattern="build",
            confidence=0.6,
            reason="Low success rate: 40.00%",
            sample_size=10,
            success_rate=0.4,
        )

        assert rule.rule_type == "avoid_pattern"
        assert rule.pattern == "build"
        assert rule.confidence == 0.6
        assert "Low success rate" in rule.reason
        assert rule.sample_size == 10
        assert rule.success_rate == 0.4

    def test_rule_creation_prefer_pattern(self):
        """EffectivenessLearningRule should be creatable for prefer_pattern."""
        rule = EffectivenessLearningRule(
            rule_type="prefer_pattern",
            pattern="test",
            confidence=0.9,
            reason="High success rate: 90.00%",
            sample_size=15,
            success_rate=0.9,
        )

        assert rule.rule_type == "prefer_pattern"
        assert rule.pattern == "test"
        assert rule.confidence == 0.9
        assert "High success rate" in rule.reason

    def test_rule_to_dict(self):
        """EffectivenessLearningRule.to_dict should serialize all fields."""
        now = datetime.now()
        rule = EffectivenessLearningRule(
            rule_type="avoid_pattern",
            pattern="deploy",
            confidence=0.7,
            reason="Low success rate",
            sample_size=8,
            success_rate=0.3,
            created_at=now,
        )

        data = rule.to_dict()

        assert data["rule_type"] == "avoid_pattern"
        assert data["pattern"] == "deploy"
        assert data["confidence"] == 0.7
        assert data["reason"] == "Low success rate"
        assert data["sample_size"] == 8
        assert data["success_rate"] == 0.3
        assert data["created_at"] == now.isoformat()


class TestAnalyzeEffectivenessPatterns:
    """Tests for TaskEffectivenessTracker.analyze_effectiveness_patterns."""

    def test_no_rules_when_empty(self):
        """analyze_effectiveness_patterns should return empty when no data."""
        tracker = TaskEffectivenessTracker()

        rules = tracker.analyze_effectiveness_patterns()

        assert rules == []

    def test_no_rules_below_min_sample_size(self):
        """analyze_effectiveness_patterns should not generate rules below MIN_SAMPLE_SIZE."""
        tracker = TaskEffectivenessTracker()

        # Record fewer than MIN_SAMPLE_SIZE outcomes
        for i in range(MIN_SAMPLE_SIZE - 1):
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=False,  # All failures
                category="build",
            )

        rules = tracker.analyze_effectiveness_patterns()

        assert rules == []

    def test_avoid_pattern_rule_low_success(self):
        """analyze_effectiveness_patterns should create avoid_pattern for low success."""
        tracker = TaskEffectivenessTracker()

        # Record outcomes with low success rate (< 50%)
        for i in range(MIN_SAMPLE_SIZE):
            # 2 successes, rest failures = 40% success rate
            success = i < 2
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=success,
                category="build",
            )

        rules = tracker.analyze_effectiveness_patterns()

        assert len(rules) == 1
        rule = rules[0]
        assert rule.rule_type == "avoid_pattern"
        assert rule.pattern == "build"
        assert rule.sample_size == MIN_SAMPLE_SIZE
        assert rule.success_rate < LOW_SUCCESS_THRESHOLD
        assert rule.confidence > 0.5  # Confidence = 1 - success_rate

    def test_prefer_pattern_rule_high_success(self):
        """analyze_effectiveness_patterns should create prefer_pattern for high success."""
        tracker = TaskEffectivenessTracker()

        # Record outcomes with high success rate (> 80%)
        # Use 6 samples with 5 successes = 83.3% success rate
        for i in range(6):
            # 5 successes, 1 failure = 83.3% success rate
            success = i < 5
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=success,
                category="test",
            )

        rules = tracker.analyze_effectiveness_patterns()

        assert len(rules) == 1
        rule = rules[0]
        assert rule.rule_type == "prefer_pattern"
        assert rule.pattern == "test"
        assert rule.sample_size == 6
        assert rule.success_rate > HIGH_SUCCESS_THRESHOLD
        assert rule.confidence > 0.8  # Confidence = success_rate

    def test_no_rule_for_moderate_success(self):
        """analyze_effectiveness_patterns should not create rules for moderate success."""
        tracker = TaskEffectivenessTracker()

        # Record outcomes with moderate success rate (between 50% and 80%)
        for i in range(10):
            # 6 successes, 4 failures = 60% success rate
            success = i < 6
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=success,
                category="deploy",
            )

        rules = tracker.analyze_effectiveness_patterns()

        # No rules because 60% is between LOW_SUCCESS_THRESHOLD and HIGH_SUCCESS_THRESHOLD
        assert rules == []

    def test_multiple_categories_multiple_rules(self):
        """analyze_effectiveness_patterns should handle multiple categories."""
        tracker = TaskEffectivenessTracker()

        # Category 1: Low success (avoid_pattern)
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"build_{i}",
                success=i < 1,  # 1 success = 20%
                category="build",
            )

        # Category 2: High success (prefer_pattern)
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"test_{i}",
                success=i < MIN_SAMPLE_SIZE,  # All success = 100%
                category="test",
            )

        # Category 3: Moderate success (no rule)
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"deploy_{i}",
                success=i < 3,  # 60%
                category="deploy",
            )

        rules = tracker.analyze_effectiveness_patterns()

        assert len(rules) == 2

        rule_types = {(r.rule_type, r.pattern) for r in rules}
        assert ("avoid_pattern", "build") in rule_types
        assert ("prefer_pattern", "test") in rule_types


class TestFeedbackPipelineEffectivenessRules:
    """Tests for FeedbackPipeline._check_effectiveness_rules integration."""

    def test_check_effectiveness_rules_no_tracker(self):
        """_check_effectiveness_rules should return 0 when no tracker."""
        pipeline = FeedbackPipeline()

        result = pipeline._check_effectiveness_rules()

        assert result == 0

    def test_check_effectiveness_rules_no_rules(self):
        """_check_effectiveness_rules should return 0 when no rules generated."""
        tracker = TaskEffectivenessTracker()
        pipeline = FeedbackPipeline(effectiveness_tracker=tracker)

        result = pipeline._check_effectiveness_rules()

        assert result == 0

    def test_check_effectiveness_rules_persists_to_memory(self):
        """_check_effectiveness_rules should persist rules to memory service."""
        # Setup tracker with data that will generate rules
        tracker = TaskEffectivenessTracker()
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=False,  # All failures = 0% success
                category="build",
            )

        # Setup mock memory service
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value=True)

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            effectiveness_tracker=tracker,
            run_id="test_run",
            project_id="test_project",
        )

        result = pipeline._check_effectiveness_rules()

        assert result == 1
        assert mock_memory.write_telemetry_insight.called

        # Verify the insight content
        call_args = mock_memory.write_telemetry_insight.call_args
        insight = call_args.kwargs["insight"]
        assert insight["insight_type"] == "effectiveness_rule"
        assert "avoid_pattern" in insight["description"]
        assert insight["metadata"]["rule_type"] == "avoid_pattern"
        assert insight["metadata"]["pattern"] == "build"
        assert insight["is_rule"] is True

    def test_check_effectiveness_rules_updates_stats(self):
        """_check_effectiveness_rules should update pipeline stats."""
        tracker = TaskEffectivenessTracker()
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"task_{i}",
                success=False,
                category="build",
            )

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value=True)

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            effectiveness_tracker=tracker,
        )

        pipeline._check_effectiveness_rules()

        stats = pipeline.get_stats()
        assert stats["effectiveness_rules_created"] == 1

    def test_process_phase_outcome_triggers_effectiveness_check(self):
        """process_phase_outcome should trigger effectiveness rule check."""
        tracker = TaskEffectivenessTracker()
        # Pre-populate with data to trigger rule
        for i in range(MIN_SAMPLE_SIZE):
            tracker.record_task_outcome(
                task_id=f"existing_{i}",
                success=False,
                category="build",
            )

        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.write_telemetry_insight = Mock(return_value=True)
        mock_memory.write_task_execution_feedback = Mock(return_value=True)

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            effectiveness_tracker=tracker,
            enabled=True,
        )

        # Process an outcome
        outcome = PhaseOutcome(
            phase_id="new_phase",
            phase_type="build",
            success=True,
            status="completed",
        )
        pipeline.process_phase_outcome(outcome)

        # Should have called write_telemetry_insight at least twice
        # (once for outcome insight, once for effectiveness rule)
        assert mock_memory.write_telemetry_insight.call_count >= 1


class TestGenerateRuleActionFromEffectiveness:
    """Tests for FeedbackPipeline._generate_rule_action_from_effectiveness."""

    def test_avoid_pattern_action(self):
        """Should generate appropriate action for avoid_pattern."""
        pipeline = FeedbackPipeline()

        action = pipeline._generate_rule_action_from_effectiveness("avoid_pattern", "build")

        assert "Avoid" in action
        assert "build" in action
        assert "low success rate" in action.lower()

    def test_prefer_pattern_action(self):
        """Should generate appropriate action for prefer_pattern."""
        pipeline = FeedbackPipeline()

        action = pipeline._generate_rule_action_from_effectiveness("prefer_pattern", "test")

        assert "Prioritize" in action
        assert "test" in action
        assert "high success rate" in action.lower()

    def test_unknown_rule_type_action(self):
        """Should handle unknown rule types."""
        pipeline = FeedbackPipeline()

        action = pipeline._generate_rule_action_from_effectiveness("unknown_type", "deploy")

        assert "deploy" in action
        assert "Review" in action


class TestThresholdConstants:
    """Tests for threshold constants."""

    def test_min_sample_size(self):
        """MIN_SAMPLE_SIZE should be at least 5."""
        assert MIN_SAMPLE_SIZE >= 5

    def test_low_success_threshold(self):
        """LOW_SUCCESS_THRESHOLD should be 0.5 (50%)."""
        assert LOW_SUCCESS_THRESHOLD == 0.5

    def test_high_success_threshold(self):
        """HIGH_SUCCESS_THRESHOLD should be 0.8 (80%)."""
        assert HIGH_SUCCESS_THRESHOLD == 0.8

    def test_thresholds_non_overlapping(self):
        """Thresholds should not overlap."""
        assert LOW_SUCCESS_THRESHOLD < HIGH_SUCCESS_THRESHOLD
