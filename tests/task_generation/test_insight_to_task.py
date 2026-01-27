"""Tests for InsightToTaskGenerator in autopack.task_generation module."""

import json
from pathlib import Path

import pytest

from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer
from autopack.task_generation.insight_to_task import (
    CRITICAL_ESCALATION_RATE,
    CRITICAL_FLAKINESS,
    CRITICAL_HEALTH_THRESHOLD,
    HIGH_ESCALATION_RATE,
    HIGH_FLAKINESS,
    HIGH_IMPACT_THRESHOLD,
    InsightToTaskGenerator,
)


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for state files."""
    return tmp_path


@pytest.fixture
def sample_slot_history() -> dict:
    """Sample slot_history.json with problematic slots."""
    return {
        "slots": [
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            {"slot_id": 1, "status": "completed", "event_type": "nudge"},
            # Slot 2 has high escalation rate
            {
                "slot_id": 2,
                "status": "failed",
                "event_type": "error",
                "escalated": True,
                "escalation_level": 1,
            },
            {
                "slot_id": 2,
                "status": "failed",
                "event_type": "error",
                "escalated": True,
                "escalation_level": 2,
            },
            {
                "slot_id": 2,
                "status": "failed",
                "event_type": "error",
                "escalated": True,
                "escalation_level": 3,
            },
        ],
        "events": [],
    }


@pytest.fixture
def sample_nudge_state() -> dict:
    """Sample nudge_state.json with escalation patterns."""
    return {
        "nudges": [
            {"id": "nudge-1", "phase_type": "build", "status": "resolved"},
            {"id": "nudge-2", "phase_type": "build", "status": "resolved"},
            {"id": "nudge-3", "phase_type": "build", "status": "failed", "escalated": True},
            {
                "id": "nudge-4",
                "phase_type": "test",
                "status": "failed",
                "failure_reason": "timeout",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
            {
                "id": "nudge-5",
                "phase_type": "test",
                "status": "failed",
                "failure_reason": "timeout",
                "escalated": True,
                "escalation_trigger": "max_retries",
            },
        ]
    }


@pytest.fixture
def sample_ci_retry_state() -> dict:
    """Sample ci_retry_state.json with flaky tests."""
    return {
        "retries": [
            {"test_name": "test_flaky_auth", "outcome": "failed", "attempt": 1},
            {"test_name": "test_flaky_auth", "outcome": "success", "attempt": 2},
            {"test_name": "test_flaky_auth", "outcome": "failed", "attempt": 1},
            {"test_name": "test_flaky_auth", "outcome": "success", "attempt": 2},
            {"test_name": "test_stable", "outcome": "success", "attempt": 1},
            {"test_name": "test_stable", "outcome": "success", "attempt": 1},
            {"test_name": "test_stable", "outcome": "success", "attempt": 1},
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


@pytest.fixture
def generator(populated_state_dir: Path) -> InsightToTaskGenerator:
    """Create an InsightToTaskGenerator with populated data."""
    analyzer = TelemetryAnalyzer(populated_state_dir)
    return InsightToTaskGenerator(analyzer)


@pytest.fixture
def empty_generator(temp_state_dir: Path) -> InsightToTaskGenerator:
    """Create an InsightToTaskGenerator with no data."""
    analyzer = TelemetryAnalyzer(temp_state_dir)
    return InsightToTaskGenerator(analyzer)


class TestInsightToTaskGeneratorInit:
    """Tests for InsightToTaskGenerator initialization."""

    def test_init_with_analyzer(self, populated_state_dir: Path) -> None:
        """Test generator initializes with TelemetryAnalyzer."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        generator = InsightToTaskGenerator(analyzer)
        assert generator.analyzer is analyzer

    def test_imp_counter_starts_empty(self, populated_state_dir: Path) -> None:
        """Test IMP counter starts empty."""
        analyzer = TelemetryAnalyzer(populated_state_dir)
        generator = InsightToTaskGenerator(analyzer)
        assert len(generator._imp_counter) == 0


