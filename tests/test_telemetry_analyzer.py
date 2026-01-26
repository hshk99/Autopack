"""Tests for TelemetryAnalyzer."""

import json
from pathlib import Path

import pytest

from src.telemetry_analyzer import TelemetryAnalyzer


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create a temporary directory for telemetry files."""
    return tmp_path


@pytest.fixture
def sample_nudge_state():
    """Sample nudge state data with various failure patterns."""
    return {
        "nudges": [
            {
                "id": "nudge-1",
                "failure_reason": "timeout",
                "phase_type": "build",
                "status": "failed",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-2",
                "failure_reason": "timeout",
                "phase_type": "build",
                "status": "failed",
                "escalated": False,
            },
            {
                "id": "nudge-3",
                "failure_reason": "merge_conflict",
                "phase_type": "deploy",
                "status": "failed",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-4",
                "phase_type": "test",
                "status": "completed",
                "escalated": False,
            },
            {
                "id": "nudge-5",
                "failure_reason": "timeout",
                "phase_type": "build",
                "status": "error",
                "escalated": True,
                "escalation_trigger": "stagnation",
            },
        ]
    }


@pytest.fixture
def sample_ci_retry_state():
    """Sample CI retry state data with flaky and consistent failures."""
    return {
        "retries": [
            # Flaky test - eventually succeeds
            {"test_name": "test_auth", "outcome": "failed", "attempt": 1, "workflow": "ci"},
            {"test_name": "test_auth", "outcome": "failed", "attempt": 2, "workflow": "ci"},
            {"test_name": "test_auth", "outcome": "success", "attempt": 3, "workflow": "ci"},
            # Consistent failure
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "failure_reason": "connection_refused",
                "workflow": "integration",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "failure_reason": "connection_refused",
                "workflow": "integration",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "failure_reason": "connection_refused",
                "workflow": "integration",
            },
            # Single success
            {"test_name": "test_simple", "outcome": "success", "workflow": "unit"},
            # Workflow with multiple failures
            {
                "test_name": "test_deploy_1",
                "outcome": "failed",
                "failure_reason": "timeout",
                "workflow": "deploy",
            },
            {
                "test_name": "test_deploy_2",
                "outcome": "failed",
                "failure_reason": "timeout",
                "workflow": "deploy",
            },
        ]
    }


@pytest.fixture
def sample_slot_history():
    """Sample slot history data with various event patterns."""
    return {
        "slots": [
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            {"slot_id": 1, "status": "failed", "event_type": "nudge", "error_type": "timeout"},
            {"slot_id": 1, "status": "failed", "event_type": "nudge", "error_type": "timeout"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
            {"slot_id": 3, "status": "failed", "event_type": "connection_error_detected"},
            {"slot_id": 3, "status": "failed", "event_type": "connection_error_detected"},
        ],
        "events": [
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 2, "event_type": "escalation_level_change"},
            {"slot": 2, "event_type": "escalation_level_change"},
            {"slot": 2, "event_type": "escalation_level_change"},
        ],
    }


@pytest.fixture
def populated_telemetry_dir(
    temp_telemetry_dir, sample_nudge_state, sample_ci_retry_state, sample_slot_history
):
    """Create telemetry files in temp directory."""
    (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps(sample_nudge_state))
    (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps(sample_ci_retry_state))
    (temp_telemetry_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))
    return temp_telemetry_dir


class TestTelemetryAnalyzerInit:
    """Tests for TelemetryAnalyzer initialization."""

    def test_init_with_path(self, temp_telemetry_dir):
        """Test analyzer initializes with Path object."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        assert analyzer.base_path == temp_telemetry_dir

    def test_init_with_string_path(self, temp_telemetry_dir):
        """Test analyzer accepts string paths."""
        analyzer = TelemetryAnalyzer(str(temp_telemetry_dir))
        assert analyzer.base_path == Path(str(temp_telemetry_dir))

    def test_file_paths_configured(self, temp_telemetry_dir):
        """Test telemetry file paths are correctly configured."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        assert analyzer.nudge_state_file == temp_telemetry_dir / "nudge_state.json"
        assert analyzer.ci_retry_file == temp_telemetry_dir / "ci_retry_state.json"
        assert analyzer.slot_history_file == temp_telemetry_dir / "slot_history.json"


class TestAnalyzeFailurePatterns:
    """Tests for analyze_failure_patterns() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test analysis with no telemetry files."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()
        assert patterns == []

    def test_detects_repeated_failures(self, populated_telemetry_dir):
        """Test detection of repeated failure reasons."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should detect 'timeout' as repeated failure (3 occurrences)
        timeout_patterns = [p for p in patterns if p.get("failure_reason") == "timeout"]
        assert len(timeout_patterns) == 1
        assert timeout_patterns[0]["occurrence_count"] == 3
        assert timeout_patterns[0]["pattern_type"] == "repeated_failure"

    def test_detects_phase_failures(self, populated_telemetry_dir):
        """Test detection of phase type failures."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should detect 'build' phase failures (3 occurrences)
        build_patterns = [p for p in patterns if p.get("phase_type") == "build"]
        assert len(build_patterns) == 1
        assert build_patterns[0]["occurrence_count"] == 3
        assert build_patterns[0]["pattern_type"] == "phase_failure"

    def test_detects_escalation_patterns(self, populated_telemetry_dir):
        """Test detection of escalation trigger patterns."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should detect 'max_retries' as escalation trigger (2 occurrences)
        escalation_patterns = [p for p in patterns if p.get("pattern_type") == "escalation_pattern"]
        assert len(escalation_patterns) >= 1

    def test_pattern_metadata(self, populated_telemetry_dir):
        """Test that patterns include expected metadata."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        for pattern in patterns:
            assert "pattern_type" in pattern
            assert "occurrence_count" in pattern
            assert "severity" in pattern
            assert "description" in pattern
            assert "source" in pattern
            assert pattern["source"] == "nudge_state"


