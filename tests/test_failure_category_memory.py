"""Tests for failure category memory functionality (IMP-MEM-003)."""

import json
import uuid

import pytest

from autopack.learning_memory_manager import LearningMemoryManager


@pytest.fixture
def temp_memory_file(tmp_path):
    """Create a temporary memory file path with unique name per test."""
    unique_id = uuid.uuid4().hex[:8]
    return tmp_path / f"LEARNING_MEMORY_{unique_id}.json"


@pytest.fixture
def manager(temp_memory_file):
    """Create a fresh LearningMemoryManager instance."""
    return LearningMemoryManager(temp_memory_file)


class TestFailureCategoriesStructure:
    """Tests for failure_categories in memory structure."""

    def test_default_structure_includes_failure_categories(self, manager):
        """Test that new memory includes failure_categories section."""
        manager.save()
        content = manager.memory_path.read_text()
        data = json.loads(content)

        assert "failure_categories" in data
        assert "code_failure" in data["failure_categories"]
        assert "unrelated_ci" in data["failure_categories"]
        assert "flaky_test" in data["failure_categories"]

    def test_failure_category_structure(self, manager):
        """Test that each failure category has correct structure."""
        manager.save()
        content = manager.memory_path.read_text()
        data = json.loads(content)

        for category in ["code_failure", "unrelated_ci", "flaky_test"]:
            cat_data = data["failure_categories"][category]
            assert "count" in cat_data
            assert "phases" in cat_data
            assert "last_seen" in cat_data
            assert cat_data["count"] == 0
            assert cat_data["phases"] == []

    def test_loads_existing_memory_with_failure_categories(self, temp_memory_file):
        """Test that existing memory with failure_categories loads correctly."""
        existing_data = {
            "version": "1.0.0",
            "improvement_outcomes": [],
            "success_patterns": [],
            "failure_patterns": [],
            "failure_categories": {
                "code_failure": {
                    "count": 5,
                    "phases": ["IMP-TEST-001"],
                    "last_seen": "2024-01-01T00:00:00Z",
                },
                "unrelated_ci": {"count": 2, "phases": [], "last_seen": None},
                "flaky_test": {
                    "count": 1,
                    "phases": ["IMP-TEST-002"],
                    "last_seen": "2024-01-02T00:00:00Z",
                },
            },
            "wave_history": [],
            "last_updated": "2024-01-01T00:00:00Z",
        }
        temp_memory_file.write_text(json.dumps(existing_data))

        manager = LearningMemoryManager(temp_memory_file)
        patterns = manager.get_failure_category_patterns()

        assert patterns["categories"]["code_failure"]["count"] == 5
        assert patterns["categories"]["flaky_test"]["count"] == 1


class TestRecordFailureCategory:
    """Tests for record_failure_category functionality."""

    def test_records_code_failure(self, manager):
        """Test recording a code_failure category."""
        manager.record_failure_category(
            category="code_failure",
            phase_id="IMP-MEM-003",
            details={"pr_number": 123, "failed_jobs": "lint, test"},
        )

        patterns = manager.get_failure_category_patterns()
        assert patterns["categories"]["code_failure"]["count"] == 1
        assert "IMP-MEM-003" in patterns["categories"]["code_failure"]["phases"]

    def test_records_unrelated_ci_failure(self, manager):
        """Test recording an unrelated_ci category."""
        manager.record_failure_category(
            category="unrelated_ci",
            phase_id="IMP-TEL-001",
            details={"error_summary": "Network timeout during artifact download"},
        )

        patterns = manager.get_failure_category_patterns()
        assert patterns["categories"]["unrelated_ci"]["count"] == 1
        assert "IMP-TEL-001" in patterns["categories"]["unrelated_ci"]["phases"]

    def test_records_flaky_test_failure(self, manager):
        """Test recording a flaky_test category."""
        manager.record_failure_category(
            category="flaky_test",
            phase_id="IMP-GEN-002",
            details={"failed_jobs": "integration-tests", "error_summary": "Intermittent timeout"},
        )

        patterns = manager.get_failure_category_patterns()
        assert patterns["categories"]["flaky_test"]["count"] == 1
        assert "IMP-GEN-002" in patterns["categories"]["flaky_test"]["phases"]

    def test_increments_count_on_multiple_failures(self, manager):
        """Test that count increments with multiple failures of same category."""
        manager.record_failure_category("code_failure", "IMP-001")
        manager.record_failure_category("code_failure", "IMP-002")
        manager.record_failure_category("code_failure", "IMP-003")

        patterns = manager.get_failure_category_patterns()
        assert patterns["categories"]["code_failure"]["count"] == 3

    def test_tracks_unique_phases(self, manager):
        """Test that phases are tracked uniquely (no duplicates)."""
        manager.record_failure_category("code_failure", "IMP-001")
        manager.record_failure_category("code_failure", "IMP-001")  # Same phase
        manager.record_failure_category("code_failure", "IMP-002")

        patterns = manager.get_failure_category_patterns()
        phases = patterns["categories"]["code_failure"]["phases"]
        assert len(phases) == 2
        assert "IMP-001" in phases
        assert "IMP-002" in phases

    def test_updates_last_seen_timestamp(self, manager):
        """Test that last_seen is updated on each failure."""
        manager.record_failure_category("code_failure", "IMP-001")

        patterns = manager.get_failure_category_patterns()
        assert patterns["categories"]["code_failure"]["last_seen"] is not None
        assert "T" in patterns["categories"]["code_failure"]["last_seen"]  # ISO format

    def test_handles_unknown_category(self, manager):
        """Test handling of unknown/custom category."""
        manager.record_failure_category("custom_failure", "IMP-001")

        patterns = manager.get_failure_category_patterns()
        assert "custom_failure" in patterns["categories"]
        assert patterns["categories"]["custom_failure"]["count"] == 1

    def test_adds_to_failure_patterns_list(self, manager):
        """Test that failures are also added to failure_patterns for detailed tracking."""
        manager.record_failure_category(
            category="code_failure", phase_id="IMP-001", details={"pr_number": 100}
        )

        patterns = manager.get_failure_patterns()
        assert len(patterns) >= 1
        recent = [p for p in patterns if p.get("category") == "code_failure"]
        assert len(recent) == 1
        assert recent[0]["phase_id"] == "IMP-001"

    def test_handles_none_details(self, manager):
        """Test that None details are handled gracefully."""
        manager.record_failure_category("code_failure", "IMP-001", details=None)

        patterns = manager.get_failure_patterns()
        recent = [p for p in patterns if p.get("phase_id") == "IMP-001"]
        assert recent[0]["details"] == {}


