"""Tests for LearningDatabase in autopack.memory module.

Tests cover:
- Database initialization and persistence
- Recording cycle outcomes
- Recording improvement outcomes
- Querying historical patterns
- Success rate calculation
- Edge cases and error handling
"""

import json
from pathlib import Path

import pytest

from autopack.memory.learning_db import VALID_OUTCOMES, LearningDatabase


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary path for the database file."""
    return tmp_path / "test_learning_history.json"


@pytest.fixture
def learning_db(temp_db_path: Path) -> LearningDatabase:
    """Create a fresh LearningDatabase instance."""
    return LearningDatabase(temp_db_path)


@pytest.fixture
def populated_db(temp_db_path: Path) -> LearningDatabase:
    """Create a LearningDatabase with sample data."""
    db = LearningDatabase(temp_db_path)

    # Record some improvements
    db.record_improvement_outcome(
        "IMP-MEM-001", "implemented", "Successfully deployed", "memory", "critical"
    )
    db.record_improvement_outcome(
        "IMP-MEM-002", "blocked", "Missing dependencies", "memory", "high"
    )
    db.record_improvement_outcome("IMP-TEL-001", "implemented", "Working well", "telemetry", "high")
    db.record_improvement_outcome(
        "IMP-TEL-002", "abandoned", "No longer needed", "telemetry", "medium"
    )

    # Record some cycles
    db.record_cycle_outcome(
        "cycle-001",
        {
            "phases_completed": 5,
            "phases_blocked": 1,
            "total_nudges": 12,
            "total_escalations": 2,
            "duration_hours": 4.5,
            "completion_rate": 0.83,
            "blocking_reasons": ["dependency_issue", "timeout"],
        },
    )
    db.record_cycle_outcome(
        "cycle-002",
        {
            "phases_completed": 6,
            "phases_blocked": 0,
            "total_nudges": 8,
            "total_escalations": 0,
            "duration_hours": 3.2,
            "completion_rate": 1.0,
        },
    )

    return db


class TestLearningDatabaseInit:
    """Tests for LearningDatabase initialization."""

    def test_init_creates_empty_db(self, temp_db_path: Path) -> None:
        """Test that init creates an empty database if file doesn't exist."""
        db = LearningDatabase(temp_db_path)

        assert db.db_path == temp_db_path
        assert db._data["schema_version"] == 1
        assert db._data["improvements"] == {}
        assert db._data["cycles"] == {}

    def test_init_with_string_path(self, tmp_path: Path) -> None:
        """Test that init accepts string paths."""
        path_str = str(tmp_path / "test.json")
        db = LearningDatabase(path_str)

        assert db.db_path == Path(path_str)

    def test_init_loads_existing_db(self, temp_db_path: Path) -> None:
        """Test that init loads existing database file."""
        # Create a database file
        existing_data = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "improvements": {"IMP-001": {"imp_id": "IMP-001", "current_outcome": "implemented"}},
            "cycles": {},
            "patterns": {
                "phase_correlations": {},
                "blocking_reasons": {},
                "category_success_rates": {},
            },
        }
        temp_db_path.write_text(json.dumps(existing_data))

        db = LearningDatabase(temp_db_path)

        assert "IMP-001" in db._data["improvements"]

    def test_init_handles_invalid_json(self, temp_db_path: Path) -> None:
        """Test that init handles invalid JSON gracefully."""
        temp_db_path.write_text("{ invalid json }")

        db = LearningDatabase(temp_db_path)

        # Should create empty schema
        assert db._data["schema_version"] == 1
        assert db._data["improvements"] == {}


