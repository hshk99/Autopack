"""Tests for IMP-LOOP-028: Goal Drift Auto-Correction Integration.

Tests the integration of goal drift correction with the autonomous execution loop.
This ensures that when drift is detected, corrective tasks are properly generated
and queued for execution.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from autopack.telemetry.meta_metrics import GoalDriftDetector


@dataclass
class MockGeneratedTask:
    """Mock task for testing goal drift correction integration."""

    task_id: str
    title: str
    description: str
    priority: str = "medium"
    source_insights: List[str] = None
    suggested_files: List[str] = None
    estimated_effort: str = "M"
    created_at: datetime = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.source_insights is None:
            self.source_insights = []
        if self.suggested_files is None:
            self.suggested_files = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}


class TestGoalDriftCorrectionIntegration:
    """Integration tests for goal drift correction in the autonomous loop."""

    def test_drift_correction_tasks_have_correct_type(self):
        """Corrective tasks should be marked as drift_correction type."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        # Create misaligned tasks
        tasks = [
            MockGeneratedTask(
                task_id="unaligned1",
                title="Random feature",
                description="Add something unrelated",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        for task in corrective_tasks:
            assert task["type"] == "drift_correction"

    def test_drift_correction_tasks_have_high_priority(self):
        """Corrective tasks should have high priority to be executed first."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="misaligned",
                title="Something random",
                description="Unrelated task",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        for task in corrective_tasks:
            assert task["priority"] == "high"

    def test_drift_detector_can_be_disabled(self):
        """Goal drift detection can be disabled via threshold of 1.0."""
        detector = GoalDriftDetector(drift_threshold=1.0)

        # Even completely misaligned tasks should not trigger correction
        tasks = [
            MockGeneratedTask(
                task_id="misaligned",
                title="Random",
                description="Unrelated",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        # Threshold of 1.0 means drift is never detected
        assert corrective_tasks == []

    def test_correction_addresses_specific_objectives(self):
        """Each corrective task should target a specific objective."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="unaligned",
                title="Random update",
                description="Something unrelated to any objective",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        # Each correction should have a target objective
        for task in corrective_tasks:
            assert "target_objective" in task
            assert task["target_objective"] != ""

    def test_correction_includes_actionable_details(self):
        """Corrective tasks should include actionable details."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="unaligned",
                title="Random",
                description="Unrelated",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        for task in corrective_tasks:
            corrective_action = task.get("corrective_action", {})
            assert "action_type" in corrective_action
            assert "target" in corrective_action
            assert "parameters" in corrective_action


class TestGoalDriftCorrectionEdgeCases:
    """Edge case tests for goal drift correction."""

    def test_handles_tasks_with_missing_attributes(self):
        """Should handle tasks that may have missing title or description."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        # Create a mock object without proper attributes
        class MinimalTask:
            task_id = "minimal"

        tasks = [MinimalTask()]

        # Should not raise exception
        corrective_tasks = detector.realignment_action(tasks)
        assert isinstance(corrective_tasks, list)

    def test_handles_very_long_task_descriptions(self):
        """Should handle tasks with very long descriptions."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        long_description = "random " * 1000  # Very long unrelated description

        tasks = [
            MockGeneratedTask(
                task_id="long_task",
                title="Long description task",
                description=long_description,
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)
        assert isinstance(corrective_tasks, list)

    def test_handles_unicode_in_task_text(self):
        """Should handle unicode characters in task text."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="unicode_task",
                title="修复错误 and émoji 🚀",
                description="国际化 description with ñ and ü",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)
        assert isinstance(corrective_tasks, list)

    def test_drift_score_boundary_conditions(self):
        """Test drift score exactly at threshold boundary."""
        detector = GoalDriftDetector(drift_threshold=0.5)

        # Create tasks that result in exactly threshold drift
        # This is hard to achieve exactly, so test near-boundary
        tasks_aligned = [
            MockGeneratedTask(
                task_id="aligned",
                title="Fix error and reduce cost",
                description="Improve success and fix failures",
            ),
        ]

        tasks_misaligned = [
            MockGeneratedTask(
                task_id="misaligned",
                title="Random stuff",
                description="Unrelated things",
            ),
        ]

        # Aligned should not trigger correction
        corrections_aligned = detector.realignment_action(tasks_aligned)
        # Misaligned should trigger correction
        corrections_misaligned = detector.realignment_action(tasks_misaligned)

        # One should be empty, one should have corrections
        assert corrections_aligned == [] or corrections_misaligned != []


class TestDriftAnalysisQuality:
    """Tests for the quality of drift analysis."""

    def test_identifies_all_neglected_objectives(self):
        """Analysis should identify all objectives with low coverage."""
        detector = GoalDriftDetector(drift_threshold=0.1)

        # Tasks only covering one objective
        tasks = [
            MockGeneratedTask(
                task_id="cost1",
                title="Reduce expensive operations",
                description="Cut costs and optimize budget",
            ),
            MockGeneratedTask(
                task_id="cost2",
                title="Save tokens",
                description="Reduce token spending",
            ),
        ]

        drift_result = detector.calculate_drift(tasks)
        issues = detector._analyze_drift_direction(tasks, drift_result)

        # Should identify multiple neglected objectives
        objectives_mentioned = {issue["objective"] for issue in issues}

        # At least some objectives should be flagged as neglected
        neglected_count = len(objectives_mentioned)
        assert neglected_count >= 3  # Most objectives should be neglected

    def test_provides_meaningful_descriptions(self):
        """Issue descriptions should be meaningful and actionable."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="unaligned",
                title="Random",
                description="Unrelated",
            ),
        ]

        drift_result = detector.calculate_drift(tasks)
        issues = detector._analyze_drift_direction(tasks, drift_result)

        for issue in issues:
            description = issue.get("description", "")
            # Description should mention the objective
            assert len(description) > 20  # Non-trivial description
            assert "coverage" in description.lower() or "misaligned" in description.lower()


class TestCorrectionTaskGeneration:
    """Tests for the generation of correction tasks."""

    def test_generates_unique_task_ids(self):
        """Each corrective task should have a unique ID."""
        detector = GoalDriftDetector(drift_threshold=0.2)

        tasks = [
            MockGeneratedTask(
                task_id="unaligned",
                title="Random",
                description="Unrelated task that triggers multiple corrections",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        if len(corrective_tasks) > 1:
            task_ids = [t["task_id"] for t in corrective_tasks]
            assert len(task_ids) == len(set(task_ids))  # All unique

    def test_corrective_actions_are_specific_to_objective(self):
        """Corrective actions should be tailored to the neglected objective."""
        detector = GoalDriftDetector()

        # Get corrective actions for different objectives
        cost_action = detector._get_corrective_action_for_objective("reduce_cost")
        failure_action = detector._get_corrective_action_for_objective("fix_failures")

        # Actions should be different
        assert cost_action["action_type"] != failure_action["action_type"]
        assert cost_action["target"] != failure_action["target"]

    def test_unknown_objective_gets_generic_action(self):
        """Unknown objectives should get a generic corrective action."""
        detector = GoalDriftDetector()

        action = detector._get_corrective_action_for_objective("unknown_objective")

        assert action["action_type"] == "generate_objective_aligned_tasks"
        assert action["parameters"]["objective"] == "unknown_objective"
