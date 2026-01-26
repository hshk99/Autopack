"""Tests for adaptive task prioritization."""

from unittest.mock import Mock

import pytest

from generation.task_prioritizer import PrioritizedTask, TaskPrioritizer


@pytest.fixture
def sample_tasks():
    """Sample tasks for testing prioritization."""
    return [
        {
            "id": "phase-1",
            "imp_id": "IMP-001",
            "title": "High priority task",
            "wave": 1,
            "priority": "high",
            "dependencies": [],
            "category": "feature",
        },
        {
            "id": "phase-2",
            "imp_id": "IMP-002",
            "title": "Medium priority task",
            "wave": 2,
            "priority": "medium",
            "dependencies": [],
            "category": "bugfix",
        },
        {
            "id": "phase-3",
            "imp_id": "IMP-003",
            "title": "Critical priority task",
            "wave": 3,
            "priority": "critical",
            "dependencies": [],
            "category": "security",
        },
        {
            "id": "phase-4",
            "imp_id": "IMP-004",
            "title": "Low priority task",
            "wave": 1,
            "priority": "low",
            "dependencies": [],
            "category": "docs",
        },
    ]


@pytest.fixture
def tasks_with_dependencies():
    """Tasks with dependency relationships."""
    return [
        {
            "id": "phase-a",
            "imp_id": "IMP-A",
            "title": "Base task",
            "wave": 1,
            "priority": "medium",
            "dependencies": [],
        },
        {
            "id": "phase-b",
            "imp_id": "IMP-B",
            "title": "Depends on A",
            "wave": 2,
            "priority": "high",
            "dependencies": ["IMP-A"],
        },
        {
            "id": "phase-c",
            "imp_id": "IMP-C",
            "title": "Depends on B",
            "wave": 3,
            "priority": "critical",
            "dependencies": ["IMP-B"],
        },
    ]


@pytest.fixture
def mock_metrics_db():
    """Mock MetricsDatabase."""
    db = Mock()
    db.get_phase_outcomes.return_value = []
    return db


@pytest.fixture
def mock_failure_analyzer():
    """Mock FailureAnalyzer."""
    analyzer = Mock()
    analyzer.get_failure_statistics.return_value = {
        "by_category": {},
        "top_patterns": [],
        "total_unique_patterns": 0,
    }
    return analyzer