class TestRecordCycleOutcome:
    """Tests for record_cycle_outcome() method."""

    def test_record_cycle_basic(self, learning_db: LearningDatabase) -> None:
        """Test recording a basic cycle outcome."""
        metrics = {
            "phases_completed": 5,
            "phases_blocked": 1,
            "total_nudges": 10,
            "total_escalations": 2,
            "duration_hours": 3.5,
            "completion_rate": 0.83,
        }

        result = learning_db.record_cycle_outcome("cycle-001", metrics)

        assert result is True
        cycle = learning_db.get_cycle("cycle-001")
        assert cycle is not None
        assert cycle["metrics"]["phases_completed"] == 5
        assert cycle["metrics"]["completion_rate"] == 0.83

    def test_record_cycle_persists(self, temp_db_path: Path) -> None:
        """Test that cycle data is persisted to file."""
        db = LearningDatabase(temp_db_path)
        db.record_cycle_outcome("cycle-001", {"completion_rate": 0.9})

        # Create new instance to verify persistence
        db2 = LearningDatabase(temp_db_path)
        cycle = db2.get_cycle("cycle-001")

        assert cycle is not None
        assert cycle["metrics"]["completion_rate"] == 0.9

    def test_record_cycle_empty_id_fails(self, learning_db: LearningDatabase) -> None:
        """Test that empty cycle_id returns False."""
        result = learning_db.record_cycle_outcome("", {"phases_completed": 5})

        assert result is False

    def test_record_cycle_with_blocking_reasons(self, learning_db: LearningDatabase) -> None:
        """Test recording cycle with blocking reasons updates patterns."""
        metrics = {
            "phases_completed": 4,
            "phases_blocked": 2,
            "blocking_reasons": ["timeout", "dependency_issue"],
        }

        learning_db.record_cycle_outcome("cycle-001", metrics)

        patterns = learning_db.get_historical_patterns()
        assert len(patterns["top_blocking_reasons"]) > 0


class TestRecordImprovementOutcome:
    """Tests for record_improvement_outcome() method."""

    def test_record_improvement_basic(self, learning_db: LearningDatabase) -> None:
        """Test recording a basic improvement outcome."""
        result = learning_db.record_improvement_outcome(
            "IMP-MEM-001", "implemented", "Successfully deployed"
        )

        assert result is True
        imp = learning_db.get_improvement("IMP-MEM-001")
        assert imp is not None
        assert imp["current_outcome"] == "implemented"

    def test_record_improvement_with_category(self, learning_db: LearningDatabase) -> None:
        """Test recording improvement with category and priority."""
        learning_db.record_improvement_outcome(
            "IMP-TEL-001", "implemented", "Working", "telemetry", "high"
        )

        imp = learning_db.get_improvement("IMP-TEL-001")
        assert imp["category"] == "telemetry"
        assert imp["priority"] == "high"

    def test_record_improvement_history(self, learning_db: LearningDatabase) -> None:
        """Test that improvement outcomes are recorded in history."""
        learning_db.record_improvement_outcome("IMP-001", "in_progress", "Started")
        learning_db.record_improvement_outcome("IMP-001", "blocked", "Missing dep")
        learning_db.record_improvement_outcome("IMP-001", "implemented", "Fixed and done")

        imp = learning_db.get_improvement("IMP-001")
        assert len(imp["outcome_history"]) == 3
        assert imp["current_outcome"] == "implemented"

    def test_record_improvement_invalid_outcome(self, learning_db: LearningDatabase) -> None:
        """Test that invalid outcome returns False."""
        result = learning_db.record_improvement_outcome("IMP-001", "invalid_outcome", "Notes")

        assert result is False

    def test_record_improvement_empty_id(self, learning_db: LearningDatabase) -> None:
        """Test that empty imp_id returns False."""
        result = learning_db.record_improvement_outcome("", "implemented", "Notes")

        assert result is False

    def test_valid_outcomes_enum(self) -> None:
        """Test that VALID_OUTCOMES contains expected values."""
        expected = {"implemented", "blocked", "abandoned", "in_progress", "pending", "partial"}
        assert VALID_OUTCOMES == expected


class TestGetHistoricalPatterns:
    """Tests for get_historical_patterns() method."""

    def test_empty_patterns(self, learning_db: LearningDatabase) -> None:
        """Test patterns from empty database."""
        patterns = learning_db.get_historical_patterns()

        assert patterns["top_blocking_reasons"] == []
        assert patterns["category_success_rates"] == {}
        assert patterns["total_improvements_tracked"] == 0
        assert patterns["total_cycles_tracked"] == 0

    def test_patterns_with_data(self, populated_db: LearningDatabase) -> None:
        """Test patterns with populated data."""
        patterns = populated_db.get_historical_patterns()

        assert patterns["total_improvements_tracked"] == 4
        assert patterns["total_cycles_tracked"] == 2
        assert "memory" in patterns["category_success_rates"]
        assert "telemetry" in patterns["category_success_rates"]

    def test_blocking_reasons_sorted(self, populated_db: LearningDatabase) -> None:
        """Test that blocking reasons are sorted by count."""
        patterns = populated_db.get_historical_patterns()

        if len(patterns["top_blocking_reasons"]) > 1:
            counts = [r["count"] for r in patterns["top_blocking_reasons"]]
            assert counts == sorted(counts, reverse=True)

    def test_category_success_rates(self, populated_db: LearningDatabase) -> None:
        """Test that category success rates are calculated correctly."""
        patterns = populated_db.get_historical_patterns()

        # memory: 1 implemented, 1 blocked = 50% success
        memory_stats = patterns["category_success_rates"].get("memory", {})
        assert memory_stats.get("total") == 2
        assert memory_stats.get("implemented") == 1
        assert memory_stats.get("success_rate") == 0.5

    def test_recent_trends(self, populated_db: LearningDatabase) -> None:
        """Test that recent trends are calculated."""
        patterns = populated_db.get_historical_patterns()

        trends = patterns["recent_trends"]
        assert trends["sample_size"] == 2
        assert "avg_completion_rate" in trends


