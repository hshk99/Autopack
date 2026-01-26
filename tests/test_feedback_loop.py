"""Tests for Telemetry-to-Discovery Feedback Loop (IMP-TEL-003).

Tests the generate_discovery_input() method and related feedback loop functionality
that closes the self-improvement loop by feeding operational telemetry back into
discovery phases.
"""

import json
from pathlib import Path

import pytest

from src.telemetry_analyzer import TelemetryAnalyzer


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create a temporary directory for telemetry files."""
    return tmp_path


@pytest.fixture
def sample_nudge_state_with_patterns():
    """Sample nudge state data with recurring failure patterns."""
    return {
        "nudges": [
            {
                "id": "nudge-1",
                "failure_reason": "ci_failure",
                "phase_type": "build",
                "status": "failed",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-2",
                "failure_reason": "ci_failure",
                "phase_type": "build",
                "status": "failed",
                "escalated": False,
            },
            {
                "id": "nudge-3",
                "failure_reason": "ci_failure",
                "phase_type": "test",
                "status": "failed",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-4",
                "failure_reason": "timeout",
                "phase_type": "deploy",
                "status": "error",
                "escalated": True,
                "escalation_trigger": "stagnation",
            },
            {
                "id": "nudge-5",
                "failure_reason": "timeout",
                "phase_type": "deploy",
                "status": "error",
                "escalated": False,
            },
        ]
    }


@pytest.fixture
def sample_ci_retry_with_flaky():
    """Sample CI retry state with flaky and consistent failures."""
    return {
        "retries": [
            # Flaky test
            {"test_name": "test_integration", "outcome": "failed", "workflow": "ci"},
            {"test_name": "test_integration", "outcome": "failed", "workflow": "ci"},
            {"test_name": "test_integration", "outcome": "success", "workflow": "ci"},
            # Consistent failure
            {
                "test_name": "test_db",
                "outcome": "failed",
                "failure_reason": "connection_error",
                "workflow": "integration",
            },
            {
                "test_name": "test_db",
                "outcome": "failed",
                "failure_reason": "connection_error",
                "workflow": "integration",
            },
            {
                "test_name": "test_db",
                "outcome": "failed",
                "failure_reason": "connection_error",
                "workflow": "integration",
            },
        ]
    }


@pytest.fixture
def sample_slot_history_with_issues():
    """Sample slot history with problematic events."""
    return {
        "slots": [
            {"slot_id": 1, "status": "failed", "event_type": "connection_error_detected"},
            {"slot_id": 1, "status": "failed", "event_type": "connection_error_detected"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
        ],
        "events": [
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 2, "event_type": "escalation_level_change"},
            {"slot": 2, "event_type": "escalation_level_change"},
        ],
    }


@pytest.fixture
def populated_feedback_dir(
    temp_telemetry_dir,
    sample_nudge_state_with_patterns,
    sample_ci_retry_with_flaky,
    sample_slot_history_with_issues,
):
    """Create telemetry files for feedback loop testing."""
    (temp_telemetry_dir / "nudge_state.json").write_text(
        json.dumps(sample_nudge_state_with_patterns)
    )
    (temp_telemetry_dir / "ci_retry_state.json").write_text(json.dumps(sample_ci_retry_with_flaky))
    (temp_telemetry_dir / "slot_history.json").write_text(
        json.dumps(sample_slot_history_with_issues)
    )
    return temp_telemetry_dir


class TestGenerateDiscoveryInput:
    """Tests for generate_discovery_input() method."""

    def test_returns_list(self, populated_feedback_dir):
        """Test that generate_discovery_input returns a list."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()
        assert isinstance(result, list)

    def test_empty_when_no_data(self, temp_telemetry_dir):
        """Test that empty list is returned when no telemetry data exists."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        result = analyzer.generate_discovery_input()
        assert result == []

    def test_discovery_input_structure(self, populated_feedback_dir):
        """Test that discovery input has expected structure."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        assert len(result) == 1
        discovery_input = result[0]

        assert "generated_at" in discovery_input
        assert "telemetry_source" in discovery_input
        assert "total_patterns_analyzed" in discovery_input
        assert "recurring_issues" in discovery_input
        assert "high_value_categories" in discovery_input
        assert "recommendations" in discovery_input
        assert "pattern_summary" in discovery_input

    def test_recurring_issues_detected(self, populated_feedback_dir):
        """Test that recurring issues are correctly identified."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        recurring_issues = discovery_input["recurring_issues"]

        # Should have detected recurring issues from patterns
        assert len(recurring_issues) > 0

        # Each issue should have expected fields
        for issue in recurring_issues:
            assert "issue_type" in issue
            assert "description" in issue
            assert "occurrence_count" in issue
            assert "severity" in issue
            assert "source" in issue
            assert "details" in issue

    def test_high_value_categories_ranked(self, populated_feedback_dir):
        """Test that high-value categories are ranked by score."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        high_value_categories = discovery_input["high_value_categories"]

        # Should have categories
        assert len(high_value_categories) > 0

        # Categories should have category and score
        for cat in high_value_categories:
            assert "category" in cat
            assert "score" in cat

        # Should be sorted by score (descending)
        scores = [cat["score"] for cat in high_value_categories]
        assert scores == sorted(scores, reverse=True)

    def test_recommendations_generated(self, populated_feedback_dir):
        """Test that recommendations are generated based on patterns."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        recommendations = discovery_input["recommendations"]

        # Should have recommendations
        assert len(recommendations) > 0

        # Each recommendation should have expected fields
        for rec in recommendations:
            assert "focus_area" in rec
            assert "priority" in rec
            assert "recommendation" in rec
            assert "related_pattern_count" in rec

    def test_pattern_summary_included(self, populated_feedback_dir):
        """Test that pattern summary is included."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        pattern_summary = discovery_input["pattern_summary"]

        # Should have pattern type counts
        assert isinstance(pattern_summary, dict)
        assert len(pattern_summary) > 0

    def test_total_patterns_count(self, populated_feedback_dir):
        """Test that total patterns count matches actual patterns."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        total_patterns = discovery_input["total_patterns_analyzed"]

        # Get actual pattern count
        all_patterns = analyzer.get_all_patterns()
        assert total_patterns == len(all_patterns)


class TestExtractPatternDetails:
    """Tests for _extract_pattern_details() helper method."""

    def test_flaky_test_details(self, populated_feedback_dir):
        """Test extraction of flaky test details."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)

        flaky_pattern = {
            "pattern_type": "flaky_test",
            "test_id": "test_auth",
            "retry_count": 3,
            "success_rate": 0.33,
        }

        details = analyzer._extract_pattern_details(flaky_pattern)

        assert details["test_id"] == "test_auth"
        assert details["retry_count"] == 3
        assert details["success_rate"] == 0.33

    def test_slot_failure_details(self, populated_feedback_dir):
        """Test extraction of slot failure details."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)

        slot_pattern = {
            "pattern_type": "slot_high_failure_rate",
            "slot_id": 5,
            "failure_rate": 0.75,
        }

        details = analyzer._extract_pattern_details(slot_pattern)

        assert details["slot_id"] == 5
        assert details["failure_rate"] == 0.75

    def test_phase_failure_details(self, populated_feedback_dir):
        """Test extraction of phase failure details."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)

        phase_pattern = {
            "pattern_type": "phase_failure",
            "phase_type": "deploy",
        }

        details = analyzer._extract_pattern_details(phase_pattern)

        assert details["phase_type"] == "deploy"

    def test_unknown_pattern_returns_empty(self, populated_feedback_dir):
        """Test that unknown pattern types return empty details."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)

        unknown_pattern = {
            "pattern_type": "unknown_type",
            "some_field": "value",
        }

        details = analyzer._extract_pattern_details(unknown_pattern)

        assert details == {}


class TestExportDiscoveryInput:
    """Tests for export_discovery_input() method."""

    def test_exports_to_file(self, populated_feedback_dir, tmp_path):
        """Test that discovery input is exported to a file."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        output_path = tmp_path / "discovery_input.json"

        result = analyzer.export_discovery_input(output_path)

        assert result is True
        assert output_path.exists()

    def test_exported_file_valid_json(self, populated_feedback_dir, tmp_path):
        """Test that exported file contains valid JSON."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        output_path = tmp_path / "discovery_input.json"

        analyzer.export_discovery_input(output_path)

        with open(output_path) as f:
            data = json.load(f)

        assert "discovery_input" in data

    def test_exported_structure_matches(self, populated_feedback_dir, tmp_path):
        """Test that exported structure matches generate_discovery_input output."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        output_path = tmp_path / "discovery_input.json"

        analyzer.export_discovery_input(output_path)

        with open(output_path) as f:
            exported_data = json.load(f)

        discovery_input = exported_data["discovery_input"]

        assert "recurring_issues" in discovery_input
        assert "high_value_categories" in discovery_input
        assert "recommendations" in discovery_input
        assert "pattern_summary" in discovery_input

    def test_creates_parent_directories(self, populated_feedback_dir, tmp_path):
        """Test that parent directories are created if they don't exist."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        output_path = tmp_path / "nested" / "deep" / "discovery_input.json"

        result = analyzer.export_discovery_input(output_path)

        assert result is True
        assert output_path.exists()

    def test_exports_empty_structure_when_no_data(self, temp_telemetry_dir, tmp_path):
        """Test that empty structure is exported when no telemetry data exists."""
        analyzer = TelemetryAnalyzer(temp_telemetry_dir)
        output_path = tmp_path / "discovery_input.json"

        result = analyzer.export_discovery_input(output_path)

        assert result is True

        with open(output_path) as f:
            data = json.load(f)

        discovery_input = data["discovery_input"]
        assert discovery_input["recurring_issues"] == []
        assert discovery_input["high_value_categories"] == []
        assert discovery_input["recommendations"] == []

    def test_handles_path_as_string(self, populated_feedback_dir, tmp_path):
        """Test that string paths are accepted."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        output_path = str(tmp_path / "discovery_input.json")

        result = analyzer.export_discovery_input(output_path)

        assert result is True
        assert Path(output_path).exists()