class TestTaskPrioritizer:
    """Tests for TaskPrioritizer class."""

    def test_init_without_dependencies(self):
        """Prioritizer initializes without external dependencies."""
        prioritizer = TaskPrioritizer()
        assert prioritizer.metrics_db is None
        assert prioritizer.failure_analyzer is None

    def test_init_with_dependencies(self, mock_metrics_db, mock_failure_analyzer):
        """Prioritizer accepts optional dependencies."""
        prioritizer = TaskPrioritizer(
            metrics_db=mock_metrics_db, failure_analyzer=mock_failure_analyzer
        )
        assert prioritizer.metrics_db is mock_metrics_db
        assert prioritizer.failure_analyzer is mock_failure_analyzer

    def test_prioritize_returns_prioritized_tasks(self, sample_tasks):
        """Prioritize returns list of PrioritizedTask objects."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks, available_slots=4)

        assert len(result) == 4
        for task in result:
            assert isinstance(task, PrioritizedTask)

    def test_prioritize_respects_slot_limit(self, sample_tasks):
        """Prioritize returns only requested number of tasks."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks, available_slots=2)

        assert len(result) == 2

    def test_prioritize_orders_by_score(self, sample_tasks):
        """Tasks are ordered by score (highest first)."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks, available_slots=4)

        scores = [t.score for t in result]
        assert scores == sorted(scores, reverse=True)

    def test_critical_priority_ranks_highest(self, sample_tasks):
        """Critical priority tasks rank higher than others."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks, available_slots=4)

        # Critical task should be first (highest score)
        assert result[0].priority == "critical"

    def test_blocked_tasks_excluded(self, tasks_with_dependencies):
        """Tasks blocked by unmet dependencies are excluded."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(tasks_with_dependencies, available_slots=4)

        # Only task A should be available (B and C are blocked)
        assert len(result) == 1
        assert result[0].imp_id == "IMP-A"

    def test_blocked_tasks_included_when_dependency_complete(
        self, tasks_with_dependencies, mock_metrics_db
    ):
        """Tasks become available when dependencies are complete."""
        mock_metrics_db.get_phase_outcomes.return_value = [
            {"phase_id": "IMP-A", "outcome": "success"}
        ]
        prioritizer = TaskPrioritizer(metrics_db=mock_metrics_db)
        result = prioritizer.prioritize(tasks_with_dependencies, available_slots=4)

        # Tasks A and B should be available now
        imp_ids = [t.imp_id for t in result]
        assert "IMP-A" in imp_ids
        assert "IMP-B" in imp_ids
        assert "IMP-C" not in imp_ids  # Still blocked by IMP-B

    def test_empty_task_list(self):
        """Prioritize handles empty task list."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize([], available_slots=4)

        assert result == []

    def test_fewer_tasks_than_slots(self, sample_tasks):
        """Prioritize returns all tasks when fewer than available slots."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks[:2], available_slots=4)

        assert len(result) == 2


class TestScoreCalculation:
    """Tests for priority score calculation."""

    def test_score_includes_all_factors(self, sample_tasks):
        """Score calculation includes all weighted factors."""
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(sample_tasks, available_slots=1)

        task = result[0]
        expected_factors = [
            "base_priority",
            "wave_urgency",
            "success_likelihood",
            "dependency_chain",
            "age",
        ]
        for factor in expected_factors:
            assert factor in task.factors

    def test_wave_urgency_decreases_with_wave(self):
        """Earlier waves have higher urgency factor."""
        prioritizer = TaskPrioritizer()

        wave1_task = [{"id": "w1", "wave": 1, "priority": "medium", "dependencies": []}]
        wave5_task = [{"id": "w5", "wave": 5, "priority": "medium", "dependencies": []}]

        result1 = prioritizer.prioritize(wave1_task, 1)
        result5 = prioritizer.prioritize(wave5_task, 1)

        assert result1[0].factors["wave_urgency"] > result5[0].factors["wave_urgency"]

    def test_dependency_chain_increases_with_dependents(self):
        """Tasks blocking others get higher dependency_chain factor."""
        tasks = [
            {"id": "blocker", "imp_id": "BLOCKER", "priority": "low", "dependencies": []},
            {"id": "dep1", "imp_id": "D1", "priority": "low", "dependencies": ["BLOCKER"]},
            {"id": "dep2", "imp_id": "D2", "priority": "low", "dependencies": ["BLOCKER"]},
            {"id": "dep3", "imp_id": "D3", "priority": "low", "dependencies": ["BLOCKER"]},
            {"id": "lone", "imp_id": "LONE", "priority": "low", "dependencies": []},
        ]
        prioritizer = TaskPrioritizer()
        result = prioritizer.prioritize(tasks, available_slots=5)

        # Find the blocker and lone task scores
        blocker = next(t for t in result if t.imp_id == "BLOCKER")
        lone = next(t for t in result if t.imp_id == "LONE")

        assert blocker.factors["dependency_chain"] > lone.factors["dependency_chain"]


class TestSuccessRateEstimation:
    """Tests for success rate estimation."""

    def test_default_success_rate_without_analyzer(self):
        """Default success rate is 70% without failure analyzer."""
        prioritizer = TaskPrioritizer()
        tasks = [{"id": "t1", "priority": "medium", "dependencies": []}]
        result = prioritizer.prioritize(tasks, 1)

        assert result[0].estimated_success_rate == 0.7

    def test_success_rate_uses_failure_history(self, mock_failure_analyzer):
        """Success rate adjusts based on failure history."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "by_category": {"ci_test_failure": 10, "ci_build_failure": 5},
            "top_patterns": [],
            "total_unique_patterns": 2,
        }
        prioritizer = TaskPrioritizer(failure_analyzer=mock_failure_analyzer)
        tasks = [{"id": "t1", "priority": "medium", "dependencies": [], "category": "test"}]
        result = prioritizer.prioritize(tasks, 1)

        # With failure history, success rate should be adjusted
        assert result[0].estimated_success_rate <= 0.9
        assert result[0].estimated_success_rate >= 0.3


class TestRecommendations:
    """Tests for human-readable recommendations."""

    def test_get_recommendation_format(self, sample_tasks):
        """Recommendation output includes expected information."""
        prioritizer = TaskPrioritizer()
        recommendation = prioritizer.get_recommendation(sample_tasks, slots=2)

        assert "Recommended tasks for 2 slots:" in recommendation
        assert "Score:" in recommendation
        assert "Wave" in recommendation
        assert "Success estimate:" in recommendation

    def test_get_recommendation_empty_tasks(self):
        """Recommendation handles no available tasks."""
        prioritizer = TaskPrioritizer()
        recommendation = prioritizer.get_recommendation([], slots=4)

        assert "No unblocked tasks available" in recommendation


class TestExportRecommendations:
    """Tests for JSON export functionality."""

    def test_export_creates_file(self, sample_tasks, tmp_path):
        """Export creates JSON file with recommendations."""
        prioritizer = TaskPrioritizer()
        output_path = tmp_path / "recommendations.json"

        prioritizer.export_recommendations(sample_tasks, str(output_path), slots=2)

        assert output_path.exists()

    def test_export_json_structure(self, sample_tasks, tmp_path):
        """Exported JSON has expected structure."""
        import json

        prioritizer = TaskPrioritizer()
        output_path = tmp_path / "recommendations.json"

        prioritizer.export_recommendations(sample_tasks, str(output_path), slots=2)

        with open(output_path) as f:
            data = json.load(f)

        assert "generated_at" in data
        assert "available_slots" in data
        assert data["available_slots"] == 2
        assert "recommended_tasks" in data
        assert len(data["recommended_tasks"]) == 2

    def test_export_creates_parent_directories(self, sample_tasks, tmp_path):
        """Export creates parent directories if needed."""
        prioritizer = TaskPrioritizer()
        output_path = tmp_path / "nested" / "path" / "recommendations.json"

        prioritizer.export_recommendations(sample_tasks, str(output_path), slots=1)

        assert output_path.exists()