class TestGetSuccessRate:
    """Tests for get_success_rate() method."""

    def test_success_rate_existing_category(self, populated_db: LearningDatabase) -> None:
        """Test success rate for existing category."""
        rate = populated_db.get_success_rate("memory")

        # 1 implemented out of 2 = 0.5
        assert rate == 0.5

    def test_success_rate_nonexistent_category(self, learning_db: LearningDatabase) -> None:
        """Test success rate for non-existent category."""
        rate = learning_db.get_success_rate("nonexistent")

        assert rate == 0.0

    def test_success_rate_all_implemented(self, learning_db: LearningDatabase) -> None:
        """Test success rate when all improvements are implemented."""
        learning_db.record_improvement_outcome("IMP-1", "implemented", "", "test")
        learning_db.record_improvement_outcome("IMP-2", "implemented", "", "test")

        rate = learning_db.get_success_rate("test")
        assert rate == 1.0


class TestListMethods:
    """Tests for list_improvements() and list_cycles() methods."""

    def test_list_improvements_all(self, populated_db: LearningDatabase) -> None:
        """Test listing all improvements."""
        improvements = populated_db.list_improvements()

        assert len(improvements) == 4

    def test_list_improvements_by_category(self, populated_db: LearningDatabase) -> None:
        """Test filtering improvements by category."""
        improvements = populated_db.list_improvements(category="memory")

        assert len(improvements) == 2
        assert all(imp["category"] == "memory" for imp in improvements)

    def test_list_improvements_by_outcome(self, populated_db: LearningDatabase) -> None:
        """Test filtering improvements by outcome."""
        improvements = populated_db.list_improvements(outcome="implemented")

        assert len(improvements) == 2
        assert all(imp["current_outcome"] == "implemented" for imp in improvements)

    def test_list_improvements_combined_filters(self, populated_db: LearningDatabase) -> None:
        """Test filtering improvements by both category and outcome."""
        improvements = populated_db.list_improvements(category="memory", outcome="implemented")

        assert len(improvements) == 1
        assert improvements[0]["imp_id"] == "IMP-MEM-001"

    def test_list_cycles(self, populated_db: LearningDatabase) -> None:
        """Test listing all cycles."""
        cycles = populated_db.list_cycles()

        assert len(cycles) == 2

    def test_list_cycles_with_limit(self, populated_db: LearningDatabase) -> None:
        """Test limiting cycle list."""
        cycles = populated_db.list_cycles(limit=1)

        assert len(cycles) == 1

    def test_list_cycles_sorted_by_recency(self, populated_db: LearningDatabase) -> None:
        """Test that cycles are sorted by recency."""
        cycles = populated_db.list_cycles()

        if len(cycles) > 1:
            timestamps = [c.get("recorded_at", "") for c in cycles]
            assert timestamps == sorted(timestamps, reverse=True)


class TestGetLikelyBlockers:
    """Tests for get_likely_blockers() method."""

    def test_likely_blockers_empty(self, learning_db: LearningDatabase) -> None:
        """Test likely blockers from empty database."""
        blockers = learning_db.get_likely_blockers()

        assert blockers == []

    def test_likely_blockers_from_data(self, populated_db: LearningDatabase) -> None:
        """Test likely blockers with data."""
        blockers = populated_db.get_likely_blockers()

        # Should find blocking reasons from cycles
        assert isinstance(blockers, list)

    def test_likely_blockers_by_category(self, populated_db: LearningDatabase) -> None:
        """Test likely blockers filtered by category."""
        blockers = populated_db.get_likely_blockers(category="memory")

        # Should include reasons from blocked memory improvements
        assert isinstance(blockers, list)


