"""Tests for ImprovementGenerator."""

import json
from pathlib import Path

import pytest

from src.improvement_generator import ImprovementGenerator


@pytest.fixture
def temp_master_file(tmp_path):
    """Create a temporary path for the master file."""
    return tmp_path / "AUTOPACK_IMPS_MASTER.json"


@pytest.fixture
def sample_flaky_test_pattern():
    """Sample flaky test pattern from TelemetryAnalyzer."""
    return {
        "pattern_type": "flaky_test",
        "test_id": "test_auth_flow",
        "retry_count": 5,
        "success_rate": 0.4,
        "severity": "high",
        "description": "Test 'test_auth_flow' is flaky - 5 retries with mixed outcomes",
        "source": "ci_retry_state",
    }


@pytest.fixture
def sample_consistent_failure_pattern():
    """Sample consistent CI failure pattern."""
    return {
        "pattern_type": "consistent_ci_failure",
        "test_id": "test_db_connection",
        "failure_count": 10,
        "severity": "critical",
        "description": "Test 'test_db_connection' consistently fails - 10 failures",
        "source": "ci_retry_state",
    }


@pytest.fixture
def sample_repeated_failure_pattern():
    """Sample repeated failure pattern from nudge_state."""
    return {
        "pattern_type": "repeated_failure",
        "failure_reason": "timeout",
        "occurrence_count": 15,
        "severity": "high",
        "description": "Failure reason 'timeout' occurred 15 times",
        "source": "nudge_state",
    }


@pytest.fixture
def sample_slot_failure_pattern():
    """Sample slot high failure rate pattern."""
    return {
        "pattern_type": "slot_high_failure_rate",
        "slot_id": 3,
        "failure_rate": 0.75,
        "total_events": 20,
        "failed_events": 15,
        "severity": "high",
        "description": "Slot 3 has 75% failure rate",
        "source": "slot_history",
    }


@pytest.fixture
def sample_phase_failure_pattern():
    """Sample phase failure pattern."""
    return {
        "pattern_type": "phase_failure",
        "phase_type": "build",
        "occurrence_count": 8,
        "severity": "medium",
        "description": "Phase type 'build' failed 8 times",
        "source": "nudge_state",
    }


@pytest.fixture
def sample_escalation_pattern():
    """Sample escalation pattern."""
    return {
        "pattern_type": "escalation_pattern",
        "trigger": "max_retries",
        "occurrence_count": 4,
        "severity": "medium",
        "description": "Escalation triggered by 'max_retries' occurred 4 times",
        "source": "nudge_state",
    }


@pytest.fixture
def multiple_patterns(
    sample_flaky_test_pattern,
    sample_consistent_failure_pattern,
    sample_repeated_failure_pattern,
    sample_slot_failure_pattern,
):
    """Collection of multiple patterns for batch testing."""
    return [
        sample_flaky_test_pattern,
        sample_consistent_failure_pattern,
        sample_repeated_failure_pattern,
        sample_slot_failure_pattern,
    ]


@pytest.fixture
def existing_master_file(tmp_path):
    """Create a master file with existing improvements."""
    master_file = tmp_path / "AUTOPACK_IMPS_MASTER.json"
    existing_data = {
        "improvements": [
            {
                "id": "IMP-TEST-1234",
                "title": "Existing improvement",
                "category": "testing",
                "priority": "medium",
                "status": "pending",
                "description": "An existing improvement",
                "auto_generated": True,
            }
        ],
        "metadata": {"version": "1.0", "last_updated": "2026-01-01T00:00:00"},
    }
    master_file.write_text(json.dumps(existing_data))
    return master_file


class TestImprovementGeneratorInit:
    """Tests for ImprovementGenerator initialization."""

    def test_init_with_path(self, temp_master_file):
        """Test generator initializes with Path object."""
        generator = ImprovementGenerator(temp_master_file)
        assert generator.master_file == temp_master_file

    def test_init_with_string_path(self, tmp_path):
        """Test generator accepts string paths."""
        path_str = str(tmp_path / "master.json")
        generator = ImprovementGenerator(path_str)
        assert generator.master_file == Path(path_str)

    def test_pattern_to_category_mapping(self, temp_master_file):
        """Test that pattern to category mapping is configured."""
        generator = ImprovementGenerator(temp_master_file)
        assert "flaky_test" in generator.PATTERN_TO_CATEGORY
        assert generator.PATTERN_TO_CATEGORY["flaky_test"] == "testing"
        assert generator.PATTERN_TO_CATEGORY["slot_high_failure_rate"] == "reliability"


