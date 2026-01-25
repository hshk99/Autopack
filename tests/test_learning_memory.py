"""Tests for LearningMemoryManager (IMP-MEM-001)."""

import json

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


class TestLoadOrCreate:
    """Tests for _load_or_create functionality."""

    def test_creates_new_memory_when_file_missing(self, temp_memory_file):
        """Test that new memory is created when file doesn't exist."""
        manager = LearningMemoryManager(temp_memory_file)

        assert manager.version == "1.0.0"
        assert manager.outcome_count == 0
        assert manager.wave_count == 0

    def test_loads_existing_memory(self, temp_memory_file):
        """Test that existing memory is loaded correctly."""
        # Create existing memory file
        existing_data = {
            "version": "1.0.0",
            "improvement_outcomes": [
                {
                    "imp_id": "IMP-TEST-001",
                    "success": True,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "details": {},
                }
            ],
            "success_patterns": [],
            "failure_patterns": [],
            "wave_history": [],
            "last_updated": "2024-01-01T00:00:00Z",
        }
        temp_memory_file.write_text(json.dumps(existing_data))

        manager = LearningMemoryManager(temp_memory_file)

        assert manager.outcome_count == 1
        assert manager.version == "1.0.0"

    def test_handles_corrupted_json(self, temp_memory_file):
        """Test that corrupted JSON creates fresh memory."""
        temp_memory_file.write_text("{ invalid json }")

        manager = LearningMemoryManager(temp_memory_file)

        assert manager.version == "1.0.0"
        assert manager.outcome_count == 0

    def test_adds_missing_keys_for_forward_compatibility(self, temp_memory_file):
        """Test that missing keys are added when loading old format."""
        old_data = {
            "version": "1.0.0",
            "improvement_outcomes": [],
            # Missing: success_patterns, failure_patterns, wave_history, last_updated
        }
        temp_memory_file.write_text(json.dumps(old_data))

        manager = LearningMemoryManager(temp_memory_file)

        # Should have all keys now
        assert manager.get_success_patterns() == []
        assert manager.get_failure_patterns() == []
        assert manager.wave_count == 0


class TestRecordImprovementOutcome:
    """Tests for record_improvement_outcome functionality."""

    def test_records_successful_outcome(self, manager):
        """Test recording a successful improvement outcome."""
        manager.record_improvement_outcome("IMP-MEM-001", success=True, details={"type": "memory"})

        assert manager.outcome_count == 1
        history = manager.get_improvement_history("IMP-MEM-001")
        assert len(history) == 1
        assert history[0]["success"] is True
        assert history[0]["details"]["type"] == "memory"

    def test_records_failed_outcome(self, manager):
        """Test recording a failed improvement outcome."""
        manager.record_improvement_outcome(
            "IMP-TEST-001", success=False, details={"error_type": "lint_failure"}
        )

        assert manager.outcome_count == 1
        history = manager.get_improvement_history("IMP-TEST-001")
        assert len(history) == 1
        assert history[0]["success"] is False

    def test_records_multiple_outcomes(self, manager):
        """Test recording multiple outcomes for same and different improvements."""
        manager.record_improvement_outcome("IMP-MEM-001", success=True)
        manager.record_improvement_outcome("IMP-MEM-001", success=False)
        manager.record_improvement_outcome("IMP-TEL-001", success=True)

        assert manager.outcome_count == 3
        assert len(manager.get_improvement_history("IMP-MEM-001")) == 2
        assert len(manager.get_improvement_history("IMP-TEL-001")) == 1

    def test_outcome_includes_timestamp(self, manager):
        """Test that outcomes include ISO timestamp."""
        manager.record_improvement_outcome("IMP-TEST-001", success=True)

        history = manager.get_improvement_history("IMP-TEST-001")
        assert "timestamp" in history[0]
        assert "T" in history[0]["timestamp"]  # ISO format contains T


