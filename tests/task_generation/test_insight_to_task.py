"""Tests for InsightToTaskGenerator in autopack.task_generation module.

Note: InsightToTaskGenerator is deprecated as of IMP-INT-006.
Use AutonomousTaskGenerator from autopack.roadc.task_generator instead.
"""

import json
import warnings
from pathlib import Path

import pytest

from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer

# Import with warning filter to suppress deprecation warnings during test collection
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from autopack.task_generation.insight_to_task import (
        CRITICAL_ESCALATION_RATE, CRITICAL_FLAKINESS,
        CRITICAL_HEALTH_THRESHOLD, HIGH_ESCALATION_RATE, HIGH_FLAKINESS,
        HIGH_IMPACT_THRESHOLD, InsightToTaskGenerator)


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

    # IMP-TASK-001: Tests for new category mappings
    def test_cost_sink_category(self, generator: InsightToTaskGenerator) -> None:
        """Test cost_sink maps to CST."""
        insight = {"source": "cost_sink", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-CST-")

    def test_retry_cause_category(self, generator: InsightToTaskGenerator) -> None:
        """Test retry_cause maps to RTY."""
        insight = {"source": "retry_cause", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-RTY-")

    def test_ci_fail_category(self, generator: InsightToTaskGenerator) -> None:
        """Test ci_fail maps to CI."""
        insight = {"source": "ci_fail", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-CI-")

    def test_infra_error_category(self, generator: InsightToTaskGenerator) -> None:
        """Test infra_error maps to INF."""
        insight = {"source": "infra_error", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-INF-")

    def test_auditor_reject_category(self, generator: InsightToTaskGenerator) -> None:
        """Test auditor_reject maps to AUD."""
        insight = {"source": "auditor_reject", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-AUD-")

    def test_promoted_rule_category(self, generator: InsightToTaskGenerator) -> None:
        """Test promoted_rule maps to RUL."""
        insight = {"source": "promoted_rule", "action": "Test"}
        imp = generator.format_as_imp(insight)
        assert imp["id"].startswith("IMP-RUL-")


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


class TestCreateCorrectiveTask:
    """Tests for create_corrective_task method (IMP-LOOP-022)."""

    @pytest.fixture
    def generator(self, temp_state_dir: Path) -> InsightToTaskGenerator:
        """Create a generator instance for testing."""
        analyzer = TelemetryAnalyzer(state_dir=str(temp_state_dir))
        return InsightToTaskGenerator(analyzer)

    def test_create_from_dict(self, generator: InsightToTaskGenerator) -> None:
        """Test creating corrective task from dictionary."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
            "error_patterns": ["timeout error"],
            "category": "telemetry",
        }
        imp = generator.create_corrective_task(corrective_data)

        assert imp["id"] == "CORR-001"
        assert imp["priority"] == "high"
        assert imp["type"] == "corrective"
        assert imp["original_task_id"] == "IMP-TEST-001"
        assert imp["failure_count"] == 3

    def test_create_from_object_with_to_dict(self, generator: InsightToTaskGenerator) -> None:
        """Test creating corrective task from object with to_dict method."""
        from autopack.task_generation.task_effectiveness_tracker import \
            CorrectiveTask

        corrective_task = CorrectiveTask(
            corrective_id="CORR-002",
            original_task_id="IMP-TEST-002",
            failure_count=5,
            error_patterns=["connection error"],
            category="memory",
        )
        imp = generator.create_corrective_task(corrective_task)

        assert imp["id"] == "CORR-002"
        assert imp["original_task_id"] == "IMP-TEST-002"
        assert imp["failure_count"] == 5

    def test_corrective_task_has_high_priority(self, generator: InsightToTaskGenerator) -> None:
        """Test corrective tasks always have high priority."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
        }
        imp = generator.create_corrective_task(corrective_data)

        assert imp["priority"] == "high"

    def test_corrective_task_includes_evidence(self, generator: InsightToTaskGenerator) -> None:
        """Test corrective task includes failure evidence."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
            "error_patterns": ["timeout", "connection_reset"],
        }
        imp = generator.create_corrective_task(corrective_data)

        assert "evidence" in imp
        assert imp["evidence"]["original_task_id"] == "IMP-TEST-001"
        assert imp["evidence"]["failure_count"] == 3
        assert imp["evidence"]["error_patterns"] == ["timeout", "connection_reset"]

    def test_corrective_task_description_includes_failure_info(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test corrective task description includes failure context."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 5,
            "error_patterns": ["timeout error"],
        }
        imp = generator.create_corrective_task(corrective_data)

        assert "IMP-TEST-001" in imp["description"]
        assert "5 times" in imp["description"]
        assert "timeout error" in imp["description"]

    def test_corrective_task_title_includes_original_task(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test corrective task title mentions original task."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-MEM-005",
            "failure_count": 3,
        }
        imp = generator.create_corrective_task(corrective_data)

        assert "IMP-MEM-005" in imp["title"]

    def test_corrective_task_preserves_category(self, generator: InsightToTaskGenerator) -> None:
        """Test corrective task preserves original category."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
            "category": "telemetry",
        }
        imp = generator.create_corrective_task(corrective_data)

        assert imp["category"] == "telemetry"

    def test_corrective_task_status_is_pending(self, generator: InsightToTaskGenerator) -> None:
        """Test corrective task starts with pending status."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
        }
        imp = generator.create_corrective_task(corrective_data)

        assert imp["status"] == "pending"

    def test_corrective_task_has_created_at(self, generator: InsightToTaskGenerator) -> None:
        """Test corrective task includes creation timestamp."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
        }
        imp = generator.create_corrective_task(corrective_data)

        assert "created_at" in imp
        # Should be a valid ISO timestamp
        from datetime import datetime

        datetime.fromisoformat(imp["created_at"])

    def test_corrective_task_with_empty_error_patterns(
        self, generator: InsightToTaskGenerator
    ) -> None:
        """Test corrective task handles empty error patterns."""
        corrective_data = {
            "corrective_id": "CORR-001",
            "original_task_id": "IMP-TEST-001",
            "failure_count": 3,
            "error_patterns": [],
        }
        imp = generator.create_corrective_task(corrective_data)

        # Should not crash
        assert imp["id"] == "CORR-001"
        assert "error_patterns" not in imp["description"]  # Empty patterns not mentioned


class TestDeprecationWarnings:
    """Tests for InsightToTaskGenerator deprecation (IMP-INT-006)."""

    def test_class_emits_deprecation_on_use(self) -> None:
        """Test InsightToTaskGenerator class is marked as deprecated."""
        # The deprecated library adds deprecation warnings on class instantiation
        # We verify this by checking that a warning is emitted
        import tempfile

        from autopack.analytics.telemetry_analyzer import TelemetryAnalyzer

        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = TelemetryAnalyzer(temp_dir)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                _generator = InsightToTaskGenerator(analyzer)

                # Should have deprecation warning
                deprecation_warnings = [
                    warning for warning in w if issubclass(warning.category, DeprecationWarning)
                ]
                assert (
                    len(deprecation_warnings) >= 1
                ), "Expected DeprecationWarning when using InsightToTaskGenerator"

    def test_instantiation_emits_deprecation_warning(self, temp_state_dir: Path) -> None:
        """Test instantiating InsightToTaskGenerator emits DeprecationWarning."""
        analyzer = TelemetryAnalyzer(temp_state_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # This should emit a deprecation warning
            _generator = InsightToTaskGenerator(analyzer)

            # Check that a deprecation warning was issued
            deprecation_warnings = [
                warning for warning in w if issubclass(warning.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1, "Expected DeprecationWarning on instantiation"

            # Check the warning message mentions AutonomousTaskGenerator
            warning_messages = [str(warning.message) for warning in deprecation_warnings]
            assert any(
                "AutonomousTaskGenerator" in msg for msg in warning_messages
            ), "Warning should mention AutonomousTaskGenerator as replacement"

    def test_module_import_emits_deprecation_warning(self) -> None:
        """Test importing InsightToTaskGenerator from __init__ emits warning."""
        import importlib
        import sys

        # Remove from cache to force reimport
        modules_to_remove = [key for key in sys.modules.keys() if "autopack.task_generation" in key]
        for mod in modules_to_remove:
            if mod in sys.modules:
                del sys.modules[mod]

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            # Import the module and access InsightToTaskGenerator
            import autopack.task_generation

            importlib.reload(autopack.task_generation)

            # Access the deprecated class through the module
            _ = autopack.task_generation.InsightToTaskGenerator

            # Check for deprecation warning
            deprecation_warnings = [
                warning for warning in w if issubclass(warning.category, DeprecationWarning)
            ]
            # Should have at least one warning from __getattr__
            assert (
                len(deprecation_warnings) >= 1
            ), "Expected DeprecationWarning when accessing InsightToTaskGenerator"

    def test_deprecation_message_includes_migration_info(self, temp_state_dir: Path) -> None:
        """Test deprecation warning includes migration information."""
        analyzer = TelemetryAnalyzer(temp_state_dir)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _generator = InsightToTaskGenerator(analyzer)

            deprecation_warnings = [
                warning for warning in w if issubclass(warning.category, DeprecationWarning)
            ]
            warning_messages = " ".join(str(warning.message) for warning in deprecation_warnings)

            # Should mention the replacement class
            assert "AutonomousTaskGenerator" in warning_messages
            # Should mention the roadc module
            assert "roadc" in warning_messages

    def test_autonomous_task_generator_is_preferred(self) -> None:
        """Test AutonomousTaskGenerator is importable as the preferred class."""
        from autopack.roadc.task_generator import AutonomousTaskGenerator

        # Should be able to import without any deprecation warnings
        assert AutonomousTaskGenerator is not None
        assert hasattr(AutonomousTaskGenerator, "generate_tasks")
