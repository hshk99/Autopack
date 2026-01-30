"""Tests for autonomous Phase 1 discovery."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopack.generation.autonomous_discovery import AutonomousDiscovery, DiscoveredIMP


@pytest.fixture
def mock_metrics_db():
    """Create a mock MetricsDatabase instance."""
    return MagicMock()


@pytest.fixture
def mock_failure_analyzer():
    """Create a mock FailureAnalyzer instance."""
    return MagicMock()


@pytest.fixture
def mock_optimization_detector():
    """Create a mock OptimizationDetector instance."""
    return MagicMock()


@pytest.fixture
def discovery(mock_metrics_db, mock_failure_analyzer, mock_optimization_detector):
    """Create an AutonomousDiscovery instance with all mock dependencies."""
    return AutonomousDiscovery(
        metrics_db=mock_metrics_db,
        failure_analyzer=mock_failure_analyzer,
        optimization_detector=mock_optimization_detector,
    )


class TestDiscoveredIMP:
    """Tests for DiscoveredIMP dataclass."""

    def test_imp_creation(self):
        """Test that IMP can be created with all fields."""
        imp = DiscoveredIMP(
            imp_id="IMP-REL-001",
            title="Fix test failures",
            category="reliability",
            priority="high",
            description="Test description",
            files_affected=["src/test.py"],
            discovery_source="failure_pattern",
            confidence=0.8,
        )

        assert imp.imp_id == "IMP-REL-001"
        assert imp.title == "Fix test failures"
        assert imp.category == "reliability"
        assert imp.priority == "high"
        assert imp.description == "Test description"
        assert imp.files_affected == ["src/test.py"]
        assert imp.discovery_source == "failure_pattern"
        assert imp.confidence == 0.8
        assert imp.dependencies == []
        assert imp.discovered_at is not None

    def test_imp_with_dependencies(self):
        """Test that IMP can be created with dependencies."""
        imp = DiscoveredIMP(
            imp_id="IMP-REL-002",
            title="Fix build failures",
            category="reliability",
            priority="medium",
            description="Build fix",
            files_affected=[],
            discovery_source="failure_pattern",
            confidence=0.6,
            dependencies=["IMP-REL-001"],
        )

        assert imp.dependencies == ["IMP-REL-001"]


class TestAutonomousDiscovery:
    """Tests for AutonomousDiscovery class."""

    def test_init_stores_dependencies(self, discovery, mock_metrics_db):
        """Test that initialization stores dependencies."""
        assert discovery.metrics_db is mock_metrics_db

    def test_init_with_no_dependencies(self):
        """Test that discovery can be created without dependencies."""
        discovery = AutonomousDiscovery()
        assert discovery.metrics_db is None
        assert discovery.failure_analyzer is None
        assert discovery.optimization_detector is None

    def test_discover_all_no_dependencies(self):
        """Test discover_all returns empty list when no dependencies."""
        discovery = AutonomousDiscovery()
        imps = discovery.discover_all()
        assert imps == []

    def test_discover_all_combines_sources(
        self, mock_metrics_db, mock_failure_analyzer, mock_optimization_detector
    ):
        """Test discover_all combines IMPs from all sources."""
        # Setup failure analyzer to return patterns
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                }
            ]
        }

        # Setup optimization detector to return suggestions
        mock_suggestion = MagicMock()
        mock_suggestion.category = "slot_utilization"
        mock_suggestion.severity = "high"
        mock_suggestion.description = "Low utilization"
        mock_suggestion.implementation_hint = "Increase parallelism"
        mock_optimization_detector.detect_all.return_value = [mock_suggestion]

        # Setup metrics db to return empty (no anomalies)
        mock_metrics_db.get_daily_metrics.return_value = []

        discovery = AutonomousDiscovery(
            metrics_db=mock_metrics_db,
            failure_analyzer=mock_failure_analyzer,
            optimization_detector=mock_optimization_detector,
        )

        imps = discovery.discover_all()

        # Should have 2 IMPs: 1 from failures, 1 from optimizations
        assert len(imps) == 2


class TestDiscoverFromFailures:
    """Tests for failure pattern discovery."""

    def test_discovers_recurring_failures(self, mock_failure_analyzer):
        """Test that recurring failures without resolution are discovered."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                }
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        imps = discovery._discover_from_failures()

        assert len(imps) == 1
        assert imps[0].category == "reliability"
        assert imps[0].priority == "high"
        assert imps[0].discovery_source == "failure_pattern"
        assert "ci_test_failure" in imps[0].title

    def test_ignores_resolved_failures(self, mock_failure_analyzer):
        """Test that resolved failures are not discovered."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 10,
                    "resolution": "Fixed in PR #123",
                }
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        imps = discovery._discover_from_failures()

        assert len(imps) == 0

    def test_ignores_infrequent_failures(self, mock_failure_analyzer):
        """Test that failures with < 3 occurrences are not discovered."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 2,
                    "resolution": None,
                }
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        imps = discovery._discover_from_failures()

        assert len(imps) == 0

    def test_medium_priority_for_3_4_occurrences(self, mock_failure_analyzer):
        """Test that 3-4 occurrences result in medium priority."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 4,
                    "resolution": None,
                }
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        imps = discovery._discover_from_failures()

        assert len(imps) == 1
        assert imps[0].priority == "medium"


class TestDiscoverFromOptimizations:
    """Tests for optimization suggestion discovery."""

    def test_discovers_optimization_suggestions(self, mock_optimization_detector):
        """Test that optimization suggestions are converted to IMPs."""
        mock_suggestion = MagicMock()
        mock_suggestion.category = "ci_efficiency"
        mock_suggestion.severity = "high"
        mock_suggestion.description = "High CI failure rate"
        mock_suggestion.implementation_hint = "Add pre-commit hooks"
        mock_optimization_detector.detect_all.return_value = [mock_suggestion]

        discovery = AutonomousDiscovery(optimization_detector=mock_optimization_detector)
        imps = discovery._discover_from_optimizations()

        assert len(imps) == 1
        assert imps[0].category == "reliability"
        assert imps[0].priority == "high"
        assert imps[0].discovery_source == "optimization"
        assert imps[0].confidence == 0.7

    def test_low_confidence_for_low_severity(self, mock_optimization_detector):
        """Test that low severity suggestions have lower confidence."""
        mock_suggestion = MagicMock()
        mock_suggestion.category = "slot_utilization"
        mock_suggestion.severity = "low"
        mock_suggestion.description = "Slightly low utilization"
        mock_suggestion.implementation_hint = "Consider more tasks"
        mock_optimization_detector.detect_all.return_value = [mock_suggestion]

        discovery = AutonomousDiscovery(optimization_detector=mock_optimization_detector)
        imps = discovery._discover_from_optimizations()

        assert len(imps) == 1
        assert imps[0].confidence == 0.5


class TestDiscoverFromMetrics:
    """Tests for metrics anomaly discovery."""

    def test_discovers_declining_completion_rate(self, mock_metrics_db):
        """Test that declining task completion is discovered."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 5},
            {"tasks_completed": 5},
            {"tasks_completed": 5},
            {"tasks_completed": 20},
            {"tasks_completed": 20},
            {"tasks_completed": 20},
        ]

        discovery = AutonomousDiscovery(metrics_db=mock_metrics_db)
        imps = discovery._discover_from_metrics()

        assert len(imps) == 1
        assert imps[0].category == "reliability"
        assert imps[0].priority == "high"
        assert imps[0].discovery_source == "metrics"
        assert "declining" in imps[0].title.lower()

    def test_no_imp_when_metrics_stable(self, mock_metrics_db):
        """Test that stable metrics don't trigger IMPs."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 10},
            {"tasks_completed": 10},
            {"tasks_completed": 10},
            {"tasks_completed": 10},
            {"tasks_completed": 10},
            {"tasks_completed": 10},
        ]

        discovery = AutonomousDiscovery(metrics_db=mock_metrics_db)
        imps = discovery._discover_from_metrics()

        assert len(imps) == 0

    def test_no_imp_when_insufficient_metrics(self, mock_metrics_db):
        """Test that insufficient metrics don't trigger IMPs."""
        mock_metrics_db.get_daily_metrics.return_value = [
            {"tasks_completed": 5},
            {"tasks_completed": 5},
        ]

        discovery = AutonomousDiscovery(metrics_db=mock_metrics_db)
        imps = discovery._discover_from_metrics()

        assert len(imps) == 0

    def test_no_imp_when_no_metrics(self, mock_metrics_db):
        """Test that empty metrics don't trigger IMPs."""
        mock_metrics_db.get_daily_metrics.return_value = []

        discovery = AutonomousDiscovery(metrics_db=mock_metrics_db)
        imps = discovery._discover_from_metrics()

        assert len(imps) == 0