class TestExportAndClear:
    """Tests for export_data() and clear_all() methods."""

    def test_export_data(self, populated_db: LearningDatabase) -> None:
        """Test exporting all data."""
        data = populated_db.export_data()

        assert "improvements" in data
        assert "cycles" in data
        assert "patterns" in data
        assert len(data["improvements"]) == 4

    def test_clear_all(self, populated_db: LearningDatabase, temp_db_path: Path) -> None:
        """Test clearing all data."""
        assert len(populated_db.list_improvements()) == 4

        result = populated_db.clear_all()

        assert result is True
        assert len(populated_db.list_improvements()) == 0
        assert len(populated_db.list_cycles()) == 0

        # Verify persistence
        db2 = LearningDatabase(temp_db_path)
        assert len(db2.list_improvements()) == 0


class TestSchemaMigration:
    """Tests for schema migration."""

    def test_migrate_old_schema(self, temp_db_path: Path) -> None:
        """Test migration from old schema version."""
        old_data = {
            "schema_version": 0,
            # Missing expected keys
        }
        temp_db_path.write_text(json.dumps(old_data))

        db = LearningDatabase(temp_db_path)

        assert db._data["schema_version"] == 1
        assert "improvements" in db._data
        assert "cycles" in db._data
        assert "patterns" in db._data

    def test_no_migration_needed(self, temp_db_path: Path) -> None:
        """Test that current schema doesn't trigger migration."""
        current_data = {
            "schema_version": 1,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "improvements": {"IMP-001": {"imp_id": "IMP-001"}},
            "cycles": {},
            "patterns": {
                "phase_correlations": {},
                "blocking_reasons": {},
                "category_success_rates": {},
            },
        }
        temp_db_path.write_text(json.dumps(current_data))

        db = LearningDatabase(temp_db_path)

        # Should preserve existing data
        assert "IMP-001" in db._data["improvements"]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_concurrent_writes(self, temp_db_path: Path) -> None:
        """Test multiple writes don't corrupt data."""
        db = LearningDatabase(temp_db_path)

        for i in range(10):
            db.record_improvement_outcome(f"IMP-{i:03d}", "implemented", f"Note {i}")

        assert len(db.list_improvements()) == 10

    def test_special_characters_in_notes(self, learning_db: LearningDatabase) -> None:
        """Test handling special characters in notes."""
        notes = 'Notes with "quotes", \\backslashes, and unicode: 日本語'

        result = learning_db.record_improvement_outcome("IMP-001", "implemented", notes)

        assert result is True
        imp = learning_db.get_improvement("IMP-001")
        assert imp["outcome_history"][0]["notes"] == notes

    def test_large_metrics_dict(self, learning_db: LearningDatabase) -> None:
        """Test handling large metrics dictionary."""
        large_metrics = {f"metric_{i}": i * 1.5 for i in range(100)}
        large_metrics["phases_completed"] = 5
        large_metrics["completion_rate"] = 0.9

        result = learning_db.record_cycle_outcome("cycle-large", large_metrics)

        assert result is True
        cycle = learning_db.get_cycle("cycle-large")
        assert cycle["metrics"]["phases_completed"] == 5

    def test_get_nonexistent_improvement(self, learning_db: LearningDatabase) -> None:
        """Test getting non-existent improvement returns None."""
        imp = learning_db.get_improvement("nonexistent")

        assert imp is None

    def test_get_nonexistent_cycle(self, learning_db: LearningDatabase) -> None:
        """Test getting non-existent cycle returns None."""
        cycle = learning_db.get_cycle("nonexistent")

        assert cycle is None

    def test_outcome_case_insensitive(self, learning_db: LearningDatabase) -> None:
        """Test that outcomes are normalized to lowercase."""
        learning_db.record_improvement_outcome("IMP-001", "IMPLEMENTED", "Notes")

        imp = learning_db.get_improvement("IMP-001")
        assert imp["current_outcome"] == "implemented"

    def test_parent_directory_created(self, tmp_path: Path) -> None:
        """Test that parent directories are created for db file."""
        nested_path = tmp_path / "a" / "b" / "c" / "learning.json"

        db = LearningDatabase(nested_path)
        db.record_improvement_outcome("IMP-001", "implemented", "Test")

        assert nested_path.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