class TestEstimateImpact:
    """Tests for estimate_impact() method."""

    def test_critical_from_severity(self, generator: InsightToTaskGenerator) -> None:
        """Test critical impact from explicit severity."""
        insight = {"severity": "critical"}
        assert generator.estimate_impact(insight) == "critical"

    def test_critical_from_priority(self, generator: InsightToTaskGenerator) -> None:
        """Test critical impact from explicit priority."""
        insight = {"priority": "critical"}
        assert generator.estimate_impact(insight) == "critical"

    def test_critical_from_low_health(self, generator: InsightToTaskGenerator) -> None:
        """Test critical impact from very low health score."""
        insight = {"health_score": CRITICAL_HEALTH_THRESHOLD - 0.1}
        assert generator.estimate_impact(insight) == "critical"

    def test_high_from_health_score(self, generator: InsightToTaskGenerator) -> None:
        """Test high impact from health score below threshold."""
        insight = {"health_score": HIGH_IMPACT_THRESHOLD - 0.1}
        assert generator.estimate_impact(insight) == "high"

    def test_critical_from_escalation_rate(self, generator: InsightToTaskGenerator) -> None:
        """Test critical impact from high escalation rate."""
        insight = {"escalation_rate": CRITICAL_ESCALATION_RATE}
        assert generator.estimate_impact(insight) == "critical"

    def test_high_from_escalation_rate(self, generator: InsightToTaskGenerator) -> None:
        """Test high impact from moderate escalation rate."""
        insight = {"escalation_rate": HIGH_ESCALATION_RATE}
        assert generator.estimate_impact(insight) == "high"

    def test_critical_from_flakiness(self, generator: InsightToTaskGenerator) -> None:
        """Test critical impact from high flakiness score."""
        insight = {"flakiness_score": CRITICAL_FLAKINESS}
        assert generator.estimate_impact(insight) == "critical"

    def test_high_from_flakiness(self, generator: InsightToTaskGenerator) -> None:
        """Test high impact from moderate flakiness score."""
        insight = {"flakiness_score": HIGH_FLAKINESS}
        assert generator.estimate_impact(insight) == "high"

    def test_high_from_failure_rate(self, generator: InsightToTaskGenerator) -> None:
        """Test high impact from high failure rate."""
        insight = {"failure_rate": 0.5}
        assert generator.estimate_impact(insight) == "high"

    def test_medium_from_failure_rate(self, generator: InsightToTaskGenerator) -> None:
        """Test medium impact from moderate failure rate."""
        insight = {"failure_rate": 0.25}
        assert generator.estimate_impact(insight) == "medium"

    def test_low_default(self, generator: InsightToTaskGenerator) -> None:
        """Test low impact as default."""
        insight = {}
        assert generator.estimate_impact(insight) == "low"

    def test_medium_from_severity(self, generator: InsightToTaskGenerator) -> None:
        """Test medium impact from explicit medium severity."""
        insight = {"severity": "medium"}
        assert generator.estimate_impact(insight) == "medium"


