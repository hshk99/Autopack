"""Unit tests for goal drift detection mechanism.

IMP-LOOP-023: Tests for GoalDriftDetector to ensure the self-improvement loop
detects when task generation drifts from stated objectives.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from autopack.telemetry.meta_metrics import GoalDriftDetector, GoalDriftResult


@dataclass
class MockGeneratedTask:
    """Mock task for testing goal drift detection."""

    task_id: str
    title: str
    description: str
    priority: str = "medium"
    source_insights: List[str] = None
    suggested_files: List[str] = None
    estimated_effort: str = "M"
    created_at: datetime = None

    def __post_init__(self):
        if self.source_insights is None:
            self.source_insights = []
        if self.suggested_files is None:
            self.suggested_files = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class TestGoalDriftDetector:
    """Tests for GoalDriftDetector class."""

    def test_default_objectives_defined(self):
        """Detector should have default objectives defined."""
        detector = GoalDriftDetector()

        assert len(detector.objectives) > 0
        assert "reduce_cost" in detector.objectives
        assert "improve_success" in detector.objectives
        assert "fix_failures" in detector.objectives

    def test_custom_objectives(self):
        """Detector should accept custom objectives."""
        custom = {
            "custom_goal": ["keyword1", "keyword2"],
        }
        detector = GoalDriftDetector(objectives=custom)

        assert detector.objectives == custom
        assert "reduce_cost" not in detector.objectives

    def test_calculate_drift_empty_tasks(self):
        """Empty task list should return zero drift."""
        detector = GoalDriftDetector()
        result = detector.calculate_drift([])

        assert result.drift_score == 0.0
        assert result.total_task_count == 0
        assert result.aligned_task_count == 0
        assert len(result.misaligned_tasks) == 0

    def test_calculate_drift_aligned_tasks(self):
        """Tasks with relevant keywords should have low drift score."""
        detector = GoalDriftDetector()

        tasks = [
            MockGeneratedTask(
                task_id="task1",
                title="Reduce token cost in API calls",
                description="Optimize API calls to reduce expensive token usage and save budget",
            ),
            MockGeneratedTask(
                task_id="task2",
                title="Fix recurring failure in build phase",
                description="Resolve the error causing repeated build failures",
            ),
            MockGeneratedTask(
                task_id="task3",
                title="Improve success rate for deployments",
                description="Enhance deployment reliability and increase success accuracy",
            ),
        ]

        result = detector.calculate_drift(tasks)

        # Aligned tasks should have low drift (high alignment)
        assert result.drift_score < 0.5
        assert result.aligned_task_count > 0
        assert result.total_task_count == 3

    def test_calculate_drift_misaligned_tasks(self):
        """Tasks without relevant keywords should have high drift score."""
        detector = GoalDriftDetector()

        tasks = [
            MockGeneratedTask(
                task_id="task1",
                title="Add new feature",
                description="Implement a completely unrelated capability",
            ),
            MockGeneratedTask(
                task_id="task2",
                title="Random update",
                description="Make arbitrary changes to the system",
            ),
        ]

        result = detector.calculate_drift(tasks)

        # Misaligned tasks should have high drift
        assert result.drift_score > 0.5
        assert len(result.misaligned_tasks) > 0

    def test_is_drifting_threshold(self):
        """GoalDriftResult should correctly identify drift based on threshold."""
        result_low = GoalDriftResult(
            drift_score=0.2,
            aligned_task_count=4,
            total_task_count=5,
            alignment_details={},
            misaligned_tasks=[],
        )

        result_high = GoalDriftResult(
            drift_score=0.5,
            aligned_task_count=1,
            total_task_count=5,
            alignment_details={},
            misaligned_tasks=["task2", "task3", "task4", "task5"],
        )

        assert result_low.is_drifting(threshold=0.3) is False
        assert result_high.is_drifting(threshold=0.3) is True

    def test_drift_history_tracking(self):
        """Detector should track drift history for trend analysis."""
        detector = GoalDriftDetector()

        # Generate multiple drift measurements
        for i in range(5):
            tasks = [
                MockGeneratedTask(
                    task_id=f"task{i}",
                    title="Fix cost issue",
                    description="Reduce expensive operations",
                )
            ]
            detector.calculate_drift(tasks)

        assert len(detector._drift_history) == 5

    def test_get_drift_trend_insufficient_data(self):
        """Trend analysis should return None with insufficient data."""
        detector = GoalDriftDetector()

        # Only one measurement
        detector.calculate_drift(
            [MockGeneratedTask(task_id="t1", title="Fix error", description="Fix bug")]
        )

        trend = detector.get_drift_trend(window_size=5)
        assert trend is None

    def test_get_average_drift(self):
        """Average drift should be calculated correctly."""
        detector = GoalDriftDetector()

        # Create tasks with varying alignment
        for title in ["Fix error", "Reduce cost", "Random task"]:
            detector.calculate_drift(
                [MockGeneratedTask(task_id="t", title=title, description="description")]
            )

        avg = detector.get_average_drift()
        assert 0.0 <= avg <= 1.0

    def test_clear_history(self):
        """Clear history should reset drift tracking."""
        detector = GoalDriftDetector()

        detector.calculate_drift(
            [MockGeneratedTask(task_id="t1", title="Fix bug", description="Fix error")]
        )
        assert len(detector._drift_history) > 0

        detector.clear_history()
        assert len(detector._drift_history) == 0

    def test_to_dict_serialization(self):
        """Detector state should serialize to dictionary."""
        detector = GoalDriftDetector(drift_threshold=0.4)

        detector.calculate_drift(
            [MockGeneratedTask(task_id="t1", title="Fix cost", description="Reduce token cost")]
        )

        data = detector.to_dict()

        assert data["drift_threshold"] == 0.4
        assert "objectives" in data
        assert "history_size" in data
        assert "average_drift" in data

    def test_goal_drift_result_to_dict(self):
        """GoalDriftResult should serialize to dictionary."""
        result = GoalDriftResult(
            drift_score=0.25,
            aligned_task_count=3,
            total_task_count=4,
            alignment_details={"task1": 0.8, "task2": 0.6},
            misaligned_tasks=["task3"],
        )

        data = result.to_dict()

        assert data["drift_score"] == 0.25
        assert data["aligned_task_count"] == 3
        assert data["total_task_count"] == 4
        assert "timestamp" in data


class TestGoalDriftIntegration:
    """Integration tests for goal drift detection in task generation."""

    def test_mixed_alignment_tasks(self):
        """Detector should handle mix of aligned and misaligned tasks."""
        detector = GoalDriftDetector(min_alignment_score=0.2)

        tasks = [
            # Aligned task - matches cost reduction
            MockGeneratedTask(
                task_id="aligned1",
                title="Reduce API token cost",
                description="Optimize token usage to reduce expensive calls",
            ),
            # Aligned task - matches failure fixing
            MockGeneratedTask(
                task_id="aligned2",
                title="Fix build failures",
                description="Resolve recurring error in build process",
            ),
            # Misaligned task - no matching keywords
            MockGeneratedTask(
                task_id="misaligned1",
                title="Add documentation",
                description="Write some notes about the system",
            ),
        ]

        result = detector.calculate_drift(tasks)

        assert result.total_task_count == 3
        assert result.aligned_task_count >= 2  # At least 2 aligned
        assert "aligned1" in result.alignment_details
        assert "aligned2" in result.alignment_details
        assert "misaligned1" in result.alignment_details

    def test_keyword_matching_case_insensitive(self):
        """Keyword matching should be case-insensitive."""
        detector = GoalDriftDetector()

        tasks = [
            MockGeneratedTask(
                task_id="t1",
                title="REDUCE COST NOW",
                description="OPTIMIZE TOKEN BUDGET",
            ),
        ]

        result = detector.calculate_drift(tasks)

        # Should match despite uppercase
        assert result.drift_score < 0.5

    def test_multiple_objectives_diversity_bonus(self):
        """Tasks matching multiple objectives should get diversity bonus."""
        detector = GoalDriftDetector()

        # Task matching multiple objectives
        multi_task = MockGeneratedTask(
            task_id="multi",
            title="Fix errors and reduce cost",
            description="Improve success rate, fix failures, and optimize token budget",
        )

        # Task matching single objective
        single_task = MockGeneratedTask(
            task_id="single",
            title="Fix error",
            description="Fix the bug",
        )

        result_multi = detector.calculate_drift([multi_task])
        result_single = detector.calculate_drift([single_task])

        # Multi-objective task should have lower drift (better alignment)
        assert result_multi.drift_score <= result_single.drift_score


class TestGoalDriftAutoCorrection:
    """Tests for IMP-LOOP-028: Goal drift auto-correction functionality."""

    def test_realignment_action_no_drift(self):
        """realignment_action should return empty list when drift is below threshold."""
        detector = GoalDriftDetector(drift_threshold=0.5)

        # Create well-aligned tasks
        tasks = [
            MockGeneratedTask(
                task_id="task1",
                title="Reduce token cost",
                description="Optimize API calls to reduce expensive token usage",
            ),
            MockGeneratedTask(
                task_id="task2",
                title="Fix build failure",
                description="Resolve recurring error in build process",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        assert corrective_tasks == []

    def test_realignment_action_generates_corrections_on_drift(self):
        """realignment_action should generate corrective tasks when drift detected."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        # Create misaligned tasks (no relevant keywords)
        tasks = [
            MockGeneratedTask(
                task_id="task1",
                title="Add new feature",
                description="Implement a completely unrelated capability",
            ),
            MockGeneratedTask(
                task_id="task2",
                title="Update documentation",
                description="Write some notes about the system",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        # Should generate corrective tasks for neglected objectives
        assert len(corrective_tasks) > 0
        assert all(task["type"] == "drift_correction" for task in corrective_tasks)
        assert all(task["priority"] == "high" for task in corrective_tasks)

    def test_realignment_action_corrective_task_structure(self):
        """Corrective tasks should have proper structure."""
        detector = GoalDriftDetector(drift_threshold=0.3)

        tasks = [
            MockGeneratedTask(
                task_id="unrelated",
                title="Random update",
                description="Make arbitrary changes",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        # Verify corrective task structure
        for task in corrective_tasks:
            assert "task_id" in task
            assert "title" in task
            assert "description" in task
            assert "type" in task
            assert "priority" in task
            assert "corrective_action" in task
            assert "source" in task
            assert task["source"] == "goal_drift_detector"

    def test_analyze_drift_direction_identifies_neglected_objectives(self):
        """_analyze_drift_direction should identify neglected objectives."""
        detector = GoalDriftDetector()

        # Create tasks that only focus on cost reduction
        tasks = [
            MockGeneratedTask(
                task_id="cost1",
                title="Reduce cost",
                description="Optimize budget spending",
            ),
            MockGeneratedTask(
                task_id="cost2",
                title="Save money",
                description="Reduce expensive operations",
            ),
        ]

        drift_result = detector.calculate_drift(tasks)
        issues = detector._analyze_drift_direction(tasks, drift_result)

        # Should identify other objectives as neglected
        neglected_objectives = [issue["objective"] for issue in issues]

        # fix_failures should be neglected (no failure-related keywords)
        assert any(
            obj in neglected_objectives
            for obj in [
                "fix_failures",
                "reduce_retries",
                "improve_performance",
                "enhance_reliability",
            ]
        )

    def test_analyze_drift_direction_includes_misaligned_tasks_issue(self):
        """_analyze_drift_direction should report misaligned tasks."""
        detector = GoalDriftDetector()

        # Create completely misaligned tasks
        tasks = [
            MockGeneratedTask(
                task_id="misaligned1",
                title="Random stuff",
                description="Do something unrelated",
            ),
        ]

        drift_result = detector.calculate_drift(tasks)
        issues = detector._analyze_drift_direction(tasks, drift_result)

        # Should include task_realignment issue
        realignment_issues = [i for i in issues if i["objective"] == "task_realignment"]
        assert len(realignment_issues) > 0

    def test_corrective_action_for_each_objective_type(self):
        """Each objective type should have a specific corrective action."""
        detector = GoalDriftDetector()

        objectives = [
            "reduce_cost",
            "improve_success",
            "fix_failures",
            "reduce_retries",
            "improve_performance",
            "enhance_reliability",
        ]

        for objective in objectives:
            action = detector._get_corrective_action_for_objective(objective)

            assert "action_type" in action
            assert "target" in action
            assert "parameters" in action
            assert isinstance(action["parameters"], dict)

    def test_realignment_action_with_empty_task_list(self):
        """realignment_action should handle empty task list."""
        detector = GoalDriftDetector()

        corrective_tasks = detector.realignment_action([])

        # Empty list = no drift = no corrections
        assert corrective_tasks == []

    def test_realignment_action_includes_drift_score(self):
        """Corrective tasks should include the drift score."""
        detector = GoalDriftDetector(drift_threshold=0.2)

        tasks = [
            MockGeneratedTask(
                task_id="unaligned",
                title="Something random",
                description="Unrelated task description",
            ),
        ]

        corrective_tasks = detector.realignment_action(tasks)

        if corrective_tasks:
            for task in corrective_tasks:
                assert "drift_score" in task
                assert isinstance(task["drift_score"], float)
                assert 0.0 <= task["drift_score"] <= 1.0

    def test_analyze_drift_direction_sorts_by_urgency(self):
        """Issues should be sorted by coverage ratio (most urgent first)."""
        detector = GoalDriftDetector()

        # Create tasks that only match one objective
        tasks = [
            MockGeneratedTask(
                task_id="task1",
                title="Fix error",
                description="Fix the bug issue problem",
            ),
        ]

        drift_result = detector.calculate_drift(tasks)
        issues = detector._analyze_drift_direction(tasks, drift_result)

        # Issues should be sorted by coverage_ratio ascending
        coverage_ratios = [i.get("coverage_ratio", 0.0) for i in issues]
        assert coverage_ratios == sorted(coverage_ratios)
