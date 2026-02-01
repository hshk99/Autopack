"""Tests for effectiveness feedback to task generation (IMP-TASK-001).

Tests the integration between TaskEffectivenessTracker and PriorityEngine
to ensure effectiveness data is persisted and used for task prioritization.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopack.memory.learning_db import LearningDatabase
from autopack.task_generation.priority_engine import PriorityEngine
from autopack.task_generation.task_effectiveness_tracker import (
    TaskEffectivenessTracker, TaskImpactReport)


class TestTaskEffectivenessTrackerWithLearningDb:
    """Tests for TaskEffectivenessTracker with LearningDatabase integration."""

    @pytest.fixture
    def learning_db(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase for testing."""
        db_path = tmp_path / "learning_db.json"
        return LearningDatabase(db_path)

    @pytest.fixture
    def tracker_with_db(self, learning_db: LearningDatabase) -> TaskEffectivenessTracker:
        """Create a tracker with learning database."""
        return TaskEffectivenessTracker(learning_db=learning_db)

    def test_init_with_learning_db(self, learning_db: LearningDatabase) -> None:
        """Test tracker initializes with learning database."""
        tracker = TaskEffectivenessTracker(learning_db=learning_db)
        assert tracker._learning_db is learning_db

    def test_set_learning_db(self) -> None:
        """Test setting learning database after initialization."""
        tracker = TaskEffectivenessTracker()
        assert tracker._learning_db is None

        learning_db = MagicMock()
        learning_db.get_historical_patterns.return_value = {"category_success_rates": {}}
        tracker.set_learning_db(learning_db)
        assert tracker._learning_db is learning_db


class TestPersistEffectivenessReport:
    """Tests for persist_effectiveness_report method."""

    @pytest.fixture
    def learning_db(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase for testing."""
        db_path = tmp_path / "learning_db.json"
        return LearningDatabase(db_path)

    @pytest.fixture
    def tracker(self, learning_db: LearningDatabase) -> TaskEffectivenessTracker:
        """Create a tracker with learning database."""
        return TaskEffectivenessTracker(learning_db=learning_db)

    def test_persist_excellent_report(
        self, tracker: TaskEffectivenessTracker, learning_db: LearningDatabase
    ) -> None:
        """Test persisting excellent effectiveness report."""
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target_improvement=0.5,
            actual_improvement=0.9,
            effectiveness_score=0.95,  # Excellent
            measured_at=datetime.now(),
            category="telemetry",
        )

        result = tracker.persist_effectiveness_report(report)
        assert result is True

        # Verify persisted to learning database
        imp_record = learning_db.get_improvement("IMP-TEST-001")
        assert imp_record is not None
        assert imp_record["current_outcome"] == "implemented"
        assert imp_record["category"] == "telemetry"

    def test_persist_good_report(
        self, tracker: TaskEffectivenessTracker, learning_db: LearningDatabase
    ) -> None:
        """Test persisting good effectiveness report."""
        report = TaskImpactReport(
            task_id="IMP-TEST-002",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=0.75,  # Good
            measured_at=datetime.now(),
            category="memory",
        )

        result = tracker.persist_effectiveness_report(report)
        assert result is True

        imp_record = learning_db.get_improvement("IMP-TEST-002")
        assert imp_record["current_outcome"] == "implemented"

    def test_persist_moderate_report(
        self, tracker: TaskEffectivenessTracker, learning_db: LearningDatabase
    ) -> None:
        """Test persisting moderate effectiveness report."""
        report = TaskImpactReport(
            task_id="IMP-TEST-003",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target_improvement=0.5,
            actual_improvement=0.25,
            effectiveness_score=0.5,  # Moderate
            measured_at=datetime.now(),
            category="memory",
        )

        result = tracker.persist_effectiveness_report(report)
        assert result is True

        imp_record = learning_db.get_improvement("IMP-TEST-003")
        assert imp_record["current_outcome"] == "partial"

    def test_persist_poor_report(
        self, tracker: TaskEffectivenessTracker, learning_db: LearningDatabase
    ) -> None:
        """Test persisting poor effectiveness report."""
        report = TaskImpactReport(
            task_id="IMP-TEST-004",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.22},
            target_improvement=0.5,
            actual_improvement=-0.1,
            effectiveness_score=0.1,  # Poor
            measured_at=datetime.now(),
            category="telemetry",
        )

        result = tracker.persist_effectiveness_report(report)
        assert result is True

        imp_record = learning_db.get_improvement("IMP-TEST-004")
        assert imp_record["current_outcome"] == "blocked"

    def test_persist_without_learning_db(self) -> None:
        """Test persist returns False without learning database."""
        tracker = TaskEffectivenessTracker()
        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={},
            after_metrics={},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=1.0,
            measured_at=datetime.now(),
        )

        result = tracker.persist_effectiveness_report(report)
        assert result is False


class TestPersistAllReports:
    """Tests for persist_all_reports method."""

    @pytest.fixture
    def learning_db(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase for testing."""
        db_path = tmp_path / "learning_db.json"
        return LearningDatabase(db_path)

    @pytest.fixture
    def tracker(self, learning_db: LearningDatabase) -> TaskEffectivenessTracker:
        """Create a tracker with learning database."""
        return TaskEffectivenessTracker(learning_db=learning_db)

    def test_persist_all_reports(
        self, tracker: TaskEffectivenessTracker, learning_db: LearningDatabase
    ) -> None:
        """Test batch persisting all reports."""
        # Add some measurements
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
            category="telemetry",
        )
        tracker.measure_impact(
            task_id="IMP-TEST-002",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.05},
            target=0.5,
            category="memory",
        )

        # Persist all
        persisted = tracker.persist_all_reports()
        assert persisted == 2

        # Verify both persisted
        assert learning_db.get_improvement("IMP-TEST-001") is not None
        assert learning_db.get_improvement("IMP-TEST-002") is not None

    def test_persist_all_without_learning_db(self) -> None:
        """Test persist_all returns 0 without learning database."""
        tracker = TaskEffectivenessTracker()
        tracker.measure_impact(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
        )

        persisted = tracker.persist_all_reports()
        assert persisted == 0