class TestCategoryMapping:
    """Tests for category mapping methods."""

    def test_failure_to_category_mapping(self):
        """Test failure type to category mapping."""
        discovery = AutonomousDiscovery()

        assert discovery._map_failure_to_category("ci_test_failure") == "reliability"
        assert discovery._map_failure_to_category("ci_build_failure") == "reliability"
        assert discovery._map_failure_to_category("merge_conflict") == "refactor"
        assert discovery._map_failure_to_category("stagnation") == "performance"
        assert discovery._map_failure_to_category("permission_denied") == "security"
        assert discovery._map_failure_to_category("rate_limit") == "performance"
        assert discovery._map_failure_to_category("lint_failure") == "refactor"
        assert discovery._map_failure_to_category("unknown_type") == "reliability"

    def test_optimization_to_category_mapping(self):
        """Test optimization category to IMP category mapping."""
        discovery = AutonomousDiscovery()

        assert discovery._map_optimization_to_category("slot_utilization") == "performance"
        assert discovery._map_optimization_to_category("ci_efficiency") == "reliability"
        assert discovery._map_optimization_to_category("stagnation") == "reliability"
        assert discovery._map_optimization_to_category("pr_merge_time") == "performance"
        assert discovery._map_optimization_to_category("unknown") == "performance"


