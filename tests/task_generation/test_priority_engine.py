"""Tests for the Data-Driven Task Priority Engine.

Tests the PriorityEngine class which prioritizes improvements based on
historical learning data including category success rates, blocking patterns,
and complexity estimation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from autopack.task_generation.priority_engine import (
    COMPLEXITY_KEYWORDS,
    ExecutionPlanResult,
    PriorityEngine,
)


@pytest.fixture
def mock_learning_db() -> MagicMock:
    """Create a mock LearningDatabase for testing."""
    db = MagicMock()
    # Default return values
    db.get_success_rate.return_value = 0.7
    db.get_likely_blockers.return_value = []
    db.get_historical_patterns.return_value = {
        "top_blocking_reasons": [],
        "category_success_rates": {},
        "recent_trends": {"sample_size": 0},
        "improvement_outcome_summary": {},
        "total_improvements_tracked": 0,
        "total_cycles_tracked": 0,
    }
    return db


@pytest.fixture
def priority_engine(mock_learning_db: MagicMock) -> PriorityEngine:
    """Create a PriorityEngine instance with mock database."""
    return PriorityEngine(mock_learning_db)


@pytest.fixture
def sample_improvements() -> list[dict[str, Any]]:
    """Create sample improvement records for testing."""
    return [
        {
            "imp_id": "IMP-TEL-001",
            "title": "Add telemetry analytics pipeline",
            "description": "Create analytics pipeline for operational insights",
            "priority": "critical",
            "category": "telemetry",
        },
        {
            "imp_id": "IMP-MEM-001",
            "title": "Historical learning database",
            "description": "Persist learnings across discovery cycles",
            "priority": "high",
            "category": "memory",
        },
        {
            "imp_id": "IMP-TGN-001",
            "title": "Data-driven task prioritization",
            "description": "Prioritize tasks using historical outcomes",
            "priority": "critical",
        },
        {
            "imp_id": "IMP-FIX-001",
            "title": "Fix authentication bug",
            "description": "Fix login flow issue in edge case",
            "priority": "medium",
        },
        {
            "imp_id": "IMP-PERF-001",
            "title": "Optimize database queries",
            "description": "Migrate to async query pattern",
            "priority": "low",
        },
    ]


class TestPriorityEngineInit:
    """Tests for PriorityEngine initialization."""

    def test_init_with_learning_db(self, mock_learning_db: MagicMock) -> None:
        """Test initialization with a learning database."""
        engine = PriorityEngine(mock_learning_db)
        assert engine.learning_db is mock_learning_db
        assert engine._patterns_cache is None

    def test_clear_cache(self, priority_engine: PriorityEngine) -> None:
        """Test cache clearing."""
        # Populate cache
        priority_engine._get_cached_patterns()
        assert priority_engine._patterns_cache is not None

        # Clear cache
        priority_engine.clear_cache()
        assert priority_engine._patterns_cache is None


class TestCategoryExtraction:
    """Tests for category extraction from improvements."""

    def test_extract_explicit_category(self, priority_engine: PriorityEngine) -> None:
        """Test extraction when category is explicitly set."""
        imp = {"imp_id": "IMP-001", "category": "Memory"}
        category = priority_engine._extract_category(imp)
        assert category == "memory"

    def test_extract_category_from_imp_id(self, priority_engine: PriorityEngine) -> None:
        """Test extraction from improvement ID pattern."""
        test_cases = [
            ("IMP-TEL-001", "telemetry"),
            ("IMP-MEM-002", "memory"),
            ("IMP-TGN-003", "task_generation"),
            ("IMP-GEN-004", "generation"),
            ("IMP-LOG-005", "logging"),
            ("IMP-API-006", "api"),
            ("IMP-CI-007", "ci"),
            ("IMP-TEST-008", "testing"),
        ]

        for imp_id, expected_category in test_cases:
            imp = {"imp_id": imp_id}
            category = priority_engine._extract_category(imp)
            assert category == expected_category, f"Failed for {imp_id}"

    def test_extract_category_unknown_code(self, priority_engine: PriorityEngine) -> None:
        """Test extraction with unknown category code."""
        imp = {"imp_id": "IMP-XYZ-001"}
        category = priority_engine._extract_category(imp)
        assert category == "xyz"

    def test_extract_category_fallback(self, priority_engine: PriorityEngine) -> None:
        """Test fallback to 'general' when no category info available."""
        imp = {"id": "001", "title": "Some improvement"}
        category = priority_engine._extract_category(imp)
        assert category == "general"


class TestPriorityLevelExtraction:
    """Tests for priority level extraction."""

    def test_extract_valid_priority_levels(self, priority_engine: PriorityEngine) -> None:
        """Test extraction of valid priority levels."""
        for level in ["critical", "high", "medium", "low"]:
            imp = {"priority": level}
            extracted = priority_engine._extract_priority_level(imp)
            assert extracted == level

    def test_extract_priority_case_insensitive(self, priority_engine: PriorityEngine) -> None:
        """Test priority extraction is case insensitive."""
        imp = {"priority": "HIGH"}
        extracted = priority_engine._extract_priority_level(imp)
        assert extracted == "high"

    def test_extract_priority_default(self, priority_engine: PriorityEngine) -> None:
        """Test default priority when not specified."""
        imp = {"title": "Some improvement"}
        extracted = priority_engine._extract_priority_level(imp)
        assert extracted == "medium"

    def test_extract_priority_invalid(self, priority_engine: PriorityEngine) -> None:
        """Test handling of invalid priority values."""
        imp = {"priority": "urgent"}
        extracted = priority_engine._extract_priority_level(imp)
        assert extracted == "medium"


class TestComplexityEstimation:
    """Tests for complexity estimation from descriptions."""

    def test_estimate_complexity_add(self, priority_engine: PriorityEngine) -> None:
        """Test complexity estimation for 'add' operations."""
        imp = {"title": "Add new feature", "description": "Add user profile page"}
        complexity = priority_engine._estimate_complexity(imp)
        assert complexity == COMPLEXITY_KEYWORDS["add"]

    def test_estimate_complexity_refactor(self, priority_engine: PriorityEngine) -> None:
        """Test complexity estimation for refactoring."""
        imp = {"title": "Refactor authentication", "description": "Clean up auth code"}
        complexity = priority_engine._estimate_complexity(imp)
        assert complexity == COMPLEXITY_KEYWORDS["refactor"]

    def test_estimate_complexity_migrate(self, priority_engine: PriorityEngine) -> None:
        """Test complexity estimation for migrations (higher risk)."""
        imp = {"title": "Migrate database schema", "description": "Migrate to new schema"}
        complexity = priority_engine._estimate_complexity(imp)
        assert complexity == COMPLEXITY_KEYWORDS["migrate"]

    def test_estimate_complexity_multiple_keywords(self, priority_engine: PriorityEngine) -> None:
        """Test complexity estimation with multiple keywords (average)."""
        imp = {
            "title": "Add and refactor user module",
            "description": "Add new features and refactor existing code",
        }
        complexity = priority_engine._estimate_complexity(imp)
        expected = (COMPLEXITY_KEYWORDS["add"] + COMPLEXITY_KEYWORDS["refactor"]) / 2
        assert complexity == expected

    def test_estimate_complexity_no_keywords(self, priority_engine: PriorityEngine) -> None:
        """Test default complexity when no keywords found."""
        imp = {"title": "Improve system", "description": "Make things better"}
        complexity = priority_engine._estimate_complexity(imp)
        assert complexity == 0.75  # Default

    def test_estimate_complexity_empty(self, priority_engine: PriorityEngine) -> None:
        """Test complexity estimation with empty fields."""
        imp = {}
        complexity = priority_engine._estimate_complexity(imp)
        assert complexity == 0.75  # Default


class TestBlockingRiskCalculation:
    """Tests for blocking risk calculation."""

    def test_calculate_blocking_risk_no_blockers(self, priority_engine: PriorityEngine) -> None:
        """Test zero risk when no blockers."""
        imp = {"title": "Some improvement"}
        risk = priority_engine._calculate_blocking_risk(imp, [])
        assert risk == 0.0

    def test_calculate_blocking_risk_matching_keywords(
        self, priority_engine: PriorityEngine
    ) -> None:
        """Test risk calculation when blocker keywords match."""
        imp = {
            "title": "Add authentication feature",
            "description": "Implement OAuth authentication",
        }
        blockers = [
            {"reason": "authentication dependency conflict", "frequency": 5, "likelihood": "high"}
        ]
        risk = priority_engine._calculate_blocking_risk(imp, blockers)
        assert risk > 0.0

    def test_calculate_blocking_risk_category_match(self, priority_engine: PriorityEngine) -> None:
        """Test risk calculation when category matches blocker."""
        imp = {"imp_id": "IMP-MEM-001", "title": "Memory improvement"}
        blockers = [{"reason": "memory allocation issues", "frequency": 3, "likelihood": "medium"}]
        risk = priority_engine._calculate_blocking_risk(imp, blockers)
        assert risk > 0.0

    def test_calculate_blocking_risk_no_match(self, priority_engine: PriorityEngine) -> None:
        """Test zero risk when blocker doesn't match."""
        imp = {"title": "Add simple feature", "description": "Basic functionality"}
        blockers = [{"reason": "database migration failure", "frequency": 10, "likelihood": "high"}]
        risk = priority_engine._calculate_blocking_risk(imp, blockers)
        assert risk == 0.0