class TestLoadFromLearningDb:
    """Tests for _load_from_learning_db method."""

    @pytest.fixture
    def learning_db_with_data(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase with historical data."""
        db_path = tmp_path / "learning_db.json"
        db = LearningDatabase(db_path)

        # Add historical outcomes
        db.record_improvement_outcome("IMP-TEL-001", "implemented", "Success", "telemetry")
        db.record_improvement_outcome("IMP-TEL-002", "implemented", "Success", "telemetry")
        db.record_improvement_outcome("IMP-MEM-001", "blocked", "Failed", "memory")
        db.record_improvement_outcome("IMP-MEM-002", "implemented", "Success", "memory")

        return db

    def test_load_historical_effectiveness(self, learning_db_with_data: LearningDatabase) -> None:
        """Test loading historical effectiveness on initialization."""
        tracker = TaskEffectivenessTracker(learning_db=learning_db_with_data)

        # Check telemetry category loaded (100% success rate)
        assert "telemetry" in tracker.history.category_stats
        stats = tracker.history.category_stats["telemetry"]
        assert stats["avg_effectiveness"] == pytest.approx(1.0)

        # Check memory category loaded (50% success rate)
        assert "memory" in tracker.history.category_stats
        stats = tracker.history.category_stats["memory"]
        assert stats["avg_effectiveness"] == pytest.approx(0.5)

    def test_get_category_effectiveness_with_history(
        self, learning_db_with_data: LearningDatabase
    ) -> None:
        """Test get_category_effectiveness_with_history method."""
        tracker = TaskEffectivenessTracker(learning_db=learning_db_with_data)

        # Should use loaded historical data
        tel_effectiveness = tracker.get_category_effectiveness_with_history("telemetry")
        assert tel_effectiveness == pytest.approx(1.0)

        mem_effectiveness = tracker.get_category_effectiveness_with_history("memory")
        assert mem_effectiveness == pytest.approx(0.5)

        # Unknown category should return default
        unknown_effectiveness = tracker.get_category_effectiveness_with_history("unknown")
        assert unknown_effectiveness == 0.5

    def test_get_category_effectiveness_prefers_current_data(
        self, learning_db_with_data: LearningDatabase
    ) -> None:
        """Test that current data is preferred over historical."""
        tracker = TaskEffectivenessTracker(learning_db=learning_db_with_data)

        # Add current measurement that differs from historical
        tracker.measure_impact(
            task_id="IMP-TEL-NEW",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target=0.5,
            category="telemetry",
        )

        # Now get_category_effectiveness_with_history should mix both
        effectiveness = tracker.get_category_effectiveness_with_history("telemetry")
        # Historical had 100% (2/2), new measurement adds data
        # The current session's measurement should be reflected
        assert effectiveness != pytest.approx(1.0)


class TestPriorityEngineWithEffectivenessTracker:
    """Tests for PriorityEngine with TaskEffectivenessTracker integration."""

    @pytest.fixture
    def mock_learning_db(self) -> MagicMock:
        """Create a mock LearningDatabase."""
        db = MagicMock()
        db.get_success_rate.return_value = 0.7
        db.get_likely_blockers.return_value = []
        db.get_historical_patterns.return_value = {
            "top_blocking_reasons": [],
            "category_success_rates": {},
            "recent_trends": {"sample_size": 0},
        }
        return db

    @pytest.fixture
    def tracker_with_data(self) -> TaskEffectivenessTracker:
        """Create a tracker with effectiveness data."""
        tracker = TaskEffectivenessTracker()
        # Add measurements for different categories
        tracker.measure_impact(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
            category="telemetry",
        )
        tracker.measure_impact(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.18},
            target=0.5,
            category="memory",
        )
        return tracker

    def test_init_with_effectiveness_tracker(
        self, mock_learning_db: MagicMock, tracker_with_data: TaskEffectivenessTracker
    ) -> None:
        """Test PriorityEngine initializes with effectiveness tracker."""
        engine = PriorityEngine(mock_learning_db, effectiveness_tracker=tracker_with_data)
        assert engine._effectiveness_tracker is tracker_with_data

    def test_set_effectiveness_tracker(
        self, mock_learning_db: MagicMock, tracker_with_data: TaskEffectivenessTracker
    ) -> None:
        """Test setting effectiveness tracker after initialization."""
        engine = PriorityEngine(mock_learning_db)
        assert engine._effectiveness_tracker is None

        engine.set_effectiveness_tracker(tracker_with_data)
        assert engine._effectiveness_tracker is tracker_with_data

    def test_set_effectiveness_tracker_clears_cache(
        self, mock_learning_db: MagicMock, tracker_with_data: TaskEffectivenessTracker
    ) -> None:
        """Test that setting tracker clears pattern cache."""
        engine = PriorityEngine(mock_learning_db)
        # Populate cache
        engine._get_cached_patterns()
        assert engine._patterns_cache is not None

        # Set tracker
        engine.set_effectiveness_tracker(tracker_with_data)
        assert engine._patterns_cache is None


class TestGetEffectivenessFactorWithTracker:
    """Tests for get_effectiveness_factor using TaskEffectivenessTracker."""

    @pytest.fixture
    def mock_learning_db(self) -> MagicMock:
        """Create a mock LearningDatabase."""
        db = MagicMock()
        db.get_success_rate.return_value = 0.5
        db.get_likely_blockers.return_value = []
        return db

    def test_effectiveness_factor_from_tracker(self, mock_learning_db: MagicMock) -> None:
        """Test effectiveness factor uses tracker data."""
        tracker = TaskEffectivenessTracker()
        # High effectiveness for telemetry
        tracker.measure_impact(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
            category="telemetry",
        )

        engine = PriorityEngine(mock_learning_db, effectiveness_tracker=tracker)

        imp = {"imp_id": "IMP-TEL-002", "category": "telemetry", "priority": "high"}
        factor = engine.get_effectiveness_factor(imp)

        # Should be high due to excellent telemetry effectiveness
        assert factor > 1.0

    def test_effectiveness_factor_low_for_poor_category(self, mock_learning_db: MagicMock) -> None:
        """Test effectiveness factor is low for poorly performing category."""
        tracker = TaskEffectivenessTracker()
        # Poor effectiveness for memory
        tracker.measure_impact(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.2},
            target=0.5,
            category="memory",
        )

        engine = PriorityEngine(mock_learning_db, effectiveness_tracker=tracker)

        imp = {"imp_id": "IMP-MEM-002", "category": "memory", "priority": "high"}
        factor = engine.get_effectiveness_factor(imp)

        # Should be low due to poor memory effectiveness
        assert factor < 1.0

    def test_effectiveness_factor_without_tracker(self, mock_learning_db: MagicMock) -> None:
        """Test effectiveness factor returns 1.0 without tracker."""
        engine = PriorityEngine(mock_learning_db)

        imp = {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "high"}
        factor = engine.get_effectiveness_factor(imp)

        assert factor == 1.0

    def test_effectiveness_factor_unknown_category(self, mock_learning_db: MagicMock) -> None:
        """Test effectiveness factor for unknown category."""
        tracker = TaskEffectivenessTracker()
        # Add data for telemetry only
        tracker.measure_impact(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target=0.5,
            category="telemetry",
        )

        engine = PriorityEngine(mock_learning_db, effectiveness_tracker=tracker)

        # Query for unknown category
        imp = {"imp_id": "IMP-UNK-001", "category": "unknown", "priority": "high"}
        factor = engine.get_effectiveness_factor(imp)

        # Should return 1.0 (no data for this category)
        assert factor == 1.0


class TestPriorityScoreWithEffectiveness:
    """Tests for priority score calculation with effectiveness feedback."""

    @pytest.fixture
    def learning_db(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase for testing."""
        db_path = tmp_path / "learning_db.json"
        return LearningDatabase(db_path)

    def test_high_effectiveness_boosts_priority(self, learning_db: LearningDatabase) -> None:
        """Test that high effectiveness boosts priority score."""
        tracker = TaskEffectivenessTracker()
        # Excellent telemetry effectiveness
        for i in range(3):
            tracker.measure_impact(
                task_id=f"IMP-TEL-{i}",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.02},
                target=0.5,
                category="telemetry",
            )

        engine = PriorityEngine(learning_db, effectiveness_tracker=tracker)

        # Score telemetry improvement
        tel_imp = {"imp_id": "IMP-TEL-NEW", "category": "telemetry", "priority": "high"}
        tel_score = engine.calculate_priority_score(tel_imp)

        # Score improvement without tracker data
        engine_no_tracker = PriorityEngine(learning_db)
        baseline_score = engine_no_tracker.calculate_priority_score(tel_imp)

        # Telemetry should score higher with effectiveness data
        assert tel_score > baseline_score

    def test_low_effectiveness_reduces_priority(self, learning_db: LearningDatabase) -> None:
        """Test that low effectiveness reduces priority score."""
        tracker = TaskEffectivenessTracker()
        # Poor memory effectiveness
        for i in range(3):
            tracker.measure_impact(
                task_id=f"IMP-MEM-{i}",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.2},  # No improvement
                target=0.5,
                category="memory",
            )

        engine = PriorityEngine(learning_db, effectiveness_tracker=tracker)

        # Score memory improvement
        mem_imp = {"imp_id": "IMP-MEM-NEW", "category": "memory", "priority": "high"}
        mem_score = engine.calculate_priority_score(mem_imp)

        # Score improvement without tracker data
        engine_no_tracker = PriorityEngine(learning_db)
        baseline_score = engine_no_tracker.calculate_priority_score(mem_imp)

        # Memory should score lower with poor effectiveness data
        assert mem_score < baseline_score