class TestPatternToImp:
    """Tests for pattern_to_imp() method."""

    def test_flaky_test_conversion(self, temp_master_file, sample_flaky_test_pattern):
        """Test conversion of flaky test pattern to IMP."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)

        assert "id" in imp
        assert imp["id"].startswith("IMP-TEST-")
        assert "flaky" in imp["title"].lower()
        assert imp["category"] == "testing"
        assert imp["priority"] == "high"
        assert imp["status"] == "pending"
        assert imp["auto_generated"] is True
        assert "test_auth_flow" in imp["title"]

    def test_consistent_failure_conversion(
        self, temp_master_file, sample_consistent_failure_pattern
    ):
        """Test conversion of consistent CI failure pattern."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_consistent_failure_pattern)

        assert imp["id"].startswith("IMP-TEST-")
        assert imp["category"] == "testing"
        assert imp["priority"] == "critical"
        assert "test_db_connection" in imp["title"]

    def test_repeated_failure_conversion(self, temp_master_file, sample_repeated_failure_pattern):
        """Test conversion of repeated failure pattern."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_repeated_failure_pattern)

        assert imp["id"].startswith("IMP-REL-")
        assert imp["category"] == "reliability"
        assert imp["priority"] == "high"
        assert "timeout" in imp["title"].lower()

    def test_slot_failure_conversion(self, temp_master_file, sample_slot_failure_pattern):
        """Test conversion of slot high failure rate pattern."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_slot_failure_pattern)

        assert imp["id"].startswith("IMP-REL-")
        assert imp["category"] == "reliability"
        assert "slot" in imp["title"].lower()
        assert imp["metadata"]["slot_id"] == 3
        assert imp["metadata"]["failure_rate"] == 0.75

    def test_phase_failure_conversion(self, temp_master_file, sample_phase_failure_pattern):
        """Test conversion of phase failure pattern."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_phase_failure_pattern)

        assert imp["id"].startswith("IMP-AUTO-")
        assert imp["category"] == "automation"
        assert "build" in imp["title"].lower()

    def test_escalation_pattern_conversion(self, temp_master_file, sample_escalation_pattern):
        """Test conversion of escalation pattern."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_escalation_pattern)

        assert imp["id"].startswith("IMP-AUTO-")
        assert imp["category"] == "automation"
        assert "escalation" in imp["title"].lower() or "max_retries" in imp["title"].lower()

    def test_imp_has_required_fields(self, temp_master_file, sample_flaky_test_pattern):
        """Test that generated IMP has all required fields."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)

        required_fields = [
            "id",
            "title",
            "category",
            "priority",
            "status",
            "description",
            "recommended_action",
            "source",
            "created_at",
            "updated_at",
            "auto_generated",
        ]
        for field in required_fields:
            assert field in imp, f"Missing required field: {field}"

    def test_imp_source_metadata(self, temp_master_file, sample_flaky_test_pattern):
        """Test that IMP includes source metadata."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)

        source = imp["source"]
        assert source["type"] == "telemetry_auto_generated"
        assert source["pattern_type"] == "flaky_test"
        assert source["telemetry_source"] == "ci_retry_state"

    def test_unknown_pattern_type(self, temp_master_file):
        """Test handling of unknown pattern types."""
        generator = ImprovementGenerator(temp_master_file)
        unknown_pattern = {
            "pattern_type": "some_new_type",
            "description": "Unknown pattern detected",
            "severity": "low",
            "source": "unknown_source",
        }
        imp = generator.pattern_to_imp(unknown_pattern)

        assert imp["id"].startswith("IMP-GEN-")
        assert imp["category"] == "general"
        assert imp["priority"] == "low"


