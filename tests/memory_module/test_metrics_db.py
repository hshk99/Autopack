"""Tests for historical metrics database."""

import sys
from pathlib import Path

# Ensure src directory is in Python path for pytest-xdist workers
_src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import sqlite3  # noqa: E402

import pytest  # noqa: E402

from memory.metrics_db import MetricsDatabase  # noqa: E402


@pytest.fixture
def db(tmp_path):
    """Create a MetricsDatabase instance with a temp database."""
    db_path = tmp_path / "test_metrics.db"
    return MetricsDatabase(db_path=str(db_path))


class TestMetricsDatabaseInit:
    """Tests for MetricsDatabase initialization."""

    def test_init_creates_database_file(self, tmp_path):
        """Test that initialization creates the database file."""
        db_path = tmp_path / "test_metrics.db"
        MetricsDatabase(db_path=str(db_path))
        assert db_path.exists()

    def test_init_creates_parent_directories(self, tmp_path):
        """Test that initialization creates parent directories if needed."""
        db_path = tmp_path / "nested" / "path" / "test.db"
        MetricsDatabase(db_path=str(db_path))
        assert db_path.exists()

    def test_init_creates_tables(self, tmp_path):
        """Test that initialization creates required tables."""
        db_path = tmp_path / "test_metrics.db"
        MetricsDatabase(db_path=str(db_path))

        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

        assert "daily_metrics" in tables
        assert "phase_outcomes" in tables
        assert "failure_patterns" in tables


class TestDailyMetrics:
    """Tests for daily metrics storage and retrieval."""

    def test_store_daily_metrics(self, db):
        """Test storing daily metrics."""
        metrics = {
            "pr_merge_time_avg": 120.5,
            "ci_failure_rate": 0.15,
            "tasks_completed": 10,
            "stagnation_count": 2,
            "slot_utilization_avg": 0.75,
        }
        db.store_daily_metrics(metrics)

        retrieved = db.get_daily_metrics(days=1)
        assert len(retrieved) == 1
        assert retrieved[0]["pr_merge_time_avg"] == 120.5
        assert retrieved[0]["ci_failure_rate"] == 0.15
        assert retrieved[0]["tasks_completed"] == 10
        assert retrieved[0]["stagnation_count"] == 2
        assert retrieved[0]["slot_utilization_avg"] == 0.75

    def test_store_daily_metrics_with_defaults(self, db):
        """Test storing partial metrics uses defaults for missing values."""
        metrics = {"tasks_completed": 5}
        db.store_daily_metrics(metrics)

        retrieved = db.get_daily_metrics(days=1)
        assert len(retrieved) == 1
        assert retrieved[0]["tasks_completed"] == 5
        assert retrieved[0]["pr_merge_time_avg"] == 0.0
        assert retrieved[0]["ci_failure_rate"] == 0.0

    def test_store_daily_metrics_updates_same_day(self, db):
        """Test that storing metrics twice on same day updates the record."""
        db.store_daily_metrics({"tasks_completed": 5})
        db.store_daily_metrics({"tasks_completed": 10})

        retrieved = db.get_daily_metrics(days=1)
        assert len(retrieved) == 1
        assert retrieved[0]["tasks_completed"] == 10

    def test_get_daily_metrics_limits_results(self, db):
        """Test that get_daily_metrics respects the days limit."""
        db.store_daily_metrics({"tasks_completed": 1})

        retrieved = db.get_daily_metrics(days=30)
        assert len(retrieved) == 1

    def test_get_daily_metrics_empty(self, db):
        """Test retrieving metrics when none exist."""
        retrieved = db.get_daily_metrics()
        assert retrieved == []


class TestPhaseOutcomes:
    """Tests for phase outcome recording and retrieval."""

    def test_record_phase_outcome(self, db):
        """Test recording a phase outcome."""
        db.record_phase_outcome(
            phase_id="IMP-MEM-001",
            outcome="success",
            duration_seconds=3600.5,
            ci_runs=3,
        )

        outcomes = db.get_phase_outcomes()
        assert len(outcomes) == 1
        assert outcomes[0]["phase_id"] == "IMP-MEM-001"
        assert outcomes[0]["outcome"] == "success"
        assert outcomes[0]["duration_seconds"] == 3600.5
        assert outcomes[0]["ci_runs"] == 3
        assert outcomes[0]["timestamp"] is not None

    def test_record_multiple_phase_outcomes(self, db):
        """Test recording multiple phase outcomes."""
        db.record_phase_outcome("PHASE-1", "success", 100.0, 1)
        db.record_phase_outcome("PHASE-2", "failure", 200.0, 2)
        db.record_phase_outcome("PHASE-1", "success", 150.0, 1)

        outcomes = db.get_phase_outcomes()
        assert len(outcomes) == 3

    def test_get_phase_outcomes_filtered_by_phase_id(self, db):
        """Test retrieving outcomes filtered by phase_id."""
        db.record_phase_outcome("PHASE-1", "success", 100.0, 1)
        db.record_phase_outcome("PHASE-2", "failure", 200.0, 2)
        db.record_phase_outcome("PHASE-1", "success", 150.0, 1)

        outcomes = db.get_phase_outcomes(phase_id="PHASE-1")
        assert len(outcomes) == 2
        assert all(o["phase_id"] == "PHASE-1" for o in outcomes)

    def test_get_phase_outcomes_empty(self, db):
        """Test retrieving outcomes when none exist."""
        outcomes = db.get_phase_outcomes()
        assert outcomes == []