class TestEndToEndEffectivenessFeedback:
    """End-to-end tests for the effectiveness feedback loop."""

    @pytest.fixture
    def learning_db(self, tmp_path: Path) -> LearningDatabase:
        """Create a LearningDatabase for testing."""
        db_path = tmp_path / "learning_db.json"
        return LearningDatabase(db_path)

    def test_full_feedback_loop(self, learning_db: LearningDatabase) -> None:
        """Test the complete feedback loop from measurement to prioritization."""
        # 1. Create tracker with learning database
        tracker = TaskEffectivenessTracker(learning_db=learning_db)

        # 2. Measure some task impacts
        tracker.measure_impact(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
            category="telemetry",
        )
        tracker.measure_impact(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.18},
            target=0.5,
            category="memory",
        )

        # 3. Persist to learning database
        persisted = tracker.persist_all_reports()
        assert persisted == 2

        # 4. Create new tracker (simulating new run) with same database
        new_tracker = TaskEffectivenessTracker(learning_db=learning_db)

        # 5. Verify historical data is loaded
        tel_effectiveness = new_tracker.get_category_effectiveness_with_history("telemetry")
        mem_effectiveness = new_tracker.get_category_effectiveness_with_history("memory")
        assert tel_effectiveness > mem_effectiveness

        # 6. Create priority engine with new tracker
        engine = PriorityEngine(learning_db, effectiveness_tracker=new_tracker)

        # 7. Score new improvements - telemetry should rank higher
        tel_imp = {"imp_id": "IMP-TEL-002", "category": "telemetry", "priority": "high"}
        mem_imp = {"imp_id": "IMP-MEM-002", "category": "memory", "priority": "high"}

        tel_score = engine.calculate_priority_score(tel_imp)
        mem_score = engine.calculate_priority_score(mem_imp)

        assert tel_score > mem_score

    def test_ranking_reflects_effectiveness(self, learning_db: LearningDatabase) -> None:
        """Test that ranking order reflects category effectiveness."""
        # Setup effectiveness data
        tracker = TaskEffectivenessTracker(learning_db=learning_db)

        # Excellent telemetry
        tracker.measure_impact(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target=0.5,
            category="telemetry",
        )

        # Good api
        tracker.measure_impact(
            task_id="IMP-API-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.08},
            target=0.5,
            category="api",
        )

        # Poor memory
        tracker.measure_impact(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.19},
            target=0.5,
            category="memory",
        )

        # Create engine with tracker
        engine = PriorityEngine(learning_db, effectiveness_tracker=tracker)

        # Rank improvements (all same priority level)
        improvements = [
            {"imp_id": "IMP-MEM-002", "category": "memory", "priority": "high"},
            {"imp_id": "IMP-TEL-002", "category": "telemetry", "priority": "high"},
            {"imp_id": "IMP-API-002", "category": "api", "priority": "high"},
        ]

        ranked = engine.rank_improvements(improvements, include_scores=True)

        # Telemetry should be first (highest effectiveness)
        assert ranked[0]["category"] == "telemetry"
        # API should be second
        assert ranked[1]["category"] == "api"
        # Memory should be last (lowest effectiveness)
        assert ranked[2]["category"] == "memory"


