"""Tests for Improvement Effectiveness Tracking (IMP-TEL-002).

Tests the get_effectiveness_stats() method and effectiveness metrics
recorded via record_improvement_outcome() with PR details.
"""

import pytest

from autopack.learning_memory_manager import LearningMemoryManager


@pytest.fixture
def temp_memory_file(tmp_path):
    """Create a temporary memory file path."""
    return tmp_path / "LEARNING_MEMORY.json"


@pytest.fixture
def manager(temp_memory_file):
    """Create a fresh LearningMemoryManager instance."""
    return LearningMemoryManager(temp_memory_file)


class TestGetEffectivenessStats:
    """Tests for get_effectiveness_stats functionality."""

    def test_returns_empty_stats_when_no_outcomes(self, manager):
        """Test that empty stats are returned with no outcomes."""
        stats = manager.get_effectiveness_stats()

        assert stats["total_outcomes"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["success_rate"] == 0.0
        assert stats["avg_merge_time_hours"] is None
        assert stats["avg_ci_pass_rate"] is None
        assert stats["avg_review_cycles"] is None
        assert stats["by_category"] == {}

    def test_calculates_basic_stats(self, manager):
        """Test basic success/failure counting."""
        manager.record_improvement_outcome("IMP-TEL-001", success=True)
        manager.record_improvement_outcome("IMP-TEL-002", success=True)
        manager.record_improvement_outcome("IMP-TEL-003", success=False)

        stats = manager.get_effectiveness_stats()

        assert stats["total_outcomes"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["success_rate"] == pytest.approx(2 / 3, rel=0.01)

    def test_calculates_merge_time_average(self, manager):
        """Test average merge time calculation from details."""
        manager.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={"merge_time_hours": 2.5},
        )
        manager.record_improvement_outcome(
            "IMP-TEL-002",
            success=True,
            details={"merge_time_hours": 5.5},
        )

        stats = manager.get_effectiveness_stats()

        assert stats["avg_merge_time_hours"] == 4.0

    def test_calculates_ci_pass_rate_average(self, manager):
        """Test average CI pass rate calculation."""
        manager.record_improvement_outcome(
            "IMP-MEM-001",
            success=True,
            details={"ci_pass_rate": 1.0},
        )
        manager.record_improvement_outcome(
            "IMP-MEM-002",
            success=True,
            details={"ci_pass_rate": 0.8},
        )

        stats = manager.get_effectiveness_stats()

        assert stats["avg_ci_pass_rate"] == pytest.approx(0.9, rel=0.01)

    def test_calculates_review_cycles_average(self, manager):
        """Test average review cycles calculation."""
        manager.record_improvement_outcome(
            "IMP-GEN-001",
            success=True,
            details={"review_cycles": 2},
        )
        manager.record_improvement_outcome(
            "IMP-GEN-002",
            success=True,
            details={"review_cycles": 4},
        )

        stats = manager.get_effectiveness_stats()

        assert stats["avg_review_cycles"] == 3.0

    def test_filters_by_category(self, manager):
        """Test filtering stats by improvement category."""
        manager.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={"merge_time_hours": 3.0},
        )
        manager.record_improvement_outcome(
            "IMP-TEL-002",
            success=True,
            details={"merge_time_hours": 5.0},
        )
        manager.record_improvement_outcome(
            "IMP-MEM-001",
            success=False,
            details={"merge_time_hours": 10.0},
        )

        # Get stats for TEL only
        tel_stats = manager.get_effectiveness_stats("IMP-TEL")

        assert tel_stats["total_outcomes"] == 2
        assert tel_stats["successful"] == 2
        assert tel_stats["failed"] == 0
        assert tel_stats["avg_merge_time_hours"] == 4.0

    def test_returns_empty_for_unknown_category(self, manager):
        """Test that empty stats are returned for unknown category."""
        manager.record_improvement_outcome("IMP-TEL-001", success=True)

        stats = manager.get_effectiveness_stats("IMP-UNKNOWN")

        assert stats["total_outcomes"] == 0
        assert stats["by_category"] == {}

    def test_by_category_breakdown(self, manager):
        """Test per-category breakdown in stats."""
        manager.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={"merge_time_hours": 2.0, "ci_pass_rate": 1.0},
        )
        manager.record_improvement_outcome(
            "IMP-MEM-001",
            success=True,
            details={"merge_time_hours": 4.0, "ci_pass_rate": 0.9},
        )
        manager.record_improvement_outcome(
            "IMP-MEM-002",
            success=False,
            details={"merge_time_hours": 8.0, "ci_pass_rate": 0.5},
        )

        stats = manager.get_effectiveness_stats()

        assert "IMP-TEL" in stats["by_category"]
        assert "IMP-MEM" in stats["by_category"]

        tel_stats = stats["by_category"]["IMP-TEL"]
        assert tel_stats["total"] == 1
        assert tel_stats["successful"] == 1
        assert tel_stats["success_rate"] == 1.0
        assert tel_stats["avg_merge_time_hours"] == 2.0
        assert tel_stats["avg_ci_pass_rate"] == 1.0

        mem_stats = stats["by_category"]["IMP-MEM"]
        assert mem_stats["total"] == 2
        assert mem_stats["successful"] == 1
        assert mem_stats["success_rate"] == 0.5
        assert mem_stats["avg_merge_time_hours"] == 6.0
        assert mem_stats["avg_ci_pass_rate"] == pytest.approx(0.7, rel=0.01)