class TestPriorityScoreCalculation:
    """Tests for priority score calculation."""

    def test_calculate_priority_score_basic(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test basic priority score calculation."""
        imp = {
            "imp_id": "IMP-TEL-001",
            "title": "Add telemetry",
            "priority": "high",
        }
        score = priority_engine.calculate_priority_score(imp)
        assert 0.0 <= score <= 1.0

    def test_calculate_priority_score_critical_higher(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test that critical priority scores higher than low priority."""
        critical_imp = {"imp_id": "IMP-001", "title": "Critical task", "priority": "critical"}
        low_imp = {"imp_id": "IMP-002", "title": "Low task", "priority": "low"}

        critical_score = priority_engine.calculate_priority_score(critical_imp)
        low_score = priority_engine.calculate_priority_score(low_imp)

        assert critical_score > low_score

    def test_calculate_priority_score_high_success_rate(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test score increases with higher category success rate."""
        mock_learning_db.get_success_rate.return_value = 0.9
        high_success_imp = {"imp_id": "IMP-001", "title": "High success category"}
        high_score = priority_engine.calculate_priority_score(high_success_imp)

        mock_learning_db.get_success_rate.return_value = 0.3
        low_success_imp = {"imp_id": "IMP-002", "title": "Low success category"}
        low_score = priority_engine.calculate_priority_score(low_success_imp)

        assert high_score > low_score

    def test_calculate_priority_score_with_blockers(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test score decreases with likely blockers."""
        # First score without blockers
        mock_learning_db.get_likely_blockers.return_value = []
        imp = {"imp_id": "IMP-001", "title": "Some database migration task"}
        score_no_blockers = priority_engine.calculate_priority_score(imp)

        # Score with matching blockers
        mock_learning_db.get_likely_blockers.return_value = [
            {"reason": "database migration failure", "frequency": 5, "likelihood": "high"}
        ]
        score_with_blockers = priority_engine.calculate_priority_score(imp)

        assert score_no_blockers >= score_with_blockers


class TestRankImprovements:
    """Tests for improvement ranking."""

    def test_rank_improvements_empty(self, priority_engine: PriorityEngine) -> None:
        """Test ranking empty list returns empty list."""
        result = priority_engine.rank_improvements([])
        assert result == []

    def test_rank_improvements_sorted(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test improvements are sorted by score descending."""
        ranked = priority_engine.rank_improvements(sample_improvements, include_scores=True)

        # Verify sorted by priority_score descending
        scores = [imp["priority_score"] for imp in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_improvements_include_scores(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test include_scores adds priority_score field."""
        ranked = priority_engine.rank_improvements(sample_improvements, include_scores=True)
        for imp in ranked:
            assert "priority_score" in imp
            assert 0.0 <= imp["priority_score"] <= 1.0

    def test_rank_improvements_no_mutation(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test original improvements are not mutated."""
        original_first = dict(sample_improvements[0])
        priority_engine.rank_improvements(sample_improvements, include_scores=True)
        assert "priority_score" not in sample_improvements[0]
        assert sample_improvements[0] == original_first


class TestDetectLikelyBlockers:
    """Tests for likely blocker detection."""

    def test_detect_blockers_empty(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test detection returns empty when no blockers in DB."""
        mock_learning_db.get_likely_blockers.return_value = []
        imp = {"title": "Some improvement"}
        blockers = priority_engine.detect_likely_blockers(imp)
        assert blockers == []

    def test_detect_blockers_matching(
        self, priority_engine: PriorityEngine, mock_learning_db: MagicMock
    ) -> None:
        """Test detection finds matching blockers."""
        mock_learning_db.get_likely_blockers.return_value = [
            {"reason": "database connection timeout issues", "frequency": 5, "likelihood": "high"}
        ]
        imp = {
            "title": "Update database connection handling",
            "description": "Fix timeout issues in database connection pool",
        }
        blockers = priority_engine.detect_likely_blockers(imp)
        assert len(blockers) > 0
        assert any("database" in b.lower() for b in blockers)


class TestPrioritySummary:
    """Tests for priority summary generation."""

    def test_get_priority_summary_empty(self, priority_engine: PriorityEngine) -> None:
        """Test summary with empty improvements list."""
        summary = priority_engine.get_priority_summary([])
        assert summary["total_improvements"] == 0
        assert summary["by_priority_level"] == {}
        assert summary["by_category"] == {}
        assert summary["high_risk_items"] == []
        assert summary["recommended_order"] == []

    def test_get_priority_summary_counts(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test summary contains correct counts."""
        summary = priority_engine.get_priority_summary(sample_improvements)
        assert summary["total_improvements"] == len(sample_improvements)
        assert "critical" in summary["by_priority_level"]
        assert "high" in summary["by_priority_level"]

    def test_get_priority_summary_categories(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test summary contains category information."""
        summary = priority_engine.get_priority_summary(sample_improvements)
        assert len(summary["by_category"]) > 0
        for category_data in summary["by_category"].values():
            assert "count" in category_data
            assert "avg_score" in category_data

    def test_get_priority_summary_recommended_order(
        self,
        priority_engine: PriorityEngine,
        sample_improvements: list[dict[str, Any]],
    ) -> None:
        """Test summary contains recommended order (top 5)."""
        summary = priority_engine.get_priority_summary(sample_improvements)
        assert len(summary["recommended_order"]) <= 5
        for item in summary["recommended_order"]:
            assert "imp_id" in item
            assert "priority_score" in item
            assert "priority_level" in item
            assert "category" in item


class TestIntegrationWithLearningDb:
    """Integration tests with a real-ish LearningDatabase."""

    @pytest.fixture
    def learning_db_with_data(self, tmp_path: Path) -> Any:
        """Create a LearningDatabase with test data."""
        from autopack.memory.learning_db import LearningDatabase

        db_path = tmp_path / "learning_db.json"
        db = LearningDatabase(db_path)

        # Record some improvement outcomes
        db.record_improvement_outcome(
            "IMP-TEL-001", "implemented", "Completed successfully", "telemetry", "high"
        )
        db.record_improvement_outcome(
            "IMP-TEL-002", "implemented", "Completed", "telemetry", "medium"
        )
        db.record_improvement_outcome(
            "IMP-MEM-001", "blocked", "Dependency conflict", "memory", "high"
        )
        db.record_improvement_outcome("IMP-MEM-002", "implemented", "Completed", "memory", "high")

        return db

    def test_integration_with_real_db(self, learning_db_with_data: Any) -> None:
        """Test PriorityEngine works with real LearningDatabase."""
        engine = PriorityEngine(learning_db_with_data)

        # Telemetry should have higher success rate than memory
        tel_rate = learning_db_with_data.get_success_rate("telemetry")
        mem_rate = learning_db_with_data.get_success_rate("memory")
        assert tel_rate > mem_rate

        # Score a telemetry improvement
        tel_imp = {"imp_id": "IMP-TEL-003", "title": "New telemetry feature", "priority": "high"}
        mem_imp = {"imp_id": "IMP-MEM-003", "title": "New memory feature", "priority": "high"}

        tel_score = engine.calculate_priority_score(tel_imp)
        mem_score = engine.calculate_priority_score(mem_imp)

        # Telemetry should score higher due to better success rate
        assert tel_score > mem_score

    def test_integration_ranking(self, learning_db_with_data: Any) -> None:
        """Test ranking with real database data."""
        engine = PriorityEngine(learning_db_with_data)

        improvements = [
            {"imp_id": "IMP-TEL-003", "title": "Telemetry improvement", "priority": "high"},
            {"imp_id": "IMP-MEM-003", "title": "Memory improvement", "priority": "high"},
        ]

        ranked = engine.rank_improvements(improvements, include_scores=True)
        assert len(ranked) == 2

        # First should be telemetry (higher success rate)
        assert "TEL" in ranked[0]["imp_id"]


class TestBuildDependencyDag:
    """Tests for DAG construction from task dependencies."""

    def test_build_dag_no_dependencies(self, priority_engine: PriorityEngine) -> None:
        """Test DAG with no dependencies."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1"},
            {"imp_id": "IMP-002", "title": "Task 2"},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        assert dag["IMP-001"] == []
        assert dag["IMP-002"] == []

    def test_build_dag_with_dependencies(self, priority_engine: PriorityEngine) -> None:
        """Test DAG with explicit dependencies."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1"},
            {"imp_id": "IMP-002", "title": "Task 2", "depends_on": ["IMP-001"]},
            {"imp_id": "IMP-003", "title": "Task 3", "depends_on": ["IMP-001", "IMP-002"]},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        assert dag["IMP-001"] == []
        assert dag["IMP-002"] == ["IMP-001"]
        assert set(dag["IMP-003"]) == {"IMP-001", "IMP-002"}

    def test_build_dag_filters_invalid_deps(self, priority_engine: PriorityEngine) -> None:
        """Test that invalid dependencies are filtered out."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1"},
            {"imp_id": "IMP-002", "title": "Task 2", "depends_on": ["IMP-001", "INVALID"]},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        assert dag["IMP-002"] == ["IMP-001"]

    def test_build_dag_string_dependency(self, priority_engine: PriorityEngine) -> None:
        """Test DAG handles string dependency (not list)."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1"},
            {"imp_id": "IMP-002", "title": "Task 2", "depends_on": "IMP-001"},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        assert dag["IMP-002"] == ["IMP-001"]


class TestTopologicalSort:
    """Tests for topological sorting of tasks."""

    def test_topological_sort_no_deps(self, priority_engine: PriorityEngine) -> None:
        """Test sort with no dependencies - sorted by priority."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Low priority", "priority": "low"},
            {"imp_id": "IMP-002", "title": "High priority", "priority": "high"},
            {"imp_id": "IMP-003", "title": "Critical priority", "priority": "critical"},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        sorted_tasks = priority_engine._topological_sort(tasks, dag)

        # Should be sorted by priority score
        assert len(sorted_tasks) == 3
        # Critical should come first
        assert sorted_tasks[0]["imp_id"] == "IMP-003"
        # High should come second
        assert sorted_tasks[1]["imp_id"] == "IMP-002"
        # Low should come last
        assert sorted_tasks[2]["imp_id"] == "IMP-001"

    def test_topological_sort_with_deps(self, priority_engine: PriorityEngine) -> None:
        """Test sort respects dependencies."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1", "priority": "low"},
            {
                "imp_id": "IMP-002",
                "title": "Task 2",
                "priority": "critical",
                "depends_on": ["IMP-001"],
            },
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        sorted_tasks = priority_engine._topological_sort(tasks, dag)

        # IMP-001 must come before IMP-002 despite lower priority
        assert len(sorted_tasks) == 2
        assert sorted_tasks[0]["imp_id"] == "IMP-001"
        assert sorted_tasks[1]["imp_id"] == "IMP-002"

    def test_topological_sort_chain(self, priority_engine: PriorityEngine) -> None:
        """Test sort with dependency chain."""
        tasks = [
            {"imp_id": "IMP-003", "title": "Task 3", "depends_on": ["IMP-002"]},
            {"imp_id": "IMP-001", "title": "Task 1"},
            {"imp_id": "IMP-002", "title": "Task 2", "depends_on": ["IMP-001"]},
        ]
        dag = priority_engine._build_dependency_dag(tasks)
        sorted_tasks = priority_engine._topological_sort(tasks, dag)

        ids = [t["imp_id"] for t in sorted_tasks]
        assert ids.index("IMP-001") < ids.index("IMP-002")
        assert ids.index("IMP-002") < ids.index("IMP-003")

    def test_topological_sort_empty(self, priority_engine: PriorityEngine) -> None:
        """Test sort with empty list."""
        sorted_tasks = priority_engine._topological_sort([], {})
        assert sorted_tasks == []


class TestParetoFrontier:
    """Tests for Pareto frontier computation."""

    def test_pareto_frontier_single_task(self, priority_engine: PriorityEngine) -> None:
        """Test frontier with single task."""
        tasks = [{"imp_id": "IMP-001", "estimated_tokens": 1000, "priority": "high"}]
        frontier, count = priority_engine._compute_pareto_frontier(tasks)
        assert len(frontier) == 1
        assert count == 1

    def test_pareto_frontier_all_on_frontier(self, priority_engine: PriorityEngine) -> None:
        """Test when all tasks are on the frontier."""
        # High cost high impact vs low cost low impact
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 5000, "priority": "critical"},
            {"imp_id": "IMP-002", "estimated_tokens": 500, "priority": "low"},
        ]
        frontier, count = priority_engine._compute_pareto_frontier(tasks)
        assert count == 2  # Both on frontier

    def test_pareto_frontier_dominated_task(self, priority_engine: PriorityEngine) -> None:
        """Test that dominated tasks are identified."""
        # IMP-002 is dominated: same cost but lower priority
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 1000, "priority": "critical"},
            {"imp_id": "IMP-002", "estimated_tokens": 1000, "priority": "low"},
        ]
        frontier, count = priority_engine._compute_pareto_frontier(tasks)
        assert count == 1  # Only one on frontier
        # Order is preserved from input (topological order)
        assert len(frontier) == 2
        assert frontier[0]["imp_id"] == "IMP-001"
        assert frontier[1]["imp_id"] == "IMP-002"

    def test_pareto_frontier_empty(self, priority_engine: PriorityEngine) -> None:
        """Test frontier with empty list."""
        frontier, count = priority_engine._compute_pareto_frontier([])
        assert frontier == []
        assert count == 0