class TestCategoryWeightMultiplier:
    """Tests for IMP-TASK-003: Category weight multiplier functionality."""

    @pytest.fixture
    def mock_learning_db(self) -> MagicMock:
        """Create a mock LearningDatabase."""
        db = MagicMock()
        db.get_success_rate.return_value = 0.5
        db.get_likely_blockers.return_value = []
        db.get_historical_patterns.return_value = {
            "top_blocking_reasons": [],
            "category_success_rates": {},
            "recent_trends": {"sample_size": 0},
        }
        return db

    def test_initial_multiplier_is_one(self, mock_learning_db: MagicMock) -> None:
        """Test that initial category multiplier is 1.0."""
        engine = PriorityEngine(mock_learning_db)
        assert engine.get_category_weight_multiplier("telemetry") == 1.0
        assert engine.get_category_weight_multiplier("memory") == 1.0
        assert engine.get_category_weight_multiplier("unknown") == 1.0

    def test_update_category_weight_multiplier(self, mock_learning_db: MagicMock) -> None:
        """Test updating category weight multiplier."""
        engine = PriorityEngine(mock_learning_db)

        engine.update_category_weight_multiplier("telemetry", 1.2)
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(1.2)

        engine.update_category_weight_multiplier("memory", 0.8)
        assert engine.get_category_weight_multiplier("memory") == pytest.approx(0.8)

    def test_multiplier_clamped_to_max(self, mock_learning_db: MagicMock) -> None:
        """Test that multiplier is clamped to max 2.0."""
        engine = PriorityEngine(mock_learning_db)

        engine.update_category_weight_multiplier("telemetry", 5.0)
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(2.0)

    def test_multiplier_clamped_to_min(self, mock_learning_db: MagicMock) -> None:
        """Test that multiplier is clamped to min 0.1."""
        engine = PriorityEngine(mock_learning_db)

        engine.update_category_weight_multiplier("memory", 0.01)
        assert engine.get_category_weight_multiplier("memory") == pytest.approx(0.1)

    def test_multiplier_applied_to_priority_score(self, mock_learning_db: MagicMock) -> None:
        """Test that multiplier affects priority score calculation."""
        engine = PriorityEngine(mock_learning_db)

        imp = {"imp_id": "IMP-TEL-001", "category": "telemetry", "priority": "high"}

        # Get baseline score
        baseline_score = engine.calculate_priority_score(imp)

        # Apply boost multiplier
        engine.update_category_weight_multiplier("telemetry", 1.5)
        boosted_score = engine.calculate_priority_score(imp)

        # Boosted score should be higher
        assert boosted_score > baseline_score
        # Allow for rounding tolerance (score is rounded to 3 decimal places)
        assert boosted_score == pytest.approx(baseline_score * 1.5, abs=0.001)

    def test_multiplier_penalty_reduces_score(self, mock_learning_db: MagicMock) -> None:
        """Test that penalty multiplier reduces priority score."""
        engine = PriorityEngine(mock_learning_db)

        imp = {"imp_id": "IMP-MEM-001", "category": "memory", "priority": "high"}

        # Get baseline score
        baseline_score = engine.calculate_priority_score(imp)

        # Apply penalty multiplier
        engine.update_category_weight_multiplier("memory", 0.7)
        penalized_score = engine.calculate_priority_score(imp)

        # Penalized score should be lower
        assert penalized_score < baseline_score
        # Allow for rounding tolerance (score is rounded to 3 decimal places)
        assert penalized_score == pytest.approx(baseline_score * 0.7, abs=0.001)