class TestSuccessPatterns:
    """Tests for get_success_patterns functionality."""

    def test_returns_empty_when_no_outcomes(self, manager):
        """Test that empty list is returned with no outcomes."""
        patterns = manager.get_success_patterns()
        assert patterns == []

    def test_identifies_success_patterns_by_type(self, manager):
        """Test that success patterns are grouped by improvement type."""
        # Record multiple successes for IMP-MEM
        manager.record_improvement_outcome("IMP-MEM-001", success=True)
        manager.record_improvement_outcome("IMP-MEM-002", success=True)
        manager.record_improvement_outcome("IMP-TEL-001", success=True)

        patterns = manager.get_success_patterns()

        # Should have patterns for both types
        assert len(patterns) >= 2
        type_counts = {p["type"]: p["count"] for p in patterns}
        assert type_counts.get("IMP-MEM") == 2
        assert type_counts.get("IMP-TEL") == 1


class TestFailurePatterns:
    """Tests for get_failure_patterns functionality."""

    def test_returns_empty_when_no_failures(self, manager):
        """Test that empty list is returned with no failures."""
        manager.record_improvement_outcome("IMP-TEST-001", success=True)

        patterns = manager.get_failure_patterns()
        # May include empty patterns, check for failure-specific entries
        failure_types = [p for p in patterns if p.get("pattern") == "recurring_failure"]
        assert len(failure_types) == 0

    def test_identifies_failure_patterns_by_type(self, manager):
        """Test that failure patterns are grouped by improvement type."""
        manager.record_improvement_outcome("IMP-MEM-001", success=False)
        manager.record_improvement_outcome("IMP-MEM-002", success=False)
        manager.record_improvement_outcome("IMP-TEL-001", success=False)

        patterns = manager.get_failure_patterns()

        type_patterns = [p for p in patterns if p.get("pattern") == "recurring_failure"]
        assert len(type_patterns) >= 2

    def test_identifies_common_error_patterns(self, manager):
        """Test that repeated error types are identified as patterns."""
        for i in range(3):
            manager.record_improvement_outcome(
                f"IMP-TEST-{i:03d}", success=False, details={"error_type": "lint_failure"}
            )

        patterns = manager.get_failure_patterns()

        error_patterns = [p for p in patterns if p.get("type") == "error_pattern"]
        # Should find lint_failure as a pattern (count >= 2)
        assert any(p.get("pattern") == "lint_failure" for p in error_patterns)


class TestWaveHistory:
    """Tests for wave history and optimal sizing."""

    def test_records_wave_completion(self, manager):
        """Test recording wave completion statistics."""
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)

        assert manager.wave_count == 1

    def test_calculates_completion_rate(self, manager):
        """Test that completion rate is calculated correctly."""
        manager.record_wave_completion(wave_size=10, completed=8, failed=2)
        manager.save()

        # Reload and check
        manager2 = LearningMemoryManager(manager.memory_path)
        waves = manager2._memory["wave_history"]
        assert waves[0]["completion_rate"] == 0.8

    def test_optimal_wave_size_default_with_no_history(self, manager):
        """Test that default wave size is 3 with no history."""
        optimal = manager.get_optimal_wave_size()
        assert optimal == 3

    def test_optimal_wave_size_prefers_high_throughput(self, manager):
        """Test that optimal size maximizes throughput above threshold."""
        # Size 3 with 100% completion = throughput 3.0
        manager.record_wave_completion(wave_size=3, completed=3, failed=0)
        manager.record_wave_completion(wave_size=3, completed=3, failed=0)

        # Size 5 with 80% completion = throughput 4.0 (higher)
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)

        optimal = manager.get_optimal_wave_size()
        # Should prefer size 5 due to higher throughput
        assert optimal == 5

    def test_optimal_wave_size_avoids_low_completion_rate(self, manager):
        """Test that sizes with low completion rates are avoided."""
        # Size 3 with 100% completion
        manager.record_wave_completion(wave_size=3, completed=3, failed=0)

        # Size 10 with 50% completion (below 70% threshold)
        manager.record_wave_completion(wave_size=10, completed=5, failed=5)

        optimal = manager.get_optimal_wave_size()
        # Should prefer size 3 (meets threshold) over size 10 (doesn't meet threshold)
        assert optimal == 3