class TestAnalyzeCiPatterns:
    """Tests for analyze_ci_patterns() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test analysis with no CI retry data."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()
        assert patterns == []

    def test_detects_flaky_tests(self, populated_telemetry_dir):
        """Test detection of flaky tests."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()

        # Should detect 'test_auth' as flaky (fails then succeeds)
        flaky_patterns = [p for p in patterns if p.get("pattern_type") == "flaky_test"]
        assert len(flaky_patterns) == 1
        assert flaky_patterns[0]["test_id"] == "test_auth"
        assert flaky_patterns[0]["retry_count"] == 3

    def test_detects_consistent_failures(self, populated_telemetry_dir):
        """Test detection of consistently failing tests."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()

        # Should detect 'test_db_connection' as consistent failure
        failure_patterns = [p for p in patterns if p.get("pattern_type") == "consistent_ci_failure"]
        assert len(failure_patterns) == 1
        assert failure_patterns[0]["test_id"] == "test_db_connection"
        assert failure_patterns[0]["failure_count"] == 3

    def test_detects_workflow_failures(self, populated_telemetry_dir):
        """Test detection of workflow failure patterns."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()

        # Should detect patterns in integration and deploy workflows
        workflow_patterns = [p for p in patterns if p.get("pattern_type") == "workflow_failure"]
        workflow_names = [p.get("workflow") for p in workflow_patterns]

        # At least integration workflow should be detected (3 failures)
        assert "integration" in workflow_names

    def test_pattern_severity(self, populated_telemetry_dir):
        """Test that severity is correctly assigned."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()

        # Flaky tests should be high severity
        flaky_patterns = [p for p in patterns if p.get("pattern_type") == "flaky_test"]
        for p in flaky_patterns:
            assert p["severity"] == "high"

        # Consistent failures should be critical severity
        failure_patterns = [p for p in patterns if p.get("pattern_type") == "consistent_ci_failure"]
        for p in failure_patterns:
            assert p["severity"] == "critical"


class TestAnalyzeSlotBehavior:
    """Tests for analyze_slot_behavior() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test analysis with no slot history data."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_slot_behavior()
        assert patterns == []

    def test_detects_high_failure_rate_slots(self, populated_telemetry_dir):
        """Test detection of slots with high failure rates."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_slot_behavior()

        # Slot 3 has 100% failure rate (2 failures, 0 successes in slots)
        high_failure_patterns = [
            p for p in patterns if p.get("pattern_type") == "slot_high_failure_rate"
        ]
        assert len(high_failure_patterns) >= 1

        slot_3_pattern = [p for p in high_failure_patterns if p.get("slot_id") == 3]
        assert len(slot_3_pattern) == 1
        assert slot_3_pattern[0]["failure_rate"] == 1.0

    def test_detects_frequent_events(self, populated_telemetry_dir):
        """Test detection of frequent problematic events."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_slot_behavior()

        # Should detect escalation_level_change (3 occurrences in events)
        frequent_patterns = [p for p in patterns if p.get("pattern_type") == "frequent_event"]
        event_types = [p.get("event_type") for p in frequent_patterns]

        assert "escalation_level_change" in event_types

    def test_detects_error_types(self, populated_telemetry_dir):
        """Test detection of common error types."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        patterns = analyzer.analyze_slot_behavior()

        # Should detect 'timeout' error type (2 occurrences)
        error_patterns = [p for p in patterns if p.get("pattern_type") == "slot_error_type"]
        error_types = [p.get("error_type") for p in error_patterns]

        assert "timeout" in error_types


class TestGenerateImprovementSuggestions:
    """Tests for generate_improvement_suggestions() method."""

    def test_empty_directory(self, temp_telemetry_dir):
        """Test suggestion generation with no data."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()
        assert suggestions == []

    def test_generates_suggestions_from_patterns(self, populated_telemetry_dir):
        """Test that suggestions are generated from all pattern types."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()

        # Should have suggestions from all three analysis types
        assert len(suggestions) > 0

        sources = set(s["telemetry_source"] for s in suggestions)
        assert "nudge_state" in sources
        assert "ci_retry_state" in sources
        assert "slot_history" in sources

    def test_suggestion_format(self, populated_telemetry_dir):
        """Test that suggestions have the expected format."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()

        for suggestion in suggestions:
            assert "id" in suggestion
            assert "title" in suggestion
            assert "category" in suggestion
            assert "priority" in suggestion
            assert "description" in suggestion
            assert "recommended_action" in suggestion
            assert "source_pattern" in suggestion
            assert "detected_at" in suggestion
            assert suggestion["auto_generated"] is True

    def test_suggestions_sorted_by_priority(self, populated_telemetry_dir):
        """Test that suggestions are sorted by priority."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities = [priority_order.get(s["priority"], 4) for s in suggestions]

        # Check that priorities are in non-decreasing order
        assert priorities == sorted(priorities)

    def test_suggestion_categories(self, populated_telemetry_dir):
        """Test that suggestions have appropriate categories."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()

        valid_categories = {
            "reliability",
            "automation",
            "testing",
            "ci_cd",
            "monitoring",
            "general",
        }
        for suggestion in suggestions:
            assert suggestion["category"] in valid_categories

    def test_flaky_test_suggestion(self, populated_telemetry_dir):
        """Test that flaky test patterns generate testing category suggestions."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        suggestions = analyzer.generate_improvement_suggestions()

        flaky_suggestions = [s for s in suggestions if s["source_pattern"] == "flaky_test"]
        assert len(flaky_suggestions) >= 1

        for suggestion in flaky_suggestions:
            assert suggestion["category"] == "testing"
            assert "flaky" in suggestion["title"].lower()


class TestGetSummary:
    """Tests for get_summary() method."""

    def test_summary_structure(self, populated_telemetry_dir):
        """Test that summary has expected structure."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        summary = analyzer.get_summary()

        assert "analysis_timestamp" in summary
        assert "base_path" in summary
        assert "pattern_counts" in summary
        assert "suggestion_count" in summary
        assert "suggestions_by_priority" in summary
        assert "suggestions_by_category" in summary
        assert "patterns" in summary
        assert "suggestions" in summary

    def test_pattern_counts(self, populated_telemetry_dir):
        """Test that pattern counts are correctly calculated."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        summary = analyzer.get_summary()

        pattern_counts = summary["pattern_counts"]
        assert pattern_counts["total_patterns"] == (
            pattern_counts["failure_patterns"]
            + pattern_counts["ci_patterns"]
            + pattern_counts["slot_patterns"]
        )

    def test_suggestion_counts_by_priority(self, populated_telemetry_dir):
        """Test suggestion counts by priority."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)
        summary = analyzer.get_summary()

        by_priority = summary["suggestions_by_priority"]
        total = (
            by_priority["critical"]
            + by_priority["high"]
            + by_priority["medium"]
            + by_priority["low"]
        )
        assert total == summary["suggestion_count"]