class TestFeedBackToPriorityEngineComplete:
    """Tests for IMP-TASK-003: Complete feedback loop integration."""

    @pytest.fixture
    def mock_learning_db(self) -> MagicMock:
        """Create a mock LearningDatabase."""
        db = MagicMock()
        db.get_success_rate.return_value = 0.5
        db.get_likely_blockers.return_value = []
        db.get_historical_patterns.return_value = {
            "top_blocking_reasons": [],
            "category_success_rates": {},
            "recent_trends": {"sample_size": 0},
        }
        return db

    def test_feed_back_updates_multiplier_excellent(self, mock_learning_db: MagicMock) -> None:
        """Test that excellent effectiveness boosts multiplier."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        report = TaskImpactReport(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target_improvement=0.5,
            actual_improvement=0.9,
            effectiveness_score=0.95,  # Excellent
            measured_at=datetime.now(),
            category="telemetry",
        )

        tracker.feed_back_to_priority_engine(report)

        # Multiplier should be boosted (1.0 * 1.2 = 1.2)
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(1.2)

    def test_feed_back_updates_multiplier_good(self, mock_learning_db: MagicMock) -> None:
        """Test that good effectiveness boosts multiplier."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        report = TaskImpactReport(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.08},
            target_improvement=0.5,
            actual_improvement=0.6,
            effectiveness_score=0.75,  # Good
            measured_at=datetime.now(),
            category="api",
        )

        tracker.feed_back_to_priority_engine(report)

        # Multiplier should be boosted (1.0 * 1.1 = 1.1)
        assert engine.get_category_weight_multiplier("api") == pytest.approx(1.1)

    def test_feed_back_updates_multiplier_poor(self, mock_learning_db: MagicMock) -> None:
        """Test that poor effectiveness reduces multiplier."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        report = TaskImpactReport(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.22},
            target_improvement=0.5,
            actual_improvement=-0.1,
            effectiveness_score=0.1,  # Poor
            measured_at=datetime.now(),
            category="memory",
        )

        tracker.feed_back_to_priority_engine(report)

        # Multiplier should be reduced (1.0 * 0.9 = 0.9)
        assert engine.get_category_weight_multiplier("memory") == pytest.approx(0.9)

    def test_feed_back_moderate_no_change(self, mock_learning_db: MagicMock) -> None:
        """Test that moderate effectiveness keeps multiplier unchanged."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.15},
            target_improvement=0.5,
            actual_improvement=0.25,
            effectiveness_score=0.5,  # Moderate
            measured_at=datetime.now(),
            category="testing",
        )

        tracker.feed_back_to_priority_engine(report)

        # Multiplier should stay at 1.0 (1.0 * 1.0 = 1.0)
        assert engine.get_category_weight_multiplier("testing") == pytest.approx(1.0)

    def test_feed_back_cumulative(self, mock_learning_db: MagicMock) -> None:
        """Test that multiple feedbacks accumulate multipliers."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        # First excellent report
        report1 = TaskImpactReport(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target_improvement=0.5,
            actual_improvement=0.9,
            effectiveness_score=0.95,  # Excellent
            measured_at=datetime.now(),
            category="telemetry",
        )
        tracker.feed_back_to_priority_engine(report1)
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(1.2)

        # Second excellent report
        report2 = TaskImpactReport(
            task_id="IMP-TEL-002",
            before_metrics={"error_rate": 0.1},
            after_metrics={"error_rate": 0.01},
            target_improvement=0.5,
            actual_improvement=0.9,
            effectiveness_score=0.95,  # Excellent
            measured_at=datetime.now(),
            category="telemetry",
        )
        tracker.feed_back_to_priority_engine(report2)
        # Should be 1.2 * 1.2 = 1.44
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(1.44)

    def test_feed_back_clamped_at_max(self, mock_learning_db: MagicMock) -> None:
        """Test that cumulative feedback is clamped at max."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        # Multiple excellent reports to hit max
        for i in range(10):
            report = TaskImpactReport(
                task_id=f"IMP-TEL-{i:03d}",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.02},
                target_improvement=0.5,
                actual_improvement=0.9,
                effectiveness_score=0.95,  # Excellent
                measured_at=datetime.now(),
                category="telemetry",
            )
            tracker.feed_back_to_priority_engine(report)

        # Should be clamped at 2.0
        assert engine.get_category_weight_multiplier("telemetry") == pytest.approx(2.0)

    def test_feed_back_clamped_at_min(self, mock_learning_db: MagicMock) -> None:
        """Test that cumulative feedback is clamped at min."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        # Multiple poor reports to hit min
        for i in range(30):
            report = TaskImpactReport(
                task_id=f"IMP-MEM-{i:03d}",
                before_metrics={"error_rate": 0.2},
                after_metrics={"error_rate": 0.25},
                target_improvement=0.5,
                actual_improvement=-0.25,
                effectiveness_score=0.1,  # Poor
                measured_at=datetime.now(),
                category="memory",
            )
            tracker.feed_back_to_priority_engine(report)

        # Should be clamped at 0.1
        assert engine.get_category_weight_multiplier("memory") == pytest.approx(0.1)

    def test_feed_back_affects_priority_calculation(self, mock_learning_db: MagicMock) -> None:
        """Test that feedback actually affects priority scores."""
        engine = PriorityEngine(mock_learning_db)
        tracker = TaskEffectivenessTracker(priority_engine=engine)

        tel_imp = {"imp_id": "IMP-TEL-NEW", "category": "telemetry", "priority": "high"}
        mem_imp = {"imp_id": "IMP-MEM-NEW", "category": "memory", "priority": "high"}

        # Get baseline scores
        tel_baseline = engine.calculate_priority_score(tel_imp)
        mem_baseline = engine.calculate_priority_score(mem_imp)

        # Feed back excellent telemetry
        tel_report = TaskImpactReport(
            task_id="IMP-TEL-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.02},
            target_improvement=0.5,
            actual_improvement=0.9,
            effectiveness_score=0.95,
            measured_at=datetime.now(),
            category="telemetry",
        )
        tracker.feed_back_to_priority_engine(tel_report)

        # Feed back poor memory
        mem_report = TaskImpactReport(
            task_id="IMP-MEM-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.25},
            target_improvement=0.5,
            actual_improvement=-0.25,
            effectiveness_score=0.1,
            measured_at=datetime.now(),
            category="memory",
        )
        tracker.feed_back_to_priority_engine(mem_report)

        # Get new scores
        tel_after = engine.calculate_priority_score(tel_imp)
        mem_after = engine.calculate_priority_score(mem_imp)

        # Telemetry should be boosted
        assert tel_after > tel_baseline
        # Memory should be penalized
        assert mem_after < mem_baseline

    def test_feed_back_no_priority_engine(self) -> None:
        """Test that feedback without priority engine logs but doesn't fail."""
        tracker = TaskEffectivenessTracker()  # No priority engine

        report = TaskImpactReport(
            task_id="IMP-TEST-001",
            before_metrics={"error_rate": 0.2},
            after_metrics={"error_rate": 0.1},
            target_improvement=0.5,
            actual_improvement=0.5,
            effectiveness_score=0.8,
            measured_at=datetime.now(),
            category="testing",
        )

        # Should not raise exception
        tracker.feed_back_to_priority_engine(report)