class TestImpIdGeneration:
    """Tests for IMP ID generation."""

    def test_generates_unique_ids(self):
        """Test that IMP IDs are unique and sequential."""
        discovery = AutonomousDiscovery()

        id1 = discovery._generate_imp_id("reliability")
        id2 = discovery._generate_imp_id("reliability")
        id3 = discovery._generate_imp_id("performance")

        assert id1 == "IMP-REL-001"
        assert id2 == "IMP-REL-002"
        assert id3 == "IMP-PERF-001"

    def test_uses_category_prefix(self):
        """Test that IMP IDs use correct category prefixes."""
        discovery = AutonomousDiscovery()

        assert discovery._generate_imp_id("security").startswith("IMP-SEC-")
        assert discovery._generate_imp_id("performance").startswith("IMP-PERF-")
        assert discovery._generate_imp_id("feature").startswith("IMP-FEAT-")
        assert discovery._generate_imp_id("refactor").startswith("IMP-REF-")

    def test_unknown_category_uses_imp_prefix(self):
        """Test that unknown categories use IMP prefix."""
        discovery = AutonomousDiscovery()

        imp_id = discovery._generate_imp_id("unknown_category")
        assert imp_id.startswith("IMP-IMP-")


class TestExportToJson:
    """Tests for JSON export functionality."""

    def test_exports_discovered_imps(self, mock_failure_analyzer):
        """Test that discovered IMPs are exported to JSON."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                }
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        discovery.discover_all()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "imps.json"
            discovery.export_to_json(str(output_path))

            assert output_path.exists()
            with open(output_path) as f:
                data = json.load(f)

            assert data["total_imps"] == 1
            assert len(data["imps"]) == 1
            assert data["imps"][0]["imp_id"] == "IMP-REL-001"
            assert "discovered_at" in data

    def test_exports_empty_list_when_no_discoveries(self):
        """Test that empty list is exported when no discoveries."""
        discovery = AutonomousDiscovery()
        discovery.discover_all()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "imps.json"
            discovery.export_to_json(str(output_path))

            with open(output_path) as f:
                data = json.load(f)

            assert data["total_imps"] == 0
            assert data["imps"] == []


class TestGetSummary:
    """Tests for summary generation."""

    def test_summary_no_discoveries(self):
        """Test summary when no improvements discovered."""
        discovery = AutonomousDiscovery()

        summary = discovery.get_summary()

        assert "No improvements discovered" in summary

    def test_summary_with_discoveries(self, mock_failure_analyzer):
        """Test summary when improvements are discovered."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 5,
                    "resolution": None,
                },
                {
                    "pattern_hash": "def456",
                    "failure_type": "lint_failure",
                    "occurrence_count": 3,
                    "resolution": None,
                },
            ]
        }

        discovery = AutonomousDiscovery(failure_analyzer=mock_failure_analyzer)
        discovery.discover_all()

        summary = discovery.get_summary()

        assert "Discovered 2 potential improvements" in summary
        assert "HIGH" in summary
        assert "MEDIUM" in summary
        assert "IMP-REL-001" in summary
        assert "IMP-REF-001" in summary

    def test_summary_groups_by_priority(self, mock_failure_analyzer, mock_optimization_detector):
        """Test that summary groups IMPs by priority."""
        mock_failure_analyzer.get_failure_statistics.return_value = {
            "top_patterns": [
                {
                    "pattern_hash": "abc123",
                    "failure_type": "ci_test_failure",
                    "occurrence_count": 10,  # high priority
                    "resolution": None,
                }
            ]
        }

        mock_suggestion = MagicMock()
        mock_suggestion.category = "slot_utilization"
        mock_suggestion.severity = "medium"
        mock_suggestion.description = "Test"
        mock_suggestion.implementation_hint = "Test"
        mock_optimization_detector.detect_all.return_value = [mock_suggestion]

        discovery = AutonomousDiscovery(
            failure_analyzer=mock_failure_analyzer,
            optimization_detector=mock_optimization_detector,
        )
        discovery.discover_all()

        summary = discovery.get_summary()

        # Verify priority sections appear in order
        high_pos = summary.find("HIGH")
        medium_pos = summary.find("MEDIUM")
        assert high_pos < medium_pos
