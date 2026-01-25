"""Tests for Adaptive Wave Sizing (IMP-GEN-002).

Tests the get_optimal_wave_size method which dynamically adjusts wave size
recommendations based on historical completion rates:
- < 70% completion: Reduce wave size by 2
- 70-90% completion: Maintain current size
- > 90% completion: Increase wave size by 2
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


class TestAdaptiveWaveSizingReturnFormat:
    """Tests for the return format of get_optimal_wave_size."""

    def test_returns_dict_with_required_keys(self, manager):
        """Test that return value is a dict with required keys."""
        result = manager.get_optimal_wave_size()

        assert isinstance(result, dict)
        assert "recommended_size" in result
        assert "rationale" in result

    def test_default_returns_size_3(self, manager):
        """Test that default recommendation is size 3 with no history."""
        result = manager.get_optimal_wave_size()

        assert result["recommended_size"] == 3
        assert "No history" in result["rationale"]

    def test_includes_completion_rate_when_history_exists(self, manager):
        """Test that completion_rate is included when history exists."""
        manager.record_wave_completion(wave_size=4, completed=3, failed=1)

        result = manager.get_optimal_wave_size()

        assert "completion_rate" in result
        assert isinstance(result["completion_rate"], float)


class TestLowCompletionRateReduction:
    """Tests for wave size reduction when completion rate < 70%."""

    def test_reduces_size_at_50_percent_completion(self, manager):
        """Test size reduction at 50% completion rate."""
        # 5 waves with 50% completion at size 6
        for _ in range(5):
            manager.record_wave_completion(wave_size=6, completed=3, failed=3)

        result = manager.get_optimal_wave_size()

        # Expected: 6 - 2 = 4
        assert result["recommended_size"] == 4
        assert result["completion_rate"] == 0.5
        assert "reducing" in result["rationale"].lower()

    def test_reduces_size_at_60_percent_completion(self, manager):
        """Test size reduction at 60% completion rate (still below 70%)."""
        # 5 waves with 60% completion at size 5
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=3, failed=2)

        result = manager.get_optimal_wave_size()

        # Expected: 5 - 2 = 3
        assert result["recommended_size"] == 3
        assert result["completion_rate"] == 0.6
        assert "reducing" in result["rationale"].lower()

    def test_minimum_size_is_1(self, manager):
        """Test that wave size never goes below 1."""
        # 5 waves with 20% completion at size 2
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=1, failed=4)

        result = manager.get_optimal_wave_size()

        # 5 - 2 = 3, but with poor completion should reduce
        # The result should never be less than 1
        assert result["recommended_size"] >= 1

    def test_reduces_size_at_69_percent_completion(self, manager):
        """Test size reduction at exactly 69% (boundary case)."""
        # Create a scenario with exactly 69% completion
        # 5 waves: 3 with 80% and 2 with 50% = (12+5)/(15+10) = 17/25 = 68%
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)  # 80%
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)  # 80%
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)  # 80%
        manager.record_wave_completion(wave_size=5, completed=2, failed=3)  # 40%
        manager.record_wave_completion(wave_size=5, completed=2, failed=3)  # 40%
        # Total: 16/25 = 64%

        result = manager.get_optimal_wave_size()

        assert result["completion_rate"] < 0.70
        assert "reducing" in result["rationale"].lower()


class TestGoodCompletionRateMaintenance:
    """Tests for wave size maintenance when completion rate is 70-90%."""

    def test_maintains_size_at_70_percent_completion(self, manager):
        """Test size maintenance at exactly 70% completion (boundary)."""
        # 5 waves with 70% completion at size 10
        for _ in range(5):
            manager.record_wave_completion(wave_size=10, completed=7, failed=3)

        result = manager.get_optimal_wave_size()

        # Should maintain average size of 10
        assert result["recommended_size"] == 10
        assert result["completion_rate"] == 0.70
        assert "maintaining" in result["rationale"].lower()

    def test_maintains_size_at_80_percent_completion(self, manager):
        """Test size maintenance at 80% completion rate."""
        # 5 waves with 80% completion at size 5
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=4, failed=1)

        result = manager.get_optimal_wave_size()

        # Should maintain average size of 5
        assert result["recommended_size"] == 5
        assert result["completion_rate"] == 0.8
        assert "maintaining" in result["rationale"].lower()

    def test_maintains_size_at_90_percent_completion(self, manager):
        """Test size maintenance at exactly 90% completion (boundary)."""
        # 5 waves with 90% completion at size 10
        for _ in range(5):
            manager.record_wave_completion(wave_size=10, completed=9, failed=1)

        result = manager.get_optimal_wave_size()

        # Should maintain average size of 10
        assert result["recommended_size"] == 10
        assert result["completion_rate"] == 0.90
        assert "maintaining" in result["rationale"].lower()


class TestHighCompletionRateIncrease:
    """Tests for wave size increase when completion rate > 90%."""

    def test_increases_size_at_91_percent_completion(self, manager):
        """Test size increase at 91% completion (just above threshold)."""
        # Create scenario with ~91% completion
        # 5 waves at size 10, all but 0.5 per wave succeed
        manager.record_wave_completion(wave_size=10, completed=9, failed=1)
        manager.record_wave_completion(wave_size=10, completed=9, failed=1)
        manager.record_wave_completion(wave_size=10, completed=9, failed=1)
        manager.record_wave_completion(wave_size=10, completed=10, failed=0)
        manager.record_wave_completion(wave_size=10, completed=9, failed=1)
        # Total: 46/50 = 92%

        result = manager.get_optimal_wave_size()

        # Expected: 10 + 2 = 12
        assert result["recommended_size"] == 12
        assert result["completion_rate"] > 0.90
        assert "increasing" in result["rationale"].lower()

    def test_increases_size_at_100_percent_completion(self, manager):
        """Test size increase at perfect 100% completion."""
        # 5 waves with 100% completion at size 4
        for _ in range(5):
            manager.record_wave_completion(wave_size=4, completed=4, failed=0)

        result = manager.get_optimal_wave_size()

        # Expected: 4 + 2 = 6
        assert result["recommended_size"] == 6
        assert result["completion_rate"] == 1.0
        assert "increasing" in result["rationale"].lower()

    def test_increases_size_at_95_percent_completion(self, manager):
        """Test size increase at 95% completion."""
        # 5 waves with 95% completion at size 20
        for _ in range(5):
            manager.record_wave_completion(wave_size=20, completed=19, failed=1)

        result = manager.get_optimal_wave_size()

        # Expected: 20 + 2 = 22
        assert result["recommended_size"] == 22
        assert result["completion_rate"] == 0.95
        assert "increasing" in result["rationale"].lower()


class TestLast5WavesCalculation:
    """Tests to verify that only the last 5 waves are considered."""

    def test_uses_only_last_5_waves(self, manager):
        """Test that calculation uses only the 5 most recent waves."""
        # Record 3 old waves with low completion (40%)
        for _ in range(3):
            manager.record_wave_completion(wave_size=10, completed=4, failed=6)

        # Record 5 new waves with high completion (100%)
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=5, failed=0)

        result = manager.get_optimal_wave_size()

        # Should only consider last 5 waves (100% completion)
        assert result["completion_rate"] == 1.0
        assert "increasing" in result["rationale"].lower()

    def test_uses_all_waves_when_less_than_5(self, manager):
        """Test that all waves are used when fewer than 5 exist."""
        # Record only 2 waves
        manager.record_wave_completion(wave_size=4, completed=4, failed=0)
        manager.record_wave_completion(wave_size=4, completed=4, failed=0)

        result = manager.get_optimal_wave_size()

        # Should use both waves (100% completion)
        assert result["completion_rate"] == 1.0
        # Average size is 4, should increase to 6
        assert result["recommended_size"] == 6


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_handles_zero_wave_size_gracefully(self, manager):
        """Test handling of zero wave size in history."""
        manager.record_wave_completion(wave_size=0, completed=0, failed=0)

        result = manager.get_optimal_wave_size()

        # Should fall back to default
        assert result["recommended_size"] == 3
        assert "No phase data" in result["rationale"]

    def test_handles_mixed_zero_and_valid_waves(self, manager):
        """Test handling of mix of zero and valid wave sizes."""
        manager.record_wave_completion(wave_size=0, completed=0, failed=0)
        manager.record_wave_completion(wave_size=4, completed=4, failed=0)
        manager.record_wave_completion(wave_size=4, completed=4, failed=0)

        result = manager.get_optimal_wave_size()

        # Total: 8, completed: 8, rate: 100%
        # Average size: (0+4+4)/3 = 2.67
        assert "completion_rate" in result
        assert result["completion_rate"] == 1.0

    def test_handles_all_failed_waves(self, manager):
        """Test handling when all improvements failed."""
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=0, failed=5)

        result = manager.get_optimal_wave_size()

        assert result["completion_rate"] == 0.0
        assert result["recommended_size"] >= 1  # Never below 1
        assert "reducing" in result["rationale"].lower()

    def test_rationale_includes_percentage(self, manager):
        """Test that rationale includes completion rate as percentage."""
        for _ in range(5):
            manager.record_wave_completion(wave_size=4, completed=3, failed=1)

        result = manager.get_optimal_wave_size()

        # Rationale should contain percentage like "75%"
        assert "%" in result["rationale"]


class TestIntegrationWithWaveHistory:
    """Integration tests for wave history and adaptive sizing."""

    def test_adaptive_sizing_after_multiple_cycles(self, manager):
        """Test adaptive sizing across multiple cycles of waves."""
        # Cycle 1: Low completion - should reduce
        for _ in range(5):
            manager.record_wave_completion(wave_size=5, completed=2, failed=3)

        result1 = manager.get_optimal_wave_size()
        assert result1["recommended_size"] < 5  # Reduced

        # Cycle 2: After reducing size, better completion
        for _ in range(5):
            manager.record_wave_completion(
                wave_size=result1["recommended_size"],
                completed=result1["recommended_size"],
                failed=0,
            )

        result2 = manager.get_optimal_wave_size()
        # With 100% completion, should now increase
        assert result2["completion_rate"] == 1.0
        assert "increasing" in result2["rationale"].lower()

    def test_persistence_of_adaptive_recommendation(self, manager, temp_memory_file):
        """Test that recommendations persist across manager instances."""
        # Record history and save
        for _ in range(5):
            manager.record_wave_completion(wave_size=4, completed=4, failed=0)
        manager.save()

        # Create new manager instance
        new_manager = LearningMemoryManager(temp_memory_file)
        result = new_manager.get_optimal_wave_size()

        # Should still recommend increase
        assert result["recommended_size"] == 6
        assert result["completion_rate"] == 1.0