class TestTypeSuccessRate:
    """Tests for get_type_success_rate functionality."""

    def test_returns_none_when_no_history(self, manager):
        """Test that None is returned when no history for type."""
        rate = manager.get_type_success_rate("IMP-MEM")
        assert rate is None

    def test_calculates_correct_rate(self, manager):
        """Test that success rate is calculated correctly."""
        manager.record_improvement_outcome("IMP-MEM-001", success=True)
        manager.record_improvement_outcome("IMP-MEM-002", success=True)
        manager.record_improvement_outcome("IMP-MEM-003", success=False)

        rate = manager.get_type_success_rate("IMP-MEM")
        assert rate == pytest.approx(2 / 3)

    def test_isolates_by_type_prefix(self, manager):
        """Test that rate is calculated only for matching prefix."""
        manager.record_improvement_outcome("IMP-MEM-001", success=True)
        manager.record_improvement_outcome("IMP-TEL-001", success=False)

        mem_rate = manager.get_type_success_rate("IMP-MEM")
        tel_rate = manager.get_type_success_rate("IMP-TEL")

        assert mem_rate == 1.0
        assert tel_rate == 0.0


class TestPersistence:
    """Tests for save and persistence functionality."""

    def test_save_creates_file(self, manager, temp_memory_file):
        """Test that save creates the memory file."""
        manager.record_improvement_outcome("IMP-TEST-001", success=True)
        manager.save()

        assert temp_memory_file.exists()

    def test_save_preserves_data(self, temp_memory_file):
        """Test that saved data can be reloaded."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_improvement_outcome("IMP-TEST-001", success=True, details={"key": "value"})
        manager1.record_wave_completion(wave_size=5, completed=4, failed=1)
        manager1.save()

        manager2 = LearningMemoryManager(temp_memory_file)

        assert manager2.outcome_count == 1
        assert manager2.wave_count == 1
        history = manager2.get_improvement_history("IMP-TEST-001")
        assert history[0]["details"]["key"] == "value"

    def test_save_updates_last_updated(self, manager):
        """Test that save updates last_updated timestamp."""
        manager.save()

        assert manager._memory["last_updated"] is not None
        assert "T" in manager._memory["last_updated"]

    def test_clear_resets_memory(self, manager):
        """Test that clear resets all memory."""
        manager.record_improvement_outcome("IMP-TEST-001", success=True)
        manager.record_wave_completion(wave_size=5, completed=4, failed=1)

        manager.clear()

        assert manager.outcome_count == 0
        assert manager.wave_count == 0
        assert manager.get_success_patterns() == []


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_empty_imp_id(self, manager):
        """Test handling of empty improvement ID."""
        manager.record_improvement_outcome("", success=True)
        assert manager.outcome_count == 1

    def test_handles_zero_wave_size(self, manager):
        """Test handling of zero wave size (avoids division by zero)."""
        manager.record_wave_completion(wave_size=0, completed=0, failed=0)
        assert manager.wave_count == 1
        # Should not raise on optimal calculation
        manager.get_optimal_wave_size()

    def test_handles_none_details(self, manager):
        """Test that None details are handled."""
        manager.record_improvement_outcome("IMP-TEST-001", success=True, details=None)
        history = manager.get_improvement_history("IMP-TEST-001")
        assert history[0]["details"] == {}

    def test_creates_parent_directories_on_save(self, tmp_path):
        """Test that parent directories are created when saving."""
        nested_path = tmp_path / "nested" / "dir" / "LEARNING_MEMORY.json"
        manager = LearningMemoryManager(nested_path)
        manager.save()

        assert nested_path.exists()