class TestAppendToMaster:
    """Tests for append_to_master() method."""

    def test_creates_new_master_file(self, temp_master_file, sample_flaky_test_pattern):
        """Test that master file is created if it doesn't exist."""
        assert not temp_master_file.exists()

        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)
        added = generator.append_to_master([imp])

        assert temp_master_file.exists()
        assert added == 1

        # Verify content
        data = json.loads(temp_master_file.read_text())
        assert len(data["improvements"]) == 1
        assert data["improvements"][0]["id"] == imp["id"]

    def test_appends_to_existing_file(self, existing_master_file, sample_flaky_test_pattern):
        """Test appending to existing master file."""
        generator = ImprovementGenerator(existing_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)
        added = generator.append_to_master([imp])

        assert added == 1

        data = json.loads(existing_master_file.read_text())
        assert len(data["improvements"]) == 2

    def test_skips_duplicates_by_id(self, temp_master_file, sample_flaky_test_pattern):
        """Test that duplicate improvements are skipped by ID."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)

        # Add same improvement twice
        added1 = generator.append_to_master([imp])
        added2 = generator.append_to_master([imp])

        assert added1 == 1
        assert added2 == 0

        data = json.loads(temp_master_file.read_text())
        assert len(data["improvements"]) == 1

    def test_skips_duplicates_by_title(self, temp_master_file, sample_flaky_test_pattern):
        """Test that duplicate improvements are skipped by title."""
        generator = ImprovementGenerator(temp_master_file)
        imp1 = generator.pattern_to_imp(sample_flaky_test_pattern)

        # Modify ID but keep same title
        imp2 = imp1.copy()
        imp2["id"] = "IMP-DIFFERENT-9999"

        added1 = generator.append_to_master([imp1])
        added2 = generator.append_to_master([imp2])

        assert added1 == 1
        assert added2 == 0

    def test_empty_list_returns_zero(self, temp_master_file):
        """Test that empty list returns 0."""
        generator = ImprovementGenerator(temp_master_file)
        added = generator.append_to_master([])
        assert added == 0

    def test_multiple_improvements(self, temp_master_file, multiple_patterns):
        """Test adding multiple improvements at once."""
        generator = ImprovementGenerator(temp_master_file)
        improvements = generator.generate_from_patterns(multiple_patterns)
        added = generator.append_to_master(improvements)

        assert added == len(multiple_patterns)

        data = json.loads(temp_master_file.read_text())
        assert len(data["improvements"]) == len(multiple_patterns)

    def test_updates_metadata_timestamp(self, temp_master_file, sample_flaky_test_pattern):
        """Test that metadata timestamp is updated."""
        generator = ImprovementGenerator(temp_master_file)
        imp = generator.pattern_to_imp(sample_flaky_test_pattern)
        generator.append_to_master([imp])

        data = json.loads(temp_master_file.read_text())
        assert data["metadata"]["last_updated"] is not None
        assert "version" in data["metadata"]


class TestGenerateFromPatterns:
    """Tests for generate_from_patterns() method."""

    def test_converts_all_patterns(self, temp_master_file, multiple_patterns):
        """Test that all patterns are converted to improvements."""
        generator = ImprovementGenerator(temp_master_file)
        improvements = generator.generate_from_patterns(multiple_patterns)

        assert len(improvements) == len(multiple_patterns)

    def test_sorted_by_priority(self, temp_master_file, multiple_patterns):
        """Test that improvements are sorted by priority."""
        generator = ImprovementGenerator(temp_master_file)
        improvements = generator.generate_from_patterns(multiple_patterns)

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [priority_order.get(imp["priority"], 4) for imp in improvements]

        assert priorities == sorted(priorities)

    def test_empty_patterns_list(self, temp_master_file):
        """Test handling of empty patterns list."""
        generator = ImprovementGenerator(temp_master_file)
        improvements = generator.generate_from_patterns([])

        assert improvements == []


class TestGetPendingImprovements:
    """Tests for get_pending_improvements() method."""

    def test_returns_pending_only(self, tmp_path):
        """Test that only pending improvements are returned."""
        master_file = tmp_path / "master.json"
        data = {
            "improvements": [
                {"id": "IMP-1", "status": "pending", "title": "Pending 1"},
                {"id": "IMP-2", "status": "completed", "title": "Completed"},
                {"id": "IMP-3", "status": "pending", "title": "Pending 2"},
                {"id": "IMP-4", "status": "in_progress", "title": "In Progress"},
            ],
            "metadata": {"version": "1.0"},
        }
        master_file.write_text(json.dumps(data))

        generator = ImprovementGenerator(master_file)
        pending = generator.get_pending_improvements()

        assert len(pending) == 2
        assert all(imp["status"] == "pending" for imp in pending)

    def test_empty_file_returns_empty_list(self, temp_master_file):
        """Test that empty/missing file returns empty list."""
        generator = ImprovementGenerator(temp_master_file)
        pending = generator.get_pending_improvements()

        assert pending == []


class TestMarkImprovementStatus:
    """Tests for mark_improvement_status() method."""

    def test_updates_status(self, tmp_path):
        """Test that status is updated correctly."""
        master_file = tmp_path / "master.json"
        data = {
            "improvements": [
                {"id": "IMP-TEST-0001", "status": "pending", "title": "Test"},
            ],
            "metadata": {"version": "1.0"},
        }
        master_file.write_text(json.dumps(data))

        generator = ImprovementGenerator(master_file)
        result = generator.mark_improvement_status("IMP-TEST-0001", "completed")

        assert result is True

        updated_data = json.loads(master_file.read_text())
        assert updated_data["improvements"][0]["status"] == "completed"
        assert "updated_at" in updated_data["improvements"][0]

    def test_returns_false_for_missing_id(self, tmp_path):
        """Test that False is returned for non-existent ID."""
        master_file = tmp_path / "master.json"
        data = {
            "improvements": [
                {"id": "IMP-TEST-0001", "status": "pending"},
            ],
            "metadata": {"version": "1.0"},
        }
        master_file.write_text(json.dumps(data))

        generator = ImprovementGenerator(master_file)
        result = generator.mark_improvement_status("IMP-NONEXISTENT", "completed")

        assert result is False

    def test_rejects_invalid_status(self, tmp_path):
        """Test that invalid status values are rejected."""
        master_file = tmp_path / "master.json"
        data = {
            "improvements": [
                {"id": "IMP-TEST-0001", "status": "pending"},
            ],
            "metadata": {"version": "1.0"},
        }
        master_file.write_text(json.dumps(data))

        generator = ImprovementGenerator(master_file)
        result = generator.mark_improvement_status("IMP-TEST-0001", "invalid_status")

        assert result is False

        # Verify status wasn't changed
        updated_data = json.loads(master_file.read_text())
        assert updated_data["improvements"][0]["status"] == "pending"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_corrupted_master_file(self, tmp_path):
        """Test handling of corrupted master file."""
        master_file = tmp_path / "master.json"
        master_file.write_text("{ invalid json }")

        generator = ImprovementGenerator(master_file)
        # Should not raise, should create new structure
        pending = generator.get_pending_improvements()

        assert pending == []

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created if needed."""
        master_file = tmp_path / "nested" / "dirs" / "master.json"
        assert not master_file.parent.exists()

        generator = ImprovementGenerator(master_file)
        imp = {
            "id": "IMP-TEST-0001",
            "title": "Test",
            "category": "testing",
            "priority": "medium",
            "status": "pending",
            "description": "Test",
            "recommended_action": "Test",
            "source": {"type": "test"},
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
            "auto_generated": True,
        }
        generator.append_to_master([imp])

        assert master_file.exists()

    def test_pattern_with_missing_fields(self, temp_master_file):
        """Test handling of patterns with missing optional fields."""
        generator = ImprovementGenerator(temp_master_file)
        minimal_pattern = {
            "pattern_type": "unknown",
        }
        imp = generator.pattern_to_imp(minimal_pattern)

        # Should generate valid IMP despite missing fields
        assert "id" in imp
        assert "title" in imp
        assert imp["category"] == "general"

    def test_deterministic_id_generation(self, temp_master_file):
        """Test that same pattern generates same ID."""
        generator = ImprovementGenerator(temp_master_file)
        pattern = {
            "pattern_type": "flaky_test",
            "test_id": "test_example",
            "description": "Test description",
        }

        imp1 = generator.pattern_to_imp(pattern)
        imp2 = generator.pattern_to_imp(pattern)

        assert imp1["id"] == imp2["id"]


