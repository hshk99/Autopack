"""Tests for IMP-LOOP-014: Human approval feedback capture and analysis.

Tests the ApprovalFeedbackAnalyzer implementation for capturing human
decisions on tasks and analyzing patterns to improve task generation.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from autopack.approvals.feedback_analyzer import (
    ApprovalFeedback,
    ApprovalFeedbackAnalyzer,
    HumanAction,
    PriorityWeightUpdate,
    RejectionPattern,
)


class TestHumanAction:
    """Tests for HumanAction enum."""

    def test_action_values(self):
        """HumanAction should have expected values."""
        assert HumanAction.APPROVE.value == "approve"
        assert HumanAction.REJECT.value == "reject"
        assert HumanAction.MODIFY.value == "modify"

    def test_action_is_string_enum(self):
        """HumanAction should be a string enum."""
        assert isinstance(HumanAction.APPROVE, str)
        assert HumanAction.APPROVE == "approve"


class TestApprovalFeedback:
    """Tests for ApprovalFeedback dataclass."""

    def test_create_minimal_feedback(self):
        """Should create feedback with minimal required fields."""
        feedback = ApprovalFeedback(
            task_id="task-001",
            action=HumanAction.APPROVE,
            feedback_text=None,
            reasoning={},
            recorded_at=datetime.now(timezone.utc),
        )

        assert feedback.task_id == "task-001"
        assert feedback.action == HumanAction.APPROVE
        assert feedback.reasoning == {}
        assert feedback.task_type is None
        assert feedback.priority_score is None

    def test_create_full_feedback(self):
        """Should create feedback with all fields."""
        now = datetime.now(timezone.utc)
        feedback = ApprovalFeedback(
            task_id="task-002",
            action=HumanAction.REJECT,
            feedback_text="Task is too broad",
            reasoning={"scope": "too_large", "effort": "excessive"},
            recorded_at=now,
            task_type="improvement",
            priority_score=0.75,
            modifications=None,
        )

        assert feedback.task_id == "task-002"
        assert feedback.action == HumanAction.REJECT
        assert feedback.feedback_text == "Task is too broad"
        assert feedback.reasoning == {"scope": "too_large", "effort": "excessive"}
        assert feedback.task_type == "improvement"
        assert feedback.priority_score == 0.75

    def test_create_modification_feedback(self):
        """Should create feedback for modifications."""
        feedback = ApprovalFeedback(
            task_id="task-003",
            action=HumanAction.MODIFY,
            feedback_text="Reduced scope",
            reasoning={"scope": "adjusted"},
            recorded_at=datetime.now(timezone.utc),
            modifications={"scope": {"old": "large", "new": "small"}},
        )

        assert feedback.action == HumanAction.MODIFY
        assert feedback.modifications == {"scope": {"old": "large", "new": "small"}}


class TestApprovalFeedbackAnalyzer:
    """Tests for ApprovalFeedbackAnalyzer class."""

    @pytest.fixture
    def analyzer(self) -> ApprovalFeedbackAnalyzer:
        """Create a fresh analyzer for each test."""
        return ApprovalFeedbackAnalyzer(max_feedback_history=100, min_pattern_occurrences=2)

    def test_init_default_values(self):
        """Analyzer should initialize with default values."""
        analyzer = ApprovalFeedbackAnalyzer()
        weights = analyzer.get_priority_weights()

        assert weights["impact"] == 1.0
        assert weights["urgency"] == 1.0
        assert weights["effort"] == 1.0
        assert weights["risk"] == 1.0
        assert weights["dependencies"] == 1.0

    def test_capture_feedback_approve(self, analyzer):
        """Should capture approval feedback."""
        feedback = analyzer.capture_feedback(
            task_id="task-001",
            action=HumanAction.APPROVE,
            feedback_text="Looks good",
            reasoning={"quality": "high"},
        )

        assert feedback.task_id == "task-001"
        assert feedback.action == HumanAction.APPROVE
        assert feedback.recorded_at is not None
        assert feedback.reasoning == {"quality": "high"}

    def test_capture_feedback_reject(self, analyzer):
        """Should capture rejection feedback."""
        feedback = analyzer.capture_feedback(
            task_id="task-002",
            action=HumanAction.REJECT,
            feedback_text="Scope too large",
            reasoning={"scope": "too_large"},
        )

        assert feedback.task_id == "task-002"
        assert feedback.action == HumanAction.REJECT
        assert feedback.feedback_text == "Scope too large"

    def test_capture_feedback_modify(self, analyzer):
        """Should capture modification feedback."""
        feedback = analyzer.capture_feedback(
            task_id="task-003",
            action=HumanAction.MODIFY,
            reasoning={"priority": "adjusted"},
            modifications={"priority": {"old": 1, "new": 5}},
        )

        assert feedback.action == HumanAction.MODIFY
        assert feedback.modifications == {"priority": {"old": 1, "new": 5}}

    def test_capture_feedback_updates_stats(self, analyzer):
        """Capturing feedback should update statistics."""
        analyzer.capture_feedback(task_id="task-001", action=HumanAction.APPROVE, reasoning={})
        analyzer.capture_feedback(task_id="task-002", action=HumanAction.REJECT, reasoning={})
        analyzer.capture_feedback(task_id="task-003", action=HumanAction.MODIFY, reasoning={})

        summary = analyzer.get_feedback_summary()
        assert summary["total_feedback"] == 3
        assert summary["approval_rate"] == pytest.approx(1 / 3)
        assert summary["rejection_rate"] == pytest.approx(1 / 3)
        assert summary["modification_rate"] == pytest.approx(1 / 3)

    def test_history_limit_enforced(self):
        """Should enforce max history limit."""
        analyzer = ApprovalFeedbackAnalyzer(max_feedback_history=5)

        for i in range(10):
            analyzer.capture_feedback(task_id=f"task-{i}", action=HumanAction.APPROVE, reasoning={})

        summary = analyzer.get_feedback_summary()
        assert summary["total_feedback"] == 5

    def test_analyze_rejection_patterns_empty(self, analyzer):
        """Should return empty list when no rejections."""
        patterns = analyzer.analyze_rejection_patterns()
        assert patterns == []

    def test_analyze_rejection_patterns_insufficient_data(self, analyzer):
        """Should not identify patterns with insufficient occurrences."""
        analyzer.capture_feedback(
            task_id="task-001",
            action=HumanAction.REJECT,
            reasoning={"scope": "too_large"},
        )

        patterns = analyzer.analyze_rejection_patterns()
        assert patterns == []  # min_pattern_occurrences=2

    def test_analyze_rejection_patterns_identifies_pattern(self, analyzer):
        """Should identify patterns with sufficient occurrences."""
        # Add multiple rejections with same reason
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"task-{i}",
                action=HumanAction.REJECT,
                reasoning={"scope": "too_large"},
            )

        patterns = analyzer.analyze_rejection_patterns()

        assert len(patterns) == 1
        assert patterns[0].pattern_type == "scope"
        assert patterns[0].occurrence_count == 3
        assert len(patterns[0].example_task_ids) == 3

    def test_analyze_rejection_patterns_multiple_patterns(self, analyzer):
        """Should identify multiple patterns."""
        # Add rejections with different reasons
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"task-scope-{i}",
                action=HumanAction.REJECT,
                reasoning={"scope": "too_large"},
            )
        for i in range(2):
            analyzer.capture_feedback(
                task_id=f"task-effort-{i}",
                action=HumanAction.REJECT,
                reasoning={"effort": "excessive"},
            )

        patterns = analyzer.analyze_rejection_patterns()

        assert len(patterns) == 2
        # Sorted by occurrence count
        assert patterns[0].occurrence_count == 3
        assert patterns[1].occurrence_count == 2

    def test_analyze_rejection_patterns_confidence(self, analyzer):
        """Pattern confidence should reflect occurrence ratio."""
        # 3 scope rejections out of 4 total rejections
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"task-scope-{i}",
                action=HumanAction.REJECT,
                reasoning={"scope": "too_large"},
            )
        analyzer.capture_feedback(
            task_id="task-other",
            action=HumanAction.REJECT,
            reasoning={"other": "reason"},
        )

        patterns = analyzer.analyze_rejection_patterns()

        scope_pattern = patterns[0]
        assert scope_pattern.confidence == pytest.approx(0.75)

    def test_analyze_modification_patterns(self, analyzer):
        """Should identify modification patterns."""
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"task-{i}",
                action=HumanAction.MODIFY,
                reasoning={},
                modifications={"priority": {"old": 1, "new": 5}},
            )

        patterns = analyzer.analyze_modification_patterns()

        assert len(patterns) == 1
        assert patterns[0]["field"] == "priority"
        assert patterns[0]["modification_count"] == 3

    def test_update_priority_engine_weights(self, analyzer):
        """Should update weights based on patterns."""
        # Create a pattern manually
        pattern = RejectionPattern(
            pattern_type="scope",
            description="Tasks too broad",
            occurrence_count=5,
            example_task_ids=["t1", "t2"],
            suggested_adjustment="Reduce scope threshold",
            confidence=0.8,
        )

        initial_weights = analyzer.get_priority_weights().copy()
        updates = analyzer.update_priority_engine_weights([pattern])

        assert len(updates) == 1
        assert updates[0].weight_name == "effort"  # scope maps to effort
        assert updates[0].current_value == initial_weights["effort"]
        assert updates[0].suggested_value != initial_weights["effort"]

        # Verify weight was actually updated
        new_weights = analyzer.get_priority_weights()
        assert new_weights["effort"] != initial_weights["effort"]

    def test_update_priority_engine_weights_bounds(self, analyzer):
        """Weight updates should respect bounds."""
        # Create pattern with high confidence to force large adjustment
        pattern = RejectionPattern(
            pattern_type="scope",
            description="Tasks too broad",
            occurrence_count=100,
            example_task_ids=["t1"],
            suggested_adjustment="Reduce scope",
            confidence=1.0,
        )

        # Apply multiple times to test bounds
        for _ in range(50):
            analyzer.update_priority_engine_weights([pattern])

        weights = analyzer.get_priority_weights()
        assert weights["effort"] >= 0.1  # Min bound

    def test_get_approval_rate_empty(self, analyzer):
        """Approval rate should be 0.0 when no data."""
        rate = analyzer.get_approval_rate()
        assert rate == 0.0

    def test_get_approval_rate_all_approved(self, analyzer):
        """Approval rate should be 1.0 when all approved."""
        for i in range(5):
            analyzer.capture_feedback(task_id=f"task-{i}", action=HumanAction.APPROVE, reasoning={})

        rate = analyzer.get_approval_rate()
        assert rate == 1.0

    def test_get_approval_rate_mixed(self, analyzer):
        """Approval rate should reflect mix of decisions."""
        analyzer.capture_feedback(task_id="task-1", action=HumanAction.APPROVE, reasoning={})
        analyzer.capture_feedback(task_id="task-2", action=HumanAction.REJECT, reasoning={})
        analyzer.capture_feedback(task_id="task-3", action=HumanAction.APPROVE, reasoning={})
        analyzer.capture_feedback(task_id="task-4", action=HumanAction.MODIFY, reasoning={})

        rate = analyzer.get_approval_rate()
        assert rate == pytest.approx(0.5)  # 2 out of 4

    def test_get_approval_rate_by_task_type(self, analyzer):
        """Should filter approval rate by task type."""
        analyzer.capture_feedback(
            task_id="task-1",
            action=HumanAction.APPROVE,
            reasoning={},
            task_type="improvement",
        )
        analyzer.capture_feedback(
            task_id="task-2",
            action=HumanAction.REJECT,
            reasoning={},
            task_type="improvement",
        )
        analyzer.capture_feedback(
            task_id="task-3",
            action=HumanAction.APPROVE,
            reasoning={},
            task_type="bugfix",
        )

        improvement_rate = analyzer.get_approval_rate(task_type="improvement")
        bugfix_rate = analyzer.get_approval_rate(task_type="bugfix")

        assert improvement_rate == pytest.approx(0.5)
        assert bugfix_rate == 1.0

    def test_reset_weights(self, analyzer):
        """Should reset weights to defaults."""
        # Modify weights
        pattern = RejectionPattern(
            pattern_type="scope",
            description="Test",
            occurrence_count=5,
            example_task_ids=[],
            suggested_adjustment="Test",
            confidence=0.9,
        )
        analyzer.update_priority_engine_weights([pattern])

        # Verify weights changed
        weights = analyzer.get_priority_weights()
        assert weights["effort"] != 1.0

        # Reset
        analyzer.reset_weights()
        weights = analyzer.get_priority_weights()
        assert weights["effort"] == 1.0
        assert weights["impact"] == 1.0

    def test_clear_history(self, analyzer):
        """Should clear feedback history."""
        for i in range(5):
            analyzer.capture_feedback(task_id=f"task-{i}", action=HumanAction.APPROVE, reasoning={})

        count = analyzer.clear_history()
        assert count == 5

        summary = analyzer.get_feedback_summary()
        assert summary["total_feedback"] == 0

    def test_get_feedback_summary_empty(self, analyzer):
        """Summary should handle empty history."""
        summary = analyzer.get_feedback_summary()

        assert summary["total_feedback"] == 0
        assert summary["approval_rate"] == 0.0
        assert summary["rejection_rate"] == 0.0
        assert summary["modification_rate"] == 0.0


class TestRejectionPattern:
    """Tests for RejectionPattern dataclass."""

    def test_create_pattern(self):
        """Should create rejection pattern with all fields."""
        pattern = RejectionPattern(
            pattern_type="scope",
            description="Tasks have scope that is too broad",
            occurrence_count=5,
            example_task_ids=["t1", "t2", "t3"],
            suggested_adjustment="Reduce task scope threshold",
            confidence=0.75,
        )

        assert pattern.pattern_type == "scope"
        assert pattern.occurrence_count == 5
        assert len(pattern.example_task_ids) == 3
        assert pattern.confidence == 0.75


class TestPriorityWeightUpdate:
    """Tests for PriorityWeightUpdate dataclass."""

    def test_create_update(self):
        """Should create weight update with all fields."""
        update = PriorityWeightUpdate(
            weight_name="effort",
            current_value=1.0,
            suggested_value=0.8,
            adjustment_reason="Reduce effort weighting due to scope patterns",
            supporting_patterns=["scope", "effort"],
        )

        assert update.weight_name == "effort"
        assert update.current_value == 1.0
        assert update.suggested_value == 0.8
        assert len(update.supporting_patterns) == 2


class TestPatternDescriptions:
    """Tests for pattern description generation."""

    @pytest.fixture
    def analyzer(self) -> ApprovalFeedbackAnalyzer:
        return ApprovalFeedbackAnalyzer(min_pattern_occurrences=1)

    def test_scope_too_large_description(self, analyzer):
        """Should generate description for scope too large pattern."""
        analyzer.capture_feedback(
            task_id="task-1",
            action=HumanAction.REJECT,
            reasoning={"scope": "too_large"},
        )

        patterns = analyzer.analyze_rejection_patterns()

        assert "broad" in patterns[0].description.lower()

    def test_effort_excessive_description(self, analyzer):
        """Should generate description for effort excessive pattern."""
        analyzer.capture_feedback(
            task_id="task-1",
            action=HumanAction.REJECT,
            reasoning={"effort": "excessive"},
        )

        patterns = analyzer.analyze_rejection_patterns()

        assert "effort" in patterns[0].description.lower()

    def test_unknown_pattern_fallback_description(self, analyzer):
        """Should provide fallback description for unknown patterns."""
        analyzer.capture_feedback(
            task_id="task-1",
            action=HumanAction.REJECT,
            reasoning={"unknown_category": "unknown_value"},
        )

        patterns = analyzer.analyze_rejection_patterns()

        assert "unknown_category" in patterns[0].description
        assert "unknown_value" in patterns[0].description


class TestIntegration:
    """Integration tests for the full feedback loop."""

    def test_full_feedback_loop(self):
        """Test complete feedback capture -> analysis -> weight update flow."""
        analyzer = ApprovalFeedbackAnalyzer(min_pattern_occurrences=2)

        # Simulate user feedback over time
        # Tasks with scope issues are consistently rejected
        for i in range(5):
            analyzer.capture_feedback(
                task_id=f"scope-task-{i}",
                action=HumanAction.REJECT,
                feedback_text="Task scope is too broad",
                reasoning={"scope": "too_large"},
                task_type="improvement",
            )

        # Some tasks are approved
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"good-task-{i}",
                action=HumanAction.APPROVE,
                reasoning={"quality": "good"},
                task_type="improvement",
            )

        # Analyze patterns
        patterns = analyzer.analyze_rejection_patterns()
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "scope"
        assert patterns[0].occurrence_count == 5

        # Update weights based on patterns
        updates = analyzer.update_priority_engine_weights(patterns)
        assert len(updates) == 1

        # Verify weights changed
        weights = analyzer.get_priority_weights()
        assert weights["effort"] < 1.0  # Decreased due to scope issues

        # Check summary
        summary = analyzer.get_feedback_summary()
        assert summary["total_feedback"] == 8
        assert summary["rejection_rate"] == pytest.approx(5 / 8)
        assert summary["patterns_identified"] == 1
        assert summary["weight_updates_applied"] == 1

    def test_feedback_improves_over_time(self):
        """Test that applying feedback improves approval rates."""
        analyzer = ApprovalFeedbackAnalyzer(min_pattern_occurrences=2)

        # Phase 1: Initial poor approval rate due to scope issues
        for i in range(4):
            analyzer.capture_feedback(
                task_id=f"p1-{i}",
                action=HumanAction.REJECT,
                reasoning={"scope": "too_large"},
            )
        analyzer.capture_feedback(task_id="p1-good", action=HumanAction.APPROVE, reasoning={})

        phase1_rate = analyzer.get_approval_rate()
        assert phase1_rate == pytest.approx(0.2)  # 1 out of 5

        # Analyze and update weights
        patterns = analyzer.analyze_rejection_patterns()
        analyzer.update_priority_engine_weights(patterns)

        # Phase 2: After weight adjustment, simulate improved task generation
        # (In reality, task generation would use updated weights)
        # Fewer rejections now
        for i in range(3):
            analyzer.capture_feedback(
                task_id=f"p2-good-{i}", action=HumanAction.APPROVE, reasoning={}
            )
        analyzer.capture_feedback(
            task_id="p2-reject",
            action=HumanAction.REJECT,
            reasoning={"scope": "too_large"},
        )

        # Overall rate improved
        overall_rate = analyzer.get_approval_rate()
        assert overall_rate > phase1_rate