class TestEffectivenessWithPrDetails:
    """Tests for recording outcomes with full PR details."""

    def test_records_pr_details(self, manager):
        """Test recording improvement outcome with PR details."""
        details = {
            "pr_number": 123,
            "merge_time_hours": 4.5,
            "ci_pass_rate": 0.95,
            "ci_checks_passed": 19,
            "ci_checks_total": 20,
            "review_cycles": 2,
            "created_at": "2024-01-15T10:00:00Z",
            "merged_at": "2024-01-15T14:30:00Z",
            "branch": "feature/my-improvement",
        }

        manager.record_improvement_outcome("IMP-TEL-002", success=True, details=details)

        history = manager.get_improvement_history("IMP-TEL-002")
        assert len(history) == 1
        assert history[0]["details"]["pr_number"] == 123
        assert history[0]["details"]["merge_time_hours"] == 4.5
        assert history[0]["details"]["ci_pass_rate"] == 0.95
        assert history[0]["details"]["review_cycles"] == 2

    def test_effectiveness_stats_with_full_details(self, manager):
        """Test effectiveness stats calculation with full PR details."""
        details1 = {
            "pr_number": 100,
            "merge_time_hours": 2.0,
            "ci_pass_rate": 1.0,
            "review_cycles": 1,
        }
        details2 = {
            "pr_number": 101,
            "merge_time_hours": 6.0,
            "ci_pass_rate": 0.9,
            "review_cycles": 3,
        }
        details3 = {
            "pr_number": 102,
            "merge_time_hours": 4.0,
            "ci_pass_rate": 0.8,
            "review_cycles": 2,
        }

        manager.record_improvement_outcome("IMP-TEL-001", success=True, details=details1)
        manager.record_improvement_outcome("IMP-TEL-002", success=True, details=details2)
        manager.record_improvement_outcome("IMP-TEL-003", success=True, details=details3)

        stats = manager.get_effectiveness_stats()

        assert stats["total_outcomes"] == 3
        assert stats["successful"] == 3
        assert stats["avg_merge_time_hours"] == 4.0  # (2+6+4)/3
        assert stats["avg_ci_pass_rate"] == 0.9  # (1+0.9+0.8)/3
        assert stats["avg_review_cycles"] == 2.0  # (1+3+2)/3


class TestEffectivenessPersistence:
    """Tests for persistence of effectiveness data."""

    def test_saves_and_reloads_effectiveness_data(self, temp_memory_file):
        """Test that effectiveness data persists across sessions."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={
                "merge_time_hours": 3.5,
                "ci_pass_rate": 0.95,
                "review_cycles": 2,
            },
        )
        manager1.save()

        # Reload in new instance
        manager2 = LearningMemoryManager(temp_memory_file)

        stats = manager2.get_effectiveness_stats()
        assert stats["total_outcomes"] == 1
        assert stats["avg_merge_time_hours"] == 3.5
        assert stats["avg_ci_pass_rate"] == 0.95
        assert stats["avg_review_cycles"] == 2.0


class TestEdgeCasesEffectiveness:
    """Edge cases for effectiveness tracking."""

    def test_handles_partial_details(self, manager):
        """Test handling outcomes with only some details."""
        manager.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={"merge_time_hours": 2.0},  # Missing ci_pass_rate and review_cycles
        )
        manager.record_improvement_outcome(
            "IMP-TEL-002",
            success=True,
            details={"ci_pass_rate": 0.9},  # Missing merge_time_hours and review_cycles
        )

        stats = manager.get_effectiveness_stats()

        assert stats["avg_merge_time_hours"] == 2.0  # Only one value
        assert stats["avg_ci_pass_rate"] == 0.9  # Only one value
        assert stats["avg_review_cycles"] is None  # No values

    def test_handles_empty_details(self, manager):
        """Test handling outcomes with empty details."""
        manager.record_improvement_outcome("IMP-TEL-001", success=True, details={})
        manager.record_improvement_outcome("IMP-TEL-002", success=True, details=None)

        stats = manager.get_effectiveness_stats()

        assert stats["total_outcomes"] == 2
        assert stats["avg_merge_time_hours"] is None
        assert stats["avg_ci_pass_rate"] is None
        assert stats["avg_review_cycles"] is None

    def test_handles_mixed_success_failure_with_metrics(self, manager):
        """Test stats include metrics from both successful and failed outcomes."""
        manager.record_improvement_outcome(
            "IMP-TEL-001",
            success=True,
            details={"merge_time_hours": 2.0, "ci_pass_rate": 1.0},
        )
        manager.record_improvement_outcome(
            "IMP-TEL-002",
            success=False,
            details={"merge_time_hours": 10.0, "ci_pass_rate": 0.5},
        )

        stats = manager.get_effectiveness_stats()

        assert stats["successful"] == 1
        assert stats["failed"] == 1
        # Metrics include both success and failure outcomes
        assert stats["avg_merge_time_hours"] == 6.0  # (2+10)/2
        assert stats["avg_ci_pass_rate"] == 0.75  # (1+0.5)/2
