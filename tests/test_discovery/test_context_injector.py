"""Tests for context injector module."""

# CRITICAL: Ensure src is on sys.path before any imports
import sys
from pathlib import Path

_src_path = str(Path(__file__).resolve().parent.parent.parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

import json
import tempfile

import pytest

from discovery import ContextInjector, DiscoveryContext


@pytest.fixture
def temp_telemetry_file():
    """Create a temporary telemetry events file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(
            {
                "events": [
                    {"event_type": "error", "payload": {"error_type": "lint_failure"}},
                    {"event_type": "error", "payload": {"error_type": "lint_failure"}},
                    {"event_type": "error", "payload": {"error_type": "lint_failure"}},
                    {"event_type": "error", "payload": {"error_type": "type_error"}},
                    {"event_type": "success", "payload": {}},
                ]
            },
            f,
        )
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_decisions_file():
    """Create a temporary decisions log file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(
            {
                "decisions": [
                    {
                        "decision_type": "retry",
                        "chosen_option": "exponential_backoff",
                        "outcome": "success",
                        "context": {"phase_id": "phase1"},
                    },
                    {
                        "decision_type": "escalation",
                        "chosen_option": "notify_human",
                        "outcome": "success",
                        "context": {"phase_id": "phase2"},
                    },
                    {
                        "decision_type": "optimization",
                        "chosen_option": "parallel_execution",
                        "outcome": "failure",
                        "reasoning": "Resource contention",
                        "context": {"phase_id": "phase1"},
                    },
                ]
            },
            f,
        )
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_output_file():
    """Create a temporary output file path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        temp_path = f.name
    yield temp_path
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def context_injector(temp_telemetry_file, temp_decisions_file):
    """Create a ContextInjector instance with temp files."""
    return ContextInjector(telemetry_path=temp_telemetry_file, decisions_path=temp_decisions_file)


class TestDiscoveryContext:
    """Tests for DiscoveryContext dataclass."""

    def test_discovery_context_creation(self):
        """Test that DiscoveryContext can be created with all fields."""
        context = DiscoveryContext(
            recurring_issues=[{"type": "lint_failure", "occurrences": 5}],
            successful_patterns=[{"decision_type": "retry"}],
            high_value_categories=["TEL", "LOG"],
            failed_approaches=[{"approach": "parallel", "reason": "contention"}],
            performance_insights={"avg_phase_duration_seconds": 120},
        )

        assert len(context.recurring_issues) == 1
        assert context.recurring_issues[0]["type"] == "lint_failure"
        assert len(context.high_value_categories) == 2
        assert context.performance_insights["avg_phase_duration_seconds"] == 120

    def test_discovery_context_empty(self):
        """Test that DiscoveryContext can be created empty."""
        context = DiscoveryContext(
            recurring_issues=[],
            successful_patterns=[],
            high_value_categories=[],
            failed_approaches=[],
            performance_insights={},
        )

        assert len(context.recurring_issues) == 0
        assert len(context.successful_patterns) == 0


class TestContextInjector:
    """Tests for ContextInjector class."""

    def test_init_with_paths(self, temp_telemetry_file, temp_decisions_file):
        """Test that ContextInjector initializes with given paths."""
        injector = ContextInjector(
            telemetry_path=temp_telemetry_file, decisions_path=temp_decisions_file
        )

        assert injector.telemetry_path == Path(temp_telemetry_file)
        assert injector.decisions_path == Path(temp_decisions_file)

    def test_init_with_default_paths(self):
        """Test that ContextInjector uses default paths."""
        injector = ContextInjector()

        assert injector.telemetry_path == Path("telemetry_events.json")
        assert injector.decisions_path == Path("decisions_log.json")

    def test_gather_context(self, context_injector):
        """Test gathering context from telemetry files."""
        context = context_injector.gather_context(lookback_days=30)

        assert isinstance(context, DiscoveryContext)
        assert isinstance(context.recurring_issues, list)
        assert isinstance(context.successful_patterns, list)
        assert isinstance(context.high_value_categories, list)
        assert isinstance(context.failed_approaches, list)
        assert isinstance(context.performance_insights, dict)

    def test_find_recurring_issues(self, context_injector):
        """Test finding recurring issues from telemetry."""
        context = context_injector.gather_context()

        # lint_failure appears 3 times, should be included
        assert any(issue["type"] == "lint_failure" for issue in context.recurring_issues)

        # type_error appears only once, should not be included
        assert not any(issue["type"] == "type_error" for issue in context.recurring_issues)

    def test_find_recurring_issues_counts(self, context_injector):
        """Test that recurring issues include correct occurrence counts."""
        context = context_injector.gather_context()

        lint_issue = next(
            (i for i in context.recurring_issues if i["type"] == "lint_failure"), None
        )
        assert lint_issue is not None
        assert lint_issue["occurrences"] == 3
        assert "recommendation" in lint_issue

    def test_find_successful_patterns(self, context_injector):
        """Test finding successful patterns from decisions."""
        context = context_injector.gather_context()

        # Should find decisions with outcome="success"
        assert len(context.successful_patterns) == 2
        assert any(p["decision_type"] == "retry" for p in context.successful_patterns)
        assert any(p["decision_type"] == "escalation" for p in context.successful_patterns)

    def test_find_failed_approaches(self, context_injector):
        """Test finding failed approaches from decisions."""
        context = context_injector.gather_context()

        # Should find decisions with outcome="failure"
        assert len(context.failed_approaches) == 1
        assert context.failed_approaches[0]["approach"] == "parallel_execution"
        assert context.failed_approaches[0]["reason"] == "Resource contention"

    def test_high_value_categories(self, context_injector):
        """Test identifying high-value categories."""
        context = context_injector.gather_context()

        # Default high-value categories
        assert "TEL" in context.high_value_categories
        assert "LOG" in context.high_value_categories
        assert "ESC" in context.high_value_categories
        assert "PERF" in context.high_value_categories

    def test_performance_insights(self, context_injector):
        """Test getting performance insights."""
        context = context_injector.gather_context()

        assert "avg_phase_duration_seconds" in context.performance_insights
        assert "ci_success_rate" in context.performance_insights
        assert "bottleneck_components" in context.performance_insights

    def test_inject_into_phase1(self, context_injector, temp_output_file):
        """Test injecting context into a file for Phase 1."""
        context = context_injector.gather_context()
        context_injector.inject_into_phase1(context, temp_output_file)

        # Verify file was created
        assert Path(temp_output_file).exists()

        # Verify file contents
        with open(temp_output_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "generated_at" in data
        assert "recurring_issues" in data
        assert "successful_patterns" in data
        assert "high_value_categories" in data
        assert "failed_approaches" in data
        assert "performance_insights" in data
        assert "recommendations" in data

    def test_inject_creates_parent_directory(self, context_injector):
        """Test that inject_into_phase1 creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "subdir" / "context.json"
            context = context_injector.gather_context()
            context_injector.inject_into_phase1(context, str(nested_path))

            assert nested_path.exists()

    def test_generate_recommendations(self, context_injector, temp_output_file):
        """Test that recommendations are generated."""
        context = context_injector.gather_context()
        context_injector.inject_into_phase1(context, temp_output_file)

        with open(temp_output_file, encoding="utf-8") as f:
            data = json.load(f)

        recommendations = data["recommendations"]
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        # Should have recommendations about recurring issues, categories, and failed approaches
        assert any("recurring" in r.lower() for r in recommendations)
        assert any("categories" in r.lower() for r in recommendations)
        assert any("avoid" in r.lower() for r in recommendations)


class TestContextInjectorMissingFiles:
    """Tests for ContextInjector when files are missing."""

    def test_missing_telemetry_file(self, temp_decisions_file):
        """Test behavior when telemetry file is missing."""
        injector = ContextInjector(
            telemetry_path="nonexistent.json", decisions_path=temp_decisions_file
        )
        context = injector.gather_context()

        # Should return empty recurring issues
        assert context.recurring_issues == []

    def test_missing_decisions_file(self, temp_telemetry_file):
        """Test behavior when decisions file is missing."""
        injector = ContextInjector(
            telemetry_path=temp_telemetry_file, decisions_path="nonexistent.json"
        )
        context = injector.gather_context()

        # Should return empty patterns and failed approaches
        assert context.successful_patterns == []
        assert context.failed_approaches == []

    def test_both_files_missing(self):
        """Test behavior when both files are missing."""
        injector = ContextInjector(
            telemetry_path="nonexistent1.json", decisions_path="nonexistent2.json"
        )
        context = injector.gather_context()

        # Should return context with empty data
        assert context.recurring_issues == []
        assert context.successful_patterns == []
        assert context.failed_approaches == []
        # But should still have default high-value categories
        assert len(context.high_value_categories) > 0