class TestGetFailureCategoryPatterns:
    """Tests for get_failure_category_patterns functionality."""

    def test_returns_empty_patterns_when_no_failures(self, manager):
        """Test that empty patterns are returned with no failures."""
        patterns = manager.get_failure_category_patterns()

        assert patterns["total_failures"] == 0
        assert patterns["most_common"] is None
        assert patterns["phase_failure_map"] == {}

    def test_calculates_total_failures(self, manager):
        """Test that total_failures is calculated correctly."""
        manager.record_failure_category("code_failure", "IMP-001")
        manager.record_failure_category("unrelated_ci", "IMP-002")
        manager.record_failure_category("flaky_test", "IMP-003")

        patterns = manager.get_failure_category_patterns()
        assert patterns["total_failures"] == 3

    def test_identifies_most_common_category(self, manager):
        """Test that most_common category is identified."""
        manager.record_failure_category("code_failure", "IMP-001")
        manager.record_failure_category("code_failure", "IMP-002")
        manager.record_failure_category("unrelated_ci", "IMP-003")

        patterns = manager.get_failure_category_patterns()
        assert patterns["most_common"] == "code_failure"

    def test_builds_phase_failure_map(self, manager):
        """Test that phase_failure_map tracks which phases have which failures."""
        manager.record_failure_category("code_failure", "IMP-001")
        manager.record_failure_category("flaky_test", "IMP-001")  # Same phase, different category
        manager.record_failure_category("code_failure", "IMP-002")

        patterns = manager.get_failure_category_patterns()
        phase_map = patterns["phase_failure_map"]

        assert "IMP-001" in phase_map
        assert "code_failure" in phase_map["IMP-001"]
        assert "flaky_test" in phase_map["IMP-001"]
        assert "IMP-002" in phase_map
        assert "code_failure" in phase_map["IMP-002"]

    def test_returns_all_categories_in_structure(self, manager):
        """Test that all categories are included in the response."""
        patterns = manager.get_failure_category_patterns()

        assert "code_failure" in patterns["categories"]
        assert "unrelated_ci" in patterns["categories"]
        assert "flaky_test" in patterns["categories"]


class TestPersistence:
    """Tests for failure category persistence."""

    def test_failure_categories_persist_after_save(self, temp_memory_file):
        """Test that failure categories are persisted after save."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_failure_category(
            category="code_failure", phase_id="IMP-MEM-003", details={"pr_number": 456}
        )
        manager1.save()

        manager2 = LearningMemoryManager(temp_memory_file)
        patterns = manager2.get_failure_category_patterns()

        assert patterns["categories"]["code_failure"]["count"] == 1
        assert "IMP-MEM-003" in patterns["categories"]["code_failure"]["phases"]

    def test_multiple_categories_persist(self, temp_memory_file):
        """Test that multiple categories persist correctly."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_failure_category("code_failure", "IMP-001")
        manager1.record_failure_category("unrelated_ci", "IMP-002")
        manager1.record_failure_category("flaky_test", "IMP-003")
        manager1.save()

        manager2 = LearningMemoryManager(temp_memory_file)
        patterns = manager2.get_failure_category_patterns()

        assert patterns["total_failures"] == 3
        assert patterns["categories"]["code_failure"]["count"] == 1
        assert patterns["categories"]["unrelated_ci"]["count"] == 1
        assert patterns["categories"]["flaky_test"]["count"] == 1


class TestForwardCompatibility:
    """Tests for forward compatibility with older memory formats."""

    def test_adds_failure_categories_to_old_format(self, temp_memory_file):
        """Test that failure_categories is added when loading old format."""
        old_data = {
            "version": "1.0.0",
            "improvement_outcomes": [],
            "success_patterns": [],
            "failure_patterns": [],
            "wave_history": [],
            "last_updated": None,
        }
        temp_memory_file.write_text(json.dumps(old_data))

        manager = LearningMemoryManager(temp_memory_file)
        patterns = manager.get_failure_category_patterns()

        # Should have failure_categories now
        assert "code_failure" in patterns["categories"]
        assert "unrelated_ci" in patterns["categories"]
        assert "flaky_test" in patterns["categories"]

    def test_can_record_after_upgrading_format(self, temp_memory_file):
        """Test that recording works after upgrading from old format."""
        old_data = {
            "version": "1.0.0",
            "improvement_outcomes": [],
            "success_patterns": [],
            "failure_patterns": [],
            "wave_history": [],
            "last_updated": None,
        }
        temp_memory_file.write_text(json.dumps(old_data))

        manager = LearningMemoryManager(temp_memory_file)
        manager.record_failure_category("code_failure", "IMP-NEW-001")
        manager.save()

        manager2 = LearningMemoryManager(temp_memory_file)
        patterns = manager2.get_failure_category_patterns()
        assert patterns["categories"]["code_failure"]["count"] == 1
