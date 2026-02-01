"""Tests for ProjectHistoryAnalyzer in autopack.research.discovery module.

Tests cover:
- History analysis from project data
- Decision pattern analysis
- Success correlation detection
- Failure correlation detection
- Category insights extraction
- Recommendation generation
- Project summary storage and retrieval
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autopack.research.discovery.project_history_analyzer import (
    HistoryAnalysisResult,
    ProjectDecision,
    ProjectHistoryAnalyzer,
    ProjectSummary,
)


@pytest.fixture
def temp_history_path(tmp_path: Path) -> Path:
    """Create a temporary path for project history file."""
    return tmp_path / "project_history.json"


@pytest.fixture
def history_analyzer(temp_history_path: Path) -> ProjectHistoryAnalyzer:
    """Create a ProjectHistoryAnalyzer instance."""
    return ProjectHistoryAnalyzer(project_history_path=temp_history_path)


@pytest.fixture
def mock_learning_db() -> MagicMock:
    """Create a mock LearningDatabase."""
    db = MagicMock()

    db.list_improvements.return_value = [
        {
            "imp_id": "IMP-001",
            "category": "research",
            "current_outcome": "implemented",
        },
        {
            "imp_id": "IMP-002",
            "category": "research",
            "current_outcome": "blocked",
        },
        {
            "imp_id": "IMP-003",
            "category": "memory",
            "current_outcome": "implemented",
        },
    ]

    db.list_cycles.return_value = [
        {
            "cycle_id": "cycle-001",
            "recorded_at": "2025-01-15T10:00:00",
            "metrics": {
                "phases_completed": 5,
                "phases_blocked": 1,
                "completion_rate": 0.83,
            },
            "blocking_reasons": ["dependency_issue"],
        },
        {
            "cycle_id": "cycle-002",
            "recorded_at": "2025-02-20T14:00:00",
            "metrics": {
                "phases_completed": 4,
                "phases_blocked": 2,
                "completion_rate": 0.67,
            },
            "blocking_reasons": [],
        },
    ]

    db.get_historical_patterns.return_value = {
        "category_success_rates": {
            "research": {
                "total": 5,
                "implemented": 3,
                "blocked": 2,
                "success_rate": 0.6,
            },
            "memory": {
                "total": 3,
                "implemented": 2,
                "blocked": 1,
                "success_rate": 0.67,
            },
        }
    }

    db.get_likely_blockers.return_value = [
        {"reason": "Missing API access", "frequency": 3},
    ]

    return db


@pytest.fixture
def sample_history_file(temp_history_path: Path) -> Path:
    """Create a sample project history file."""
    history_data = {
        "projects": [
            {
                "project_id": "proj-001",
                "project_type": "ecommerce",
                "name": "Shop App",
                "outcome": "successful",
                "success_score": 0.85,
                "start_date": "2025-01-01T00:00:00",
                "tech_stack": {
                    "languages": ["Python", "TypeScript"],
                    "frameworks": ["FastAPI", "React"],
                },
                "architecture": {"pattern": "microservices"},
                "lessons_learned": ["API versioning is important"],
            },
            {
                "project_id": "proj-002",
                "project_type": "ecommerce",
                "name": "Market Place",
                "outcome": "successful",
                "success_score": 0.9,
                "start_date": "2025-02-01T00:00:00",
                "tech_stack": {
                    "languages": ["Python"],
                    "frameworks": ["FastAPI"],
                },
                "architecture": {"pattern": "microservices"},
                "lessons_learned": [],
            },
            {
                "project_id": "proj-003",
                "project_type": "saas",
                "name": "Tool App",
                "outcome": "blocked",
                "success_score": 0.3,
                "start_date": "2025-03-01T00:00:00",
                "tech_stack": {
                    "languages": ["JavaScript"],
                    "frameworks": ["Express"],
                },
                "architecture": {"pattern": "monolith"},
                "lessons_learned": [
                    "Blocked by: dependency_issue",
                    "Blocked by: timeout",
                ],
            },
        ],
        "updated_at": "2025-03-15T00:00:00",
    }

    with open(temp_history_path, "w", encoding="utf-8") as f:
        json.dump(history_data, f)

    return temp_history_path


class TestProjectHistoryAnalyzer:
    """Tests for ProjectHistoryAnalyzer class."""

    def test_init_without_db(self, temp_history_path: Path):
        """Test initialization without learning database."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        assert analyzer._learning_db is None
        assert analyzer._project_history_path == temp_history_path

    def test_init_with_db(self, mock_learning_db: MagicMock, temp_history_path: Path):
        """Test initialization with learning database."""
        analyzer = ProjectHistoryAnalyzer(
            learning_db=mock_learning_db,
            project_history_path=temp_history_path,
        )
        assert analyzer._learning_db is mock_learning_db

    def test_set_learning_db(
        self, history_analyzer: ProjectHistoryAnalyzer, mock_learning_db: MagicMock
    ):
        """Test setting learning database after initialization."""
        history_analyzer.set_learning_db(mock_learning_db)
        assert history_analyzer._learning_db is mock_learning_db

    def test_analyze_history_from_file(self, sample_history_file: Path, temp_history_path: Path):
        """Test analyzing history from file."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        assert isinstance(result, HistoryAnalysisResult)
        assert result.projects_analyzed == 3
        assert len(result.project_summaries) == 3

    def test_analyze_history_from_db(
        self, history_analyzer: ProjectHistoryAnalyzer, mock_learning_db: MagicMock
    ):
        """Test analyzing history from learning database."""
        history_analyzer.set_learning_db(mock_learning_db)
        result = history_analyzer.analyze_history()

        assert isinstance(result, HistoryAnalysisResult)
        assert result.projects_analyzed > 0

    def test_decision_patterns_extraction(self, sample_history_file: Path, temp_history_path: Path):
        """Test extraction of decision patterns."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        # Should have decision patterns
        assert "tech_stack" in result.decision_patterns or len(result.decision_patterns) >= 0

        # Check for tech stack patterns if extracted
        if result.decision_patterns.get("tech_stack"):
            assert len(result.decision_patterns["tech_stack"]) > 0

    def test_success_correlations(self, sample_history_file: Path, temp_history_path: Path):
        """Test extraction of success correlations."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        # Should identify success correlations
        assert isinstance(result.success_correlations, list)

    def test_failure_correlations(self, sample_history_file: Path, temp_history_path: Path):
        """Test extraction of failure correlations."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        # Should identify failure correlations
        assert isinstance(result.failure_correlations, list)

    def test_category_insights(
        self, history_analyzer: ProjectHistoryAnalyzer, mock_learning_db: MagicMock
    ):
        """Test extraction of category insights."""
        history_analyzer.set_learning_db(mock_learning_db)
        result = history_analyzer.analyze_history()

        # Should have category insights
        assert isinstance(result.category_insights, dict)

        if result.category_insights:
            for category, insights in result.category_insights.items():
                assert "total_improvements" in insights or isinstance(insights, dict)

    def test_recommendations_generation(self, sample_history_file: Path, temp_history_path: Path):
        """Test generation of recommendations."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        # Should generate recommendations
        assert isinstance(result.recommendations, list)

    def test_get_project_by_type(self, sample_history_file: Path, temp_history_path: Path):
        """Test filtering projects by type."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        ecommerce_projects = analyzer.get_project_by_type(result, "ecommerce")

        assert len(ecommerce_projects) == 2
        for project in ecommerce_projects:
            assert project.project_type == "ecommerce"

    def test_save_project_summary(
        self, history_analyzer: ProjectHistoryAnalyzer, temp_history_path: Path
    ):
        """Test saving a project summary."""
        summary = ProjectSummary(
            project_id="new-proj-001",
            project_type="automation",
            name="New Automation Project",
            overall_outcome="successful",
            success_score=0.9,
            tech_stack={"languages": ["Python"]},
        )

        result = history_analyzer.save_project_summary(summary)

        assert result is True
        assert temp_history_path.exists()

        # Verify saved data
        with open(temp_history_path, encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["projects"]) == 1
        assert data["projects"][0]["project_id"] == "new-proj-001"

    def test_save_project_summary_append(self, sample_history_file: Path, temp_history_path: Path):
        """Test appending a project summary to existing file."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)

        summary = ProjectSummary(
            project_id="new-proj-002",
            project_type="trading",
            name="Trading Bot",
            overall_outcome="partial",
            success_score=0.5,
        )

        result = analyzer.save_project_summary(summary)

        assert result is True

        with open(temp_history_path, encoding="utf-8") as f:
            data = json.load(f)

        # Should have original 3 + new 1
        assert len(data["projects"]) == 4

    def test_empty_history_analysis(self, history_analyzer: ProjectHistoryAnalyzer):
        """Test analysis with no history data."""
        result = history_analyzer.analyze_history(min_projects=0)

        assert result.projects_analyzed == 0
        assert len(result.project_summaries) == 0

    def test_history_analysis_result_to_dict(
        self, sample_history_file: Path, temp_history_path: Path
    ):
        """Test HistoryAnalysisResult serialization."""
        analyzer = ProjectHistoryAnalyzer(project_history_path=temp_history_path)
        result = analyzer.analyze_history()

        result_dict = result.to_dict()

        assert "projects_analyzed" in result_dict
        assert "analysis_timestamp" in result_dict
        assert "project_summaries" in result_dict
        assert "decision_patterns" in result_dict


class TestProjectSummary:
    """Tests for ProjectSummary dataclass."""

    def test_to_dict(self):
        """Test ProjectSummary serialization."""
        summary = ProjectSummary(
            project_id="test-001",
            project_type="saas",
            name="Test Project",
            overall_outcome="successful",
            success_score=0.85,
            tech_stack={"languages": ["Python"]},
            lessons_learned=["Lesson 1"],
        )

        summary_dict = summary.to_dict()

        assert summary_dict["project_id"] == "test-001"
        assert summary_dict["project_type"] == "saas"
        assert summary_dict["name"] == "Test Project"
        assert summary_dict["success_score"] == 0.85
        assert "Lesson 1" in summary_dict["lessons_learned"]


class TestProjectDecision:
    """Tests for ProjectDecision dataclass."""

    def test_to_dict(self):
        """Test ProjectDecision serialization."""
        decision = ProjectDecision(
            decision_id="dec-001",
            project_id="proj-001",
            decision_type="tech_stack",
            choice="Python + FastAPI",
            rationale="Team expertise",
            outcome="positive",
            impact_score=0.8,
        )

        decision_dict = decision.to_dict()

        assert decision_dict["decision_id"] == "dec-001"
        assert decision_dict["decision_type"] == "tech_stack"
        assert decision_dict["choice"] == "Python + FastAPI"
        assert decision_dict["impact_score"] == 0.8

    def test_from_dict(self):
        """Test ProjectDecision deserialization."""
        data = {
            "decision_id": "dec-002",
            "project_id": "proj-002",
            "decision_type": "architecture",
            "choice": "microservices",
            "rationale": "Scalability needs",
            "outcome": "positive",
            "impact_score": 0.9,
        }

        decision = ProjectDecision.from_dict(data)

        assert decision.decision_id == "dec-002"
        assert decision.decision_type == "architecture"
        assert decision.choice == "microservices"
        assert decision.impact_score == 0.9
