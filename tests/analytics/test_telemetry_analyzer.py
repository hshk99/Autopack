"""Tests for TelemetryAnalyzer in autopack.analytics module."""

import json
from pathlib import Path

import pytest

from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_slot_history() -> dict:
    """Sample slot_history.json data with various patterns."""
    return {
        "slots": [
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            {"slot_id": 1, "status": "failed", "event_type": "nudge", "error_type": "timeout"},
            {"slot_id": 1, "status": "failed", "event_type": "nudge", "error_type": "timeout"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
            {"slot_id": 2, "status": "completed", "event_type": "nudge"},
            {
                "slot_id": 3,
                "status": "failed",
                "event_type": "connection_error_detected",
                "escalated": True,
                "escalation_level": 1,
            },
            {
                "slot_id": 3,
                "status": "failed",
                "event_type": "connection_error_detected",
                "escalated": True,
                "escalation_level": 2,
            },
            {
                "slot_id": 3,
                "status": "failed",
                "event_type": "connection_error_detected",
                "escalated": True,
                "escalation_level": 3,
            },
        ],
        "events": [
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 1, "event_type": "stagnation_detected"},
            {"slot": 2, "event_type": "escalation_level_change"},
            {"slot": 2, "event_type": "escalation_level_change"},
        ],
    }