class TestCacheHandling:
    """Tests for data caching behavior."""

    def test_cache_prevents_multiple_reads(self, populated_telemetry_dir):
        """Test that data is cached after first read."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)

        # First call loads data
        patterns1 = analyzer.analyze_failure_patterns()
        # Second call should use cached data
        patterns2 = analyzer.analyze_failure_patterns()

        assert patterns1 == patterns2
        # Cache should be populated
        assert analyzer._nudge_data is not None

    def test_clear_cache(self, populated_telemetry_dir):
        """Test that clear_cache resets cached data."""
        analyzer = TelemetryAnalyzer(populated_telemetry_dir)

        # Load data
        analyzer.analyze_failure_patterns()
        assert analyzer._nudge_data is not None

        # Clear cache
        analyzer.clear_cache()

        assert analyzer._nudge_data is None
        assert analyzer._ci_retry_data is None
        assert analyzer._slot_history_data is None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_invalid_json(self, temp_telemetry_dir):
        """Test handling of invalid JSON files."""
        (temp_telemetry_dir / "nudge_state.json").write_text("{ invalid json }")

        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should return empty list, not crash
        assert patterns == []

    def test_handles_empty_arrays(self, temp_telemetry_dir):
        """Test handling of empty arrays in data."""
        (temp_telemetry_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps({"retries": []}))
        (temp_telemetry_dir / "slot_history.json").write_text(
            json.dumps({"slots": [], "events": []})
        )

        analyzer = TelemetryAnalyzer(temp_telemetry_dir)

        assert analyzer.analyze_failure_patterns() == []
        assert analyzer.analyze_ci_patterns() == []
        assert analyzer.analyze_slot_behavior() == []

    def test_handles_missing_fields(self, temp_telemetry_dir):
        """Test handling of missing expected fields."""
        (temp_telemetry_dir / "nudge_state.json").write_text(
            json.dumps({"nudges": [{"id": "n1"}, {"id": "n2"}]})  # Missing failure_reason, etc.
        )

        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should not crash
        assert isinstance(patterns, list)

    def test_handles_malformed_entries(self, temp_telemetry_dir):
        """Test handling of malformed entries in arrays."""
        (temp_telemetry_dir / "ci_retry_state.json").write_text(
            json.dumps({"retries": ["not a dict", 123, None, {"test_name": "valid"}]})
        )

        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_ci_patterns()

        # Should not crash, should skip invalid entries
        assert isinstance(patterns, list)

    def test_below_threshold_not_reported(self, temp_telemetry_dir):
        """Test that patterns below threshold are not reported."""
        (temp_telemetry_dir / "nudge_state.json").write_text(
            json.dumps(
                {
                    "nudges": [
                        {"failure_reason": "unique_error_1", "status": "failed"},
                        # Only 1 occurrence - below MIN_PATTERN_THRESHOLD of 2
                    ]
                }
            )
        )

        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        patterns = analyzer.analyze_failure_patterns()

        # Should not report single occurrence
        unique_patterns = [p for p in patterns if p.get("failure_reason") == "unique_error_1"]
        assert len(unique_patterns) == 0