class TestBudgetConstraint:
    """Tests for budget constraint application."""

    def test_budget_constraint_within_budget(self, priority_engine: PriorityEngine) -> None:
        """Test when all tasks fit within budget."""
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 500},
            {"imp_id": "IMP-002", "estimated_tokens": 500},
        ]
        filtered, constrained = priority_engine._apply_budget_constraint(tasks, 2000)
        assert len(filtered) == 2
        assert not constrained

    def test_budget_constraint_exceeds_budget(self, priority_engine: PriorityEngine) -> None:
        """Test when tasks exceed budget."""
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 500},
            {"imp_id": "IMP-002", "estimated_tokens": 500},
            {"imp_id": "IMP-003", "estimated_tokens": 500},
        ]
        filtered, constrained = priority_engine._apply_budget_constraint(tasks, 800)
        assert len(filtered) == 1
        assert constrained

    def test_budget_constraint_exact_fit(self, priority_engine: PriorityEngine) -> None:
        """Test when tasks exactly fit budget."""
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 500},
            {"imp_id": "IMP-002", "estimated_tokens": 500},
        ]
        filtered, constrained = priority_engine._apply_budget_constraint(tasks, 1000)
        assert len(filtered) == 2
        assert not constrained

    def test_budget_constraint_zero_budget(self, priority_engine: PriorityEngine) -> None:
        """Test with zero budget."""
        tasks = [{"imp_id": "IMP-001", "estimated_tokens": 500}]
        filtered, constrained = priority_engine._apply_budget_constraint(tasks, 0)
        assert len(filtered) == 0
        assert constrained

    def test_budget_constraint_default_tokens(self, priority_engine: PriorityEngine) -> None:
        """Test default token cost when not specified."""
        tasks = [{"imp_id": "IMP-001"}]  # No estimated_tokens
        filtered, constrained = priority_engine._apply_budget_constraint(tasks, 1500)
        assert len(filtered) == 1  # Default is 1000