@pytest.fixture
def sample_nudge_state() -> dict:
    """Sample nudge_state.json data with various effectiveness patterns."""
    return {
        "nudges": [
            {
                "id": "nudge-1",
                "phase_type": "build",
                "status": "resolved",
                "created_at": "2026-01-27T10:00:00Z",
                "resolved_at": "2026-01-27T10:30:00Z",
            },
            {
                "id": "nudge-2",
                "phase_type": "build",
                "status": "resolved",
                "created_at": "2026-01-27T11:00:00Z",
                "resolved_at": "2026-01-27T11:15:00Z",
            },
            {
                "id": "nudge-3",
                "phase_type": "build",
                "status": "failed",
                "failure_reason": "timeout",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-4",
                "phase_type": "test",
                "status": "resolved",
                "created_at": "2026-01-27T12:00:00Z",
                "resolved_at": "2026-01-27T12:45:00Z",
            },
            {
                "id": "nudge-5",
                "phase_type": "test",
                "status": "failed",
                "failure_reason": "assertion_error",
                "escalated": False,
            },
            {
                "id": "nudge-6",
                "phase_type": "test",
                "status": "failed",
                "failure_reason": "timeout",
                "escalated": True,
                "escalation_trigger": "stagnation",
            },
            {
                "id": "nudge-7",
                "phase_type": "deploy",
                "status": "failed",
                "failure_reason": "connection_refused",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
        ]
    }


@pytest.fixture
def sample_ci_retry_state() -> dict:
    """Sample ci_retry_state.json data with flaky and consistent failures."""
    return {
        "retries": [
            # Flaky test - fails then succeeds
            {
                "test_name": "test_auth_login",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "ci",
                "failure_reason": "timeout",
            },
            {
                "test_name": "test_auth_login",
                "outcome": "failed",
                "attempt": 2,
                "workflow": "ci",
                "failure_reason": "timeout",
            },
            {"test_name": "test_auth_login", "outcome": "success", "attempt": 3, "workflow": "ci"},
            # Another flaky test
            {
                "test_name": "test_api_rate_limit",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "integration",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "success",
                "attempt": 2,
                "workflow": "integration",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "failed",
                "attempt": 3,
                "workflow": "integration",
            },
            {
                "test_name": "test_api_rate_limit",
                "outcome": "success",
                "attempt": 4,
                "workflow": "integration",
            },
            # Consistent failure (not flaky, just broken)
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 1,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 2,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            {
                "test_name": "test_db_connection",
                "outcome": "failed",
                "attempt": 3,
                "workflow": "unit",
                "failure_reason": "connection_refused",
            },
            # Stable test (all pass)
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
            {
                "test_name": "test_simple_math",
                "outcome": "success",
                "attempt": 1,
                "workflow": "unit",
            },
        ]
    }


@pytest.fixture
def populated_state_dir(
    temp_state_dir: Path,
    sample_slot_history: dict,
    sample_nudge_state: dict,
    sample_ci_retry_state: dict,
) -> Path:
    """Create state files in temp directory."""
    (temp_state_dir / "slot_history.json").write_text(json.dumps(sample_slot_history))
    (temp_state_dir / "nudge_state.json").write_text(json.dumps(sample_nudge_state))
    (temp_state_dir / "ci_retry_state.json").write_text(json.dumps(sample_ci_retry_state))
    return temp_state_dir


class TestTelemetryAnalyzerInit:
    """Tests for TelemetryAnalyzer initialization."""

    def test_init_with_path(self, temp_state_dir: Path) -> None:
        """Test analyzer initializes with Path object."""
        analyzer = TelemetryAnalyzer(temp_state_dir)
        assert analyzer.state_dir == temp_state_dir

    def test_init_with_string_path(self, temp_state_dir: Path) -> None:
        """Test analyzer accepts string paths."""
        analyzer = TelemetryAnalyzer(str(temp_state_dir))
        assert analyzer.state_dir == Path(str(temp_state_dir))


class TestAnalyzeSlotReliability:
    """Tests for analyze_slot_reliability() method."""

    def test_empty_directory(self, temp_state_dir: Path) -> None:
        """Test analysis with no state files."""
        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.analyze_slot_reliability()

        assert result["slot_metrics"] == {}
        assert result["problematic_slots"] == []
        assert result["overall_reliability"] == 1.0
        assert result["recommendations"] == []

    def test_detects_slot_metrics(self, populated_state_dir: Path) -> None:
        """Test that slot metrics are calculated correctly."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_slot_reliability()

        assert "slot_metrics" in result
        # Slot 2 has 3 events, all completed
        if 2 in result["slot_metrics"]:
            assert result["slot_metrics"][2]["total_events"] == 3
            assert result["slot_metrics"][2]["failure_rate"] == 0.0

    def test_detects_problematic_slots(self, populated_state_dir: Path) -> None:
        """Test detection of slots with high escalation rates."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_slot_reliability()

        # Slot 3 has 100% escalation rate (3 escalated out of 3)
        problematic = result["problematic_slots"]
        slot_3_problems = [p for p in problematic if p["slot_id"] == 3]
        assert len(slot_3_problems) == 1
        assert slot_3_problems[0]["escalation_rate"] == 1.0
        assert slot_3_problems[0]["severity"] == "high"

    def test_generates_recommendations(self, populated_state_dir: Path) -> None:
        """Test that recommendations are generated for problematic slots."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_slot_reliability()

        assert len(result["recommendations"]) > 0
        # Should have recommendation for slot 3
        slot_3_recs = [r for r in result["recommendations"] if r.get("slot_id") == 3]
        assert len(slot_3_recs) >= 1

    def test_overall_reliability_calculated(self, populated_state_dir: Path) -> None:
        """Test overall reliability score is calculated."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_slot_reliability()

        # 5 failures out of 9 slots = ~44% failure rate = ~56% reliability
        assert 0.0 <= result["overall_reliability"] <= 1.0


class TestAnalyzeNudgeEffectiveness:
    """Tests for analyze_nudge_effectiveness() method."""

    def test_empty_directory(self, temp_state_dir: Path) -> None:
        """Test analysis with no nudge state data."""
        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.analyze_nudge_effectiveness()

        assert result["overall_effectiveness"] == 0.0
        assert result["nudge_type_stats"] == {}
        assert result["escalation_patterns"] == []

    def test_calculates_nudge_type_stats(self, populated_state_dir: Path) -> None:
        """Test per-nudge-type statistics are calculated."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_nudge_effectiveness()

        assert "nudge_type_stats" in result
        # Build has 3 nudges: 2 resolved, 1 failed
        if "build" in result["nudge_type_stats"]:
            build_stats = result["nudge_type_stats"]["build"]
            assert build_stats["total_nudges"] == 3
            assert build_stats["resolved_count"] == 2
            assert build_stats["resolution_rate"] == pytest.approx(0.667, rel=0.1)

    def test_tracks_escalation_patterns(self, populated_state_dir: Path) -> None:
        """Test escalation patterns are identified."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_nudge_effectiveness()

        # max_retries appears twice in sample data
        patterns = result["escalation_patterns"]
        max_retries_patterns = [p for p in patterns if p["trigger"] == "max_retries"]
        assert len(max_retries_patterns) >= 1 or len(patterns) > 0

    def test_calculates_timing_analysis(self, populated_state_dir: Path) -> None:
        """Test timing analysis is performed."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_nudge_effectiveness()

        timing = result["timing_analysis"]
        # Should have some timing data from resolved nudges
        assert "avg_resolution_time_hours" in timing
        assert "samples" in timing

    def test_overall_effectiveness(self, populated_state_dir: Path) -> None:
        """Test overall effectiveness is calculated."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.analyze_nudge_effectiveness()

        # 3 resolved out of 7 = ~43% effectiveness
        assert 0.0 <= result["overall_effectiveness"] <= 1.0


class TestDetectFlakyTests:
    """Tests for detect_flaky_tests() method."""

    def test_empty_directory(self, temp_state_dir: Path) -> None:
        """Test detection with no CI retry data."""
        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.detect_flaky_tests()

        assert result == []

    def test_detects_flaky_tests(self, populated_state_dir: Path) -> None:
        """Test flaky test detection."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.detect_flaky_tests()

        # test_auth_login and test_api_rate_limit are flaky (mixed outcomes)
        test_ids = [t["test_id"] for t in result]
        assert "test_auth_login" in test_ids or "test_api_rate_limit" in test_ids

    def test_excludes_consistent_failures(self, populated_state_dir: Path) -> None:
        """Test that consistently failing tests are not flagged as highly flaky."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.detect_flaky_tests()

        # test_db_connection always fails - should have low or no flakiness score
        db_test = [t for t in result if t["test_id"] == "test_db_connection"]
        if db_test:
            # If it appears, it should have low flakiness score
            assert db_test[0]["flakiness_score"] < 0.5

    def test_excludes_stable_tests(self, populated_state_dir: Path) -> None:
        """Test that stable tests are not flagged as flaky."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.detect_flaky_tests()

        # test_simple_math always passes - should not be in flaky list
        stable_tests = [t for t in result if t["test_id"] == "test_simple_math"]
        assert len(stable_tests) == 0

    def test_flaky_test_structure(self, populated_state_dir: Path) -> None:
        """Test that flaky test records have expected structure."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.detect_flaky_tests()

        if result:
            test = result[0]
            assert "test_id" in test
            assert "flakiness_score" in test
            assert "failure_rate" in test
            assert "patterns" in test
            assert "recommendation" in test
            assert "severity" in test

    def test_detects_timeout_pattern(self, populated_state_dir: Path) -> None:
        """Test timeout pattern detection in flaky tests."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.detect_flaky_tests()

        # test_auth_login has timeout failures
        auth_test = [t for t in result if t["test_id"] == "test_auth_login"]
        if auth_test:
            assert "timeout-related" in auth_test[0]["patterns"] or "timeout" in str(
                auth_test[0]["top_failure_reasons"]
            )


class TestGenerateInsights:
    """Tests for generate_insights() method."""

    def test_empty_directory(self, temp_state_dir: Path) -> None:
        """Test insight generation with no state data."""
        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.generate_insights()

        assert "timestamp" in result
        assert "summary" in result
        assert "health_score" in result
        assert result["health_score"] == 1.0  # No issues = perfect health

    def test_generates_complete_insights(self, populated_state_dir: Path) -> None:
        """Test that all insight sections are populated."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.generate_insights()

        assert "timestamp" in result
        assert "summary" in result
        assert "slot_reliability" in result
        assert "nudge_effectiveness" in result
        assert "flaky_tests" in result
        assert "prioritized_actions" in result
        assert "health_score" in result

    def test_summary_statistics(self, populated_state_dir: Path) -> None:
        """Test summary contains expected statistics."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.generate_insights()

        summary = result["summary"]
        assert "total_slots_analyzed" in summary
        assert "problematic_slots" in summary
        assert "nudge_types_analyzed" in summary
        assert "flaky_tests_detected" in summary
        assert "critical_actions" in summary

    def test_health_score_range(self, populated_state_dir: Path) -> None:
        """Test health score is within valid range."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.generate_insights()

        assert 0.0 <= result["health_score"] <= 1.0

    def test_prioritized_actions_sorted(self, populated_state_dir: Path) -> None:
        """Test that prioritized actions are sorted by priority."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        result = analyzer.generate_insights()

        actions = result["prioritized_actions"]
        if len(actions) > 1:
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            priorities = [priority_order.get(a.get("priority", "medium"), 4) for a in actions]
            assert priorities == sorted(priorities)


class TestCacheHandling:
    """Tests for data caching behavior."""

    def test_cache_prevents_multiple_reads(self, populated_state_dir: Path) -> None:
        """Test that data is cached after first read."""
        analyzer = TelemetryAnalyzer(populated_state_dir)

        # First call loads data
        result1 = analyzer.analyze_slot_reliability()
        # Second call should use cached data
        result2 = analyzer.analyze_slot_reliability()

        assert result1 == result2
        assert analyzer._slot_history is not None

    def test_clear_cache(self, populated_state_dir: Path) -> None:
        """Test that clear_cache resets cached data."""
        analyzer = TelemetryAnalyzer(populated_state_dir)

        # Load data
        analyzer.analyze_slot_reliability()
        assert analyzer._slot_history is not None

        # Clear cache
        analyzer.clear_cache()

        assert analyzer._slot_history is None
        assert analyzer._nudge_state is None
        assert analyzer._ci_retry_state is None


class TestExportInsights:
    """Tests for export_insights() method."""

    def test_export_creates_file(self, populated_state_dir: Path, tmp_path: Path) -> None:
        """Test that export creates a JSON file."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        output_file = tmp_path / "insights.json"

        result = analyzer.export_insights(output_file)

        assert result is True
        assert output_file.exists()

    def test_export_valid_json(self, populated_state_dir: Path, tmp_path: Path) -> None:
        """Test that exported file contains valid JSON."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        output_file = tmp_path / "insights.json"

        analyzer.export_insights(output_file)

        with open(output_file) as f:
            data = json.load(f)

        assert "timestamp" in data
        assert "health_score" in data

    def test_export_creates_parent_dirs(self, populated_state_dir: Path, tmp_path: Path) -> None:
        """Test that export creates parent directories if needed."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        output_file = tmp_path / "nested" / "dir" / "insights.json"

        result = analyzer.export_insights(output_file)

        assert result is True
        assert output_file.exists()


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_invalid_json(self, temp_state_dir: Path) -> None:
        """Test handling of invalid JSON files."""
        (temp_state_dir / "slot_history.json").write_text("{ invalid json }")

        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.analyze_slot_reliability()

        # Should return default values, not crash
        assert result["slot_metrics"] == {}

    def test_handles_empty_arrays(self, temp_state_dir: Path) -> None:
        """Test handling of empty arrays in data."""
        (temp_state_dir / "slot_history.json").write_text(json.dumps({"slots": [], "events": []}))
        (temp_state_dir / "nudge_state.json").write_text(json.dumps({"nudges": []}))
        (temp_state_dir / "ci_retry_state.json").write_text(json.dumps({"retries": []}))

        analyzer = TelemetryAnalyzer(temp_state_dir)

        slot_result = analyzer.analyze_slot_reliability()
        nudge_result = analyzer.analyze_nudge_effectiveness()
        flaky_result = analyzer.detect_flaky_tests()

        assert slot_result["slot_metrics"] == {}
        assert nudge_result["nudge_type_stats"] == {}
        assert flaky_result == []

    def test_handles_missing_fields(self, temp_state_dir: Path) -> None:
        """Test handling of missing expected fields."""
        (temp_state_dir / "slot_history.json").write_text(
            json.dumps({"slots": [{"slot_id": 1}, {"slot_id": 2}]})
        )

        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.analyze_slot_reliability()

        # Should not crash
        assert isinstance(result, dict)

    def test_handles_malformed_entries(self, temp_state_dir: Path) -> None:
        """Test handling of malformed entries in arrays."""
        (temp_state_dir / "ci_retry_state.json").write_text(
            json.dumps({"retries": ["not a dict", 123, None, {"test_name": "valid"}]})
        )

        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.detect_flaky_tests()

        # Should not crash, should skip invalid entries
        assert isinstance(result, list)

    def test_below_threshold_not_analyzed(self, temp_state_dir: Path) -> None:
        """Test that slots/tests below MIN_EVENTS_FOR_ANALYSIS threshold are skipped."""
        (temp_state_dir / "slot_history.json").write_text(
            json.dumps(
                {
                    "slots": [
                        {"slot_id": 1, "status": "completed"},
                        {"slot_id": 1, "status": "failed"},
                        # Only 2 events - below threshold of 3
                    ]
                }
            )
        )

        analyzer = TelemetryAnalyzer(temp_state_dir)
        result = analyzer.analyze_slot_reliability()

        # Slot 1 should not appear in metrics (below threshold)
        assert 1 not in result["slot_metrics"]