class TestFailurePatterns:
    """Tests for failure pattern recording and retrieval."""

    def test_record_failure_pattern(self, db):
        """Test recording a new failure pattern."""
        db.record_failure_pattern(
            pattern_hash="abc123",
            failure_type="lint_error",
            resolution="Run pre-commit",
        )

        patterns = db.get_failure_patterns()
        assert len(patterns) == 1
        assert patterns[0]["pattern_hash"] == "abc123"
        assert patterns[0]["failure_type"] == "lint_error"
        assert patterns[0]["occurrence_count"] == 1
        assert patterns[0]["resolution"] == "Run pre-commit"

    def test_record_failure_pattern_increments_count(self, db):
        """Test that recording same pattern increments count."""
        db.record_failure_pattern("abc123", "lint_error")
        db.record_failure_pattern("abc123", "lint_error")
        db.record_failure_pattern("abc123", "lint_error")

        patterns = db.get_failure_patterns()
        assert len(patterns) == 1
        assert patterns[0]["occurrence_count"] == 3

    def test_record_failure_pattern_updates_resolution(self, db):
        """Test that resolution is updated when provided."""
        db.record_failure_pattern("abc123", "lint_error", None)
        db.record_failure_pattern("abc123", "lint_error", "Fixed with pre-commit")

        patterns = db.get_failure_patterns()
        assert patterns[0]["resolution"] == "Fixed with pre-commit"

    def test_record_failure_pattern_preserves_resolution(self, db):
        """Test that existing resolution is preserved if new one is None."""
        db.record_failure_pattern("abc123", "lint_error", "Initial fix")
        db.record_failure_pattern("abc123", "lint_error", None)

        patterns = db.get_failure_patterns()
        assert patterns[0]["resolution"] == "Initial fix"

    def test_get_failure_patterns_filtered_by_type(self, db):
        """Test retrieving patterns filtered by failure type."""
        db.record_failure_pattern("hash1", "lint_error")
        db.record_failure_pattern("hash2", "test_failure")
        db.record_failure_pattern("hash3", "lint_error")

        patterns = db.get_failure_patterns(failure_type="lint_error")
        assert len(patterns) == 2
        assert all(p["failure_type"] == "lint_error" for p in patterns)

    def test_get_failure_patterns_empty(self, db):
        """Test retrieving patterns when none exist."""
        patterns = db.get_failure_patterns()
        assert patterns == []


class TestMetricsDatabaseIntegration:
    """Integration tests for MetricsDatabase."""

    def test_multiple_operations_same_connection(self, db):
        """Test that multiple operations work correctly."""
        db.store_daily_metrics({"tasks_completed": 5, "ci_failure_rate": 0.1})

        db.record_phase_outcome("PHASE-1", "success", 100.0, 1)
        db.record_phase_outcome("PHASE-1", "failure", 50.0, 2)

        db.record_failure_pattern("hash1", "lint_error", "Run black")

        daily = db.get_daily_metrics()
        assert len(daily) == 1
        assert daily[0]["tasks_completed"] == 5

        phases = db.get_phase_outcomes(phase_id="PHASE-1")
        assert len(phases) == 2

        patterns = db.get_failure_patterns()
        assert len(patterns) == 1
        assert patterns[0]["resolution"] == "Run black"

    def test_database_persistence(self, tmp_path):
        """Test that data persists across database instances."""
        db_path = tmp_path / "test_metrics.db"

        db1 = MetricsDatabase(db_path=str(db_path))
        db1.store_daily_metrics({"tasks_completed": 10})
        db1.record_phase_outcome("PHASE-1", "success", 100.0, 1)

        db2 = MetricsDatabase(db_path=str(db_path))
        daily = db2.get_daily_metrics()
        phases = db2.get_phase_outcomes()

        assert len(daily) == 1
        assert daily[0]["tasks_completed"] == 10
        assert len(phases) == 1
        assert phases[0]["phase_id"] == "PHASE-1"