class TestComputeExecutionPlan:
    """Tests for the main compute_execution_plan method."""

    def test_compute_execution_plan_empty(self, priority_engine: PriorityEngine) -> None:
        """Test execution plan with empty tasks."""
        result = priority_engine.compute_execution_plan([])
        assert isinstance(result, ExecutionPlanResult)
        assert result.ordered_tasks == []
        assert result.total_estimated_tokens == 0.0
        assert result.dependency_graph == {}
        assert result.pareto_frontier_count == 0
        assert result.budget_constrained is False

    def test_compute_execution_plan_basic(self, priority_engine: PriorityEngine) -> None:
        """Test basic execution plan computation."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Task 1", "estimated_tokens": 500, "priority": "high"},
            {"imp_id": "IMP-002", "title": "Task 2", "estimated_tokens": 300, "priority": "low"},
        ]
        result = priority_engine.compute_execution_plan(tasks)
        assert isinstance(result, ExecutionPlanResult)
        assert len(result.ordered_tasks) == 2
        assert result.total_estimated_tokens == 800.0

    def test_compute_execution_plan_with_deps(self, priority_engine: PriorityEngine) -> None:
        """Test execution plan respects dependencies."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Foundation", "priority": "low"},
            {
                "imp_id": "IMP-002",
                "title": "Feature",
                "priority": "critical",
                "depends_on": ["IMP-001"],
            },
        ]
        result = priority_engine.compute_execution_plan(tasks)

        # IMP-001 must come before IMP-002
        ids = [t["imp_id"] for t in result.ordered_tasks]
        assert ids.index("IMP-001") < ids.index("IMP-002")

    def test_compute_execution_plan_with_budget(self, priority_engine: PriorityEngine) -> None:
        """Test execution plan with budget constraint."""
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 500, "priority": "high"},
            {"imp_id": "IMP-002", "estimated_tokens": 500, "priority": "medium"},
            {"imp_id": "IMP-003", "estimated_tokens": 500, "priority": "low"},
        ]
        result = priority_engine.compute_execution_plan(tasks, budget_tokens=800)
        assert result.budget_constrained is True
        assert len(result.ordered_tasks) < 3
        assert result.total_estimated_tokens <= 800

    def test_compute_execution_plan_complex(self, priority_engine: PriorityEngine) -> None:
        """Test complex execution plan with deps and budget."""
        tasks = [
            {"imp_id": "IMP-001", "title": "Base", "estimated_tokens": 200, "priority": "medium"},
            {
                "imp_id": "IMP-002",
                "title": "Feature A",
                "estimated_tokens": 300,
                "priority": "high",
                "depends_on": ["IMP-001"],
            },
            {
                "imp_id": "IMP-003",
                "title": "Feature B",
                "estimated_tokens": 400,
                "priority": "high",
                "depends_on": ["IMP-001"],
            },
            {
                "imp_id": "IMP-004",
                "title": "Integration",
                "estimated_tokens": 500,
                "priority": "critical",
                "depends_on": ["IMP-002", "IMP-003"],
            },
        ]
        result = priority_engine.compute_execution_plan(tasks)

        # Verify dependency order
        ids = [t["imp_id"] for t in result.ordered_tasks]
        assert ids.index("IMP-001") < ids.index("IMP-002")
        assert ids.index("IMP-001") < ids.index("IMP-003")
        assert ids.index("IMP-002") < ids.index("IMP-004")
        assert ids.index("IMP-003") < ids.index("IMP-004")

    def test_compute_execution_plan_result_attributes(
        self, priority_engine: PriorityEngine
    ) -> None:
        """Test all attributes of ExecutionPlanResult."""
        tasks = [
            {"imp_id": "IMP-001", "estimated_tokens": 500, "priority": "high"},
        ]
        result = priority_engine.compute_execution_plan(tasks)

        assert hasattr(result, "ordered_tasks")
        assert hasattr(result, "total_estimated_tokens")
        assert hasattr(result, "dependency_graph")
        assert hasattr(result, "pareto_frontier_count")
        assert hasattr(result, "budget_constrained")
        assert result.pareto_frontier_count >= 1