class TestIntegrationWithTelemetryAnalyzer:
    """Integration tests with TelemetryAnalyzer patterns."""

    def test_handles_real_analyzer_pattern_format(self, temp_master_file):
        """Test handling of actual TelemetryAnalyzer pattern format."""
        # Pattern format as produced by TelemetryAnalyzer
        analyzer_patterns = [
            {
                "pattern_type": "repeated_failure",
                "failure_reason": "timeout",
                "occurrence_count": 5,
                "severity": "high",
                "description": "Failure reason 'timeout' occurred 5 times",
                "source": "nudge_state",
            },
            {
                "pattern_type": "flaky_test",
                "test_id": "test_auth",
                "retry_count": 3,
                "success_rate": 0.33,
                "severity": "high",
                "description": "Test 'test_auth' is flaky - 3 retries with mixed outcomes",
                "source": "ci_retry_state",
            },
            {
                "pattern_type": "slot_high_failure_rate",
                "slot_id": 1,
                "failure_rate": 0.67,
                "total_events": 3,
                "failed_events": 2,
                "severity": "high",
                "description": "Slot 1 has 67% failure rate",
                "source": "slot_history",
            },
        ]

        generator = ImprovementGenerator(temp_master_file)
        improvements = generator.generate_from_patterns(analyzer_patterns)
        added = generator.append_to_master(improvements)

        assert added == 3
        assert len(improvements) == 3

        # Verify each improvement is properly formatted
        for imp in improvements:
            assert imp["status"] == "pending"
            assert imp["auto_generated"] is True
            assert "source" in imp
            assert imp["source"]["type"] == "telemetry_auto_generated"