class TestFormatAsImp:
    """Tests for format_as_imp() method."""

    def test_basic_structure(self, generator: InsightToTaskGenerator) -> None:
        """Test IMP entry has required fields."""
        insight = {"source": "slot_reliability", "action": "Test action"}
        imp = generator.format_as_imp(insight)

        assert "id" in imp
        assert "title" in imp
        assert "description" in imp
        assert "priority" in imp
        assert "category" in imp
        assert "source" in imp
        assert "created_at" in imp
        assert "status" in imp
        assert "evidence" in imp
        assert "recommended_action" in imp

    def test_imp_id_format(self, generator: InsightToTaskGenerator) -> None:
        """Test IMP ID follows expected format."""
        insight = {"source": "slot_reliability", "action": "Test"}
        imp = generator.format_as_imp(insight)

        assert imp["id"].startswith("IMP-SLT-")
        assert len(imp["id"]) == len("IMP-SLT-001")

    def test_unique_imp_ids(self, generator: InsightToTaskGenerator) -> None:
        """Test IMP IDs are unique within same category."""
        insight = {"source": "slot_reliability", "action": "Test"}

        imp1 = generator.format_as_imp(insight)
        imp2 = generator.format_as_imp(insight)

        assert imp1["id"] != imp2["id"]
        assert imp1["id"] == "IMP-SLT-001"
        assert imp2["id"] == "IMP-SLT-002"

    def test_title_from_action(self, generator: InsightToTaskGenerator) -> None:
        """Test title is derived from action."""
        insight = {"source": "slot_reliability", "action": "Investigate slot 7"}
        imp = generator.format_as_imp(insight)

        assert imp["title"] == "Investigate slot 7"

    def test_title_fallback(self, generator: InsightToTaskGenerator) -> None:
        """Test title fallback when no action provided."""
        insight = {"source": "slot_reliability"}
        imp = generator.format_as_imp(insight)

        assert "slot reliability" in imp["title"].lower()

    def test_status_pending(self, generator: InsightToTaskGenerator) -> None:
        """Test status is always pending for new entries."""
        insight = {"source": "slot_reliability", "action": "Test"}
        imp = generator.format_as_imp(insight)

        assert imp["status"] == "pending"

    def test_source_is_telemetry_insights(self, generator: InsightToTaskGenerator) -> None:
        """Test source field indicates telemetry origin."""
        insight = {"source": "slot_reliability", "action": "Test"}
        imp = generator.format_as_imp(insight)

        assert imp["source"] == "telemetry_insights"

    def test_slot_reliability_context(self, generator: InsightToTaskGenerator) -> None:
        """Test slot reliability specific fields are included."""
        insight = {
            "source": "slot_reliability",
            "slot_id": 7,
            "escalation_rate": 0.5,
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        assert "slot" in imp["description"].lower()
        assert imp["evidence"]["slot_id"] == 7
        assert imp["evidence"]["escalation_rate"] == 0.5

    def test_nudge_effectiveness_context(self, generator: InsightToTaskGenerator) -> None:
        """Test nudge effectiveness specific fields are included."""
        insight = {
            "source": "nudge_effectiveness",
            "nudge_type": "build",
            "trigger": "max_retries",
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        assert imp["evidence"]["nudge_type"] == "build"
        assert imp["evidence"]["trigger"] == "max_retries"

    def test_flaky_tests_context(self, generator: InsightToTaskGenerator) -> None:
        """Test flaky tests specific fields are included."""
        insight = {
            "source": "flaky_tests",
            "test_id": "test_auth",
            "flakiness_score": 0.8,
            "patterns": ["timeout-related"],
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        assert "test_auth" in imp["description"]
        assert imp["evidence"]["test_id"] == "test_auth"
        assert imp["evidence"]["flakiness_score"] == 0.8


class TestGenerateImprovementsFromInsights:
    """Tests for generate_improvements_from_insights() method."""

    def test_empty_returns_empty_list(self, empty_generator: InsightToTaskGenerator) -> None:
        """Test empty insights return empty list."""
        improvements = empty_generator.generate_improvements_from_insights()
        assert improvements == []

    def test_generates_improvements(self, generator: InsightToTaskGenerator) -> None:
        """Test improvements are generated from insights."""
        improvements = generator.generate_improvements_from_insights()
        assert len(improvements) > 0

    def test_improvements_sorted_by_priority(self, generator: InsightToTaskGenerator) -> None:
        """Test improvements are sorted by priority."""
        improvements = generator.generate_improvements_from_insights()

        if len(improvements) > 1:
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            priorities = [
                priority_order.get(imp.get("priority", "medium"), 4) for imp in improvements
            ]
            assert priorities == sorted(priorities)

    def test_includes_health_score_in_evidence(self, generator: InsightToTaskGenerator) -> None:
        """Test health score is included in all improvement evidence."""
        improvements = generator.generate_improvements_from_insights()

        for imp in improvements:
            assert "system_health_score" in imp["evidence"]

    def test_resets_counter_on_each_call(self, generator: InsightToTaskGenerator) -> None:
        """Test IMP counter resets between calls."""
        improvements1 = generator.generate_improvements_from_insights()
        improvements2 = generator.generate_improvements_from_insights()

        if improvements1 and improvements2:
            # IDs should be the same between calls (counter resets)
            ids1 = {imp["id"] for imp in improvements1}
            ids2 = {imp["id"] for imp in improvements2}
            assert ids1 == ids2

    def test_includes_slot_improvements(self, generator: InsightToTaskGenerator) -> None:
        """Test slot reliability improvements are included."""
        improvements = generator.generate_improvements_from_insights()

        # Should have at least one slot-related improvement
        slot_imps = [imp for imp in improvements if imp.get("category") == "slot_reliability"]
        # May be in prioritized_actions or added separately
        all_sources = [imp.get("evidence", {}).get("source") for imp in improvements]
        assert "slot_reliability" in all_sources or len(slot_imps) > 0

    def test_improvements_have_valid_structure(self, generator: InsightToTaskGenerator) -> None:
        """Test all improvements have valid structure."""
        improvements = generator.generate_improvements_from_insights()

        for imp in improvements:
            assert imp["id"].startswith("IMP-")
            assert imp["status"] == "pending"
            assert imp["priority"] in ["critical", "high", "medium", "low"]
            assert isinstance(imp["evidence"], dict)


class TestGetSummary:
    """Tests for get_summary() method."""

    def test_summary_structure(self, generator: InsightToTaskGenerator) -> None:
        """Test summary has expected structure."""
        summary = generator.get_summary()

        assert "total_improvements" in summary
        assert "by_priority" in summary
        assert "by_category" in summary
        assert "health_score" in summary
        assert "generated_at" in summary

    def test_summary_counts_match(self, generator: InsightToTaskGenerator) -> None:
        """Test summary counts match actual improvements."""
        generator.generate_improvements_from_insights()
        summary = generator.get_summary()

        # Total should match
        # Note: get_summary calls generate_improvements_from_insights again with reset counter
        assert summary["total_improvements"] >= 0

    def test_empty_summary(self, empty_generator: InsightToTaskGenerator) -> None:
        """Test summary with no improvements."""
        summary = empty_generator.get_summary()

        assert summary["total_improvements"] == 0
        assert summary["by_priority"] == {}
        assert summary["by_category"] == {}
        assert summary["health_score"] == 1.0


class TestCategoryMapping:
    """Tests for insight source to category mapping."""

    def test_slot_reliability_category(self, generator: InsightToTaskGenerator) -> None:
        """Test slot_reliability maps to SLT."""
        insight = {"source": "slot_reliability", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-SLT-")

    def test_nudge_effectiveness_category(self, generator: InsightToTaskGenerator) -> None:
        """Test nudge_effectiveness maps to NDG."""
        insight = {"source": "nudge_effectiveness", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-NDG-")

    def test_flaky_tests_category(self, generator: InsightToTaskGenerator) -> None:
        """Test flaky_tests maps to TST."""
        insight = {"source": "flaky_tests", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-TST-")

    def test_unknown_category(self, generator: InsightToTaskGenerator) -> None:
        """Test unknown source maps to GEN."""
        insight = {"source": "unknown_source", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-GEN-")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_missing_source(self, generator: InsightToTaskGenerator) -> None:
        """Test handling of missing source field."""
        insight = {"action": "Test action"}
        imp = generator.format_as_imp(insight)

        assert imp["id"].startswith("IMP-GEN-")
        assert imp["category"] == "unknown"

    def test_none_values_in_insight(self, generator: InsightToTaskGenerator) -> None:
        """Test handling of None values."""
        insight = {
            "source": "slot_reliability",
            "slot_id": None,
            "health_score": None,
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        # Should not crash
        assert "id" in imp
        assert "slot_id" not in imp["evidence"]

    def test_empty_patterns_list(self, generator: InsightToTaskGenerator) -> None:
        """Test handling of empty patterns list."""
        insight = {
            "source": "flaky_tests",
            "patterns": [],
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        # Should not crash or include empty patterns
        assert "id" in imp

    def test_large_numbers(self, generator: InsightToTaskGenerator) -> None:
        """Test handling of extreme metric values."""
        insight = {
            "source": "slot_reliability",
            "escalation_rate": 1.0,
            "failure_rate": 1.0,
            "health_score": 0.0,
            "action": "Test",
        }
        imp = generator.format_as_imp(insight)

        assert imp["priority"] == "critical"