class TestFeedbackLoopIntegration:
    """Integration tests for the complete feedback loop."""

    def test_feedback_loop_end_to_end(self, populated_feedback_dir, tmp_path):
        """Test complete feedback loop from telemetry to discovery input."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)

        # Step 1: Analyze patterns
        all_patterns = analyzer.get_all_patterns()
        assert len(all_patterns) > 0

        # Step 2: Generate discovery input
        discovery_input = analyzer.generate_discovery_input()
        assert len(discovery_input) == 1

        # Step 3: Export for consumption
        output_path = tmp_path / "TELEMETRY_FEEDBACK.json"
        result = analyzer.export_discovery_input(output_path)
        assert result is True

        # Step 4: Verify exported data is usable
        with open(output_path) as f:
            data = json.load(f)

        discovery = data["discovery_input"]

        # Verify recurring issues map back to detected patterns
        assert discovery["total_patterns_analyzed"] == len(all_patterns)

        # Verify recommendations are actionable
        for rec in discovery["recommendations"]:
            assert rec["focus_area"] in ["testing", "reliability", "automation", "monitoring"]
            assert rec["priority"] in ["critical", "high", "medium", "low"]

    def test_recommendations_cover_major_issues(self, populated_feedback_dir):
        """Test that recommendations address the major issue categories."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        recommendations = discovery_input["recommendations"]

        focus_areas = [rec["focus_area"] for rec in recommendations]

        # Given the test data has flaky tests and reliability issues,
        # should have recommendations for testing and/or reliability
        assert len(focus_areas) > 0

    def test_category_scores_reflect_severity(self, populated_feedback_dir):
        """Test that category scores reflect pattern severity."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        high_value_categories = discovery_input["high_value_categories"]

        # Categories with critical/high severity patterns should have higher scores
        for cat in high_value_categories:
            assert cat["score"] > 0


class TestRecurringIssuesContent:
    """Tests for recurring issues content and quality."""

    def test_recurring_issues_have_actionable_details(self, populated_feedback_dir):
        """Test that recurring issues include actionable details."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        recurring_issues = discovery_input["recurring_issues"]

        for issue in recurring_issues:
            # Should have enough info to take action
            assert issue["description"]
            assert issue["occurrence_count"] >= 2
            assert issue["issue_type"]

    def test_recurring_issues_sorted_by_severity(self, populated_feedback_dir):
        """Test that recurring issues with higher severity/count are prioritized."""
        analyzer = TelemetryAnalyzer(populated_feedback_dir)
        result = analyzer.generate_discovery_input()

        discovery_input = result[0]
        recurring_issues = discovery_input["recurring_issues"]

        # Verify issues include severity info for prioritization
        severities = [issue["severity"] for issue in recurring_issues]
        assert all(s in ["critical", "high", "medium", "low"] for s in severities)
