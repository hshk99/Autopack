"""Tests for model effectiveness tracking (IMP-LOOP-032).

Tests the ModelEffectivenessReport dataclass and get_model_effectiveness_by_category()
method for tracking per-model success rates by task category to enable data-driven
model selection.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from autopack.telemetry.analyzer import (ModelCategoryStats,
                                         ModelEffectivenessReport,
                                         TelemetryAnalyzer)


class TestModelCategoryStats:
    """Tests for ModelCategoryStats dataclass."""

    def test_creation(self):
        """Test basic creation of ModelCategoryStats."""
        stats = ModelCategoryStats(
            model_id="claude-sonnet-4-5",
            task_category="test_generation",
            success_rate=0.85,
            avg_latency_ms=1500.0,
            avg_tokens_used=2000.0,
            cost_per_success=2352.94,
            sample_count=20,
        )

        assert stats.model_id == "claude-sonnet-4-5"
        assert stats.task_category == "test_generation"
        assert stats.success_rate == 0.85
        assert stats.avg_latency_ms == 1500.0
        assert stats.avg_tokens_used == 2000.0
        assert stats.cost_per_success == 2352.94
        assert stats.sample_count == 20

    def test_default_values_not_allowed(self):
        """Test that all fields are required."""
        with pytest.raises(TypeError):
            ModelCategoryStats()


class TestModelEffectivenessReport:
    """Tests for ModelEffectivenessReport dataclass."""

    @pytest.fixture
    def sample_stats(self):
        """Create sample stats for testing."""
        return {
            "claude-sonnet-4-5": {
                "test_generation": ModelCategoryStats(
                    model_id="claude-sonnet-4-5",
                    task_category="test_generation",
                    success_rate=0.8,
                    avg_latency_ms=1000.0,
                    avg_tokens_used=1500.0,
                    cost_per_success=1875.0,
                    sample_count=10,
                ),
                "code_review": ModelCategoryStats(
                    model_id="claude-sonnet-4-5",
                    task_category="code_review",
                    success_rate=0.9,
                    avg_latency_ms=800.0,
                    avg_tokens_used=1000.0,
                    cost_per_success=1111.11,
                    sample_count=15,
                ),
            },
            "claude-opus-4-5": {
                "test_generation": ModelCategoryStats(
                    model_id="claude-opus-4-5",
                    task_category="test_generation",
                    success_rate=0.95,
                    avg_latency_ms=2000.0,
                    avg_tokens_used=3000.0,
                    cost_per_success=3157.89,
                    sample_count=8,
                ),
            },
        }

    @pytest.fixture
    def sample_report(self, sample_stats):
        """Create sample report for testing."""
        return ModelEffectivenessReport(
            stats_by_model_category=sample_stats,
            best_model_by_category={
                "test_generation": "claude-opus-4-5",
                "code_review": "claude-sonnet-4-5",
            },
            overall_model_rankings={
                "claude-opus-4-5": 0.95,
                "claude-sonnet-4-5": 0.84,
            },
            analysis_window_days=7,
            total_phases_analyzed=33,
            generated_at="2024-01-15T10:00:00Z",
        )

    def test_creation(self, sample_report):
        """Test basic creation of ModelEffectivenessReport."""
        assert len(sample_report.stats_by_model_category) == 2
        assert sample_report.best_model_by_category["test_generation"] == "claude-opus-4-5"
        assert sample_report.best_model_by_category["code_review"] == "claude-sonnet-4-5"
        assert sample_report.analysis_window_days == 7
        assert sample_report.total_phases_analyzed == 33

    def test_best_model_for_known_category(self, sample_report):
        """Test best_model_for returns correct model for known category."""
        assert sample_report.best_model_for("test_generation") == "claude-opus-4-5"
        assert sample_report.best_model_for("code_review") == "claude-sonnet-4-5"

    def test_best_model_for_unknown_category(self, sample_report):
        """Test best_model_for returns top-ranked model for unknown category."""
        # Should return highest ranked model overall
        result = sample_report.best_model_for("unknown_category")
        assert result == "claude-opus-4-5"  # Has higher overall ranking

    def test_best_model_for_empty_rankings(self):
        """Test best_model_for returns None with empty data."""
        empty_report = ModelEffectivenessReport(
            stats_by_model_category={},
            best_model_by_category={},
            overall_model_rankings={},
            analysis_window_days=7,
            total_phases_analyzed=0,
            generated_at="2024-01-15T10:00:00Z",
        )

        assert empty_report.best_model_for("any_category") is None

    def test_overall_model_rankings_sorted(self, sample_report):
        """Test that overall rankings are sorted by score descending."""
        rankings = list(sample_report.overall_model_rankings.items())
        # Should be sorted by score descending
        for i in range(len(rankings) - 1):
            assert rankings[i][1] >= rankings[i + 1][1]


class TestTelemetryAnalyzerModelEffectiveness:
    """Tests for TelemetryAnalyzer.get_model_effectiveness_by_category()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def analyzer(self, mock_db):
        """Create a TelemetryAnalyzer with mock DB."""
        return TelemetryAnalyzer(db_session=mock_db)

    def test_get_model_effectiveness_empty_data(self, analyzer, mock_db):
        """Test with no data in database."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category()

        assert report.total_phases_analyzed == 0
        assert len(report.stats_by_model_category) == 0
        assert len(report.best_model_by_category) == 0
        assert len(report.overall_model_rankings) == 0

    def test_get_model_effectiveness_single_model(self, analyzer, mock_db):
        """Test with data for a single model."""
        # Create mock row
        mock_row = MagicMock()
        mock_row.model_used = "claude-sonnet-4-5"
        mock_row.task_category = "test_generation"
        mock_row.total = 10
        mock_row.successes = 8
        mock_row.avg_duration_seconds = 1.5
        mock_row.avg_tokens = 2000.0

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category()

        assert report.total_phases_analyzed == 10
        assert "claude-sonnet-4-5" in report.stats_by_model_category
        assert "test_generation" in report.stats_by_model_category["claude-sonnet-4-5"]

        stats = report.stats_by_model_category["claude-sonnet-4-5"]["test_generation"]
        assert stats.success_rate == 0.8  # 8/10
        assert stats.avg_latency_ms == 1500.0  # 1.5s * 1000
        assert stats.avg_tokens_used == 2000.0
        assert stats.sample_count == 10

    def test_get_model_effectiveness_multiple_models(self, analyzer, mock_db):
        """Test with data for multiple models."""
        # Create mock rows for two models
        mock_row1 = MagicMock()
        mock_row1.model_used = "claude-sonnet-4-5"
        mock_row1.task_category = "test_generation"
        mock_row1.total = 10
        mock_row1.successes = 7
        mock_row1.avg_duration_seconds = 1.0
        mock_row1.avg_tokens = 1500.0

        mock_row2 = MagicMock()
        mock_row2.model_used = "claude-opus-4-5"
        mock_row2.task_category = "test_generation"
        mock_row2.total = 8
        mock_row2.successes = 7
        mock_row2.avg_duration_seconds = 2.0
        mock_row2.avg_tokens = 3000.0

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category()

        assert report.total_phases_analyzed == 18
        assert len(report.stats_by_model_category) == 2

        # Verify best model selection (opus has higher success rate: 7/8 = 0.875 vs 7/10 = 0.7)
        assert report.best_model_by_category.get("test_generation") == "claude-opus-4-5"

    def test_get_model_effectiveness_min_samples_filtering(self, analyzer, mock_db):
        """Test that models with insufficient samples are not selected as best."""
        # Create mock rows - one model has many samples, other has few
        mock_row1 = MagicMock()
        mock_row1.model_used = "claude-sonnet-4-5"
        mock_row1.task_category = "test_generation"
        mock_row1.total = 10  # Sufficient samples
        mock_row1.successes = 7
        mock_row1.avg_duration_seconds = 1.0
        mock_row1.avg_tokens = 1500.0

        mock_row2 = MagicMock()
        mock_row2.model_used = "claude-opus-4-5"
        mock_row2.task_category = "test_generation"
        mock_row2.total = 2  # Insufficient samples (< default min_samples=5)
        mock_row2.successes = 2  # 100% success but too few samples
        mock_row2.avg_duration_seconds = 2.0
        mock_row2.avg_tokens = 3000.0

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category(min_samples=5)

        # Sonnet should be selected because opus has too few samples
        assert report.best_model_by_category.get("test_generation") == "claude-sonnet-4-5"

    def test_get_model_effectiveness_cost_per_success_calculation(self, analyzer, mock_db):
        """Test that cost_per_success is calculated correctly."""
        mock_row = MagicMock()
        mock_row.model_used = "claude-sonnet-4-5"
        mock_row.task_category = "test_generation"
        mock_row.total = 10
        mock_row.successes = 5  # 50% success rate
        mock_row.avg_duration_seconds = 1.0
        mock_row.avg_tokens = 2000.0

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category()

        stats = report.stats_by_model_category["claude-sonnet-4-5"]["test_generation"]
        # cost_per_success = avg_tokens / success_rate = 2000 / 0.5 = 4000
        assert stats.cost_per_success == 4000.0

    def test_get_model_effectiveness_window_days(self, analyzer, mock_db):
        """Test that window_days parameter is used in query."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_db.execute.return_value = mock_result

        report = analyzer.get_model_effectiveness_by_category(window_days=30)

        assert report.analysis_window_days == 30

    def test_get_model_effectiveness_null_handling(self, analyzer, mock_db):
        """Test handling of NULL values in database results."""
        mock_row = MagicMock()
        mock_row.model_used = "claude-sonnet-4-5"
        mock_row.task_category = "test_generation"
        mock_row.total = None  # NULL
        mock_row.successes = None  # NULL
        mock_row.avg_duration_seconds = None  # NULL
        mock_row.avg_tokens = None  # NULL

        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row])
        mock_db.execute.return_value = mock_result

        # Should not raise exception
        report = analyzer.get_model_effectiveness_by_category()

        # Should have zero for the row with all nulls
        assert report.total_phases_analyzed == 0


class TestLlmServiceModelSelection:
    """Tests for LlmService.select_model_for_task()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def mock_llm_service(self, mock_db):
        """Create a minimal mock LlmService for testing."""
        with patch("autopack.llm_service.ModelRouter"):
            with patch("autopack.llm_service.QualityGate"):
                from autopack.llm_service import LlmService

                # Create mock service
                service = MagicMock(spec=LlmService)
                service.db = mock_db
                service.anthropic_builder = MagicMock()
                service.openai_builder = MagicMock()
                service.gemini_builder = None

                # Bind the actual methods we want to test
                service.select_model_for_task = LlmService.select_model_for_task.__get__(
                    service, LlmService
                )
                service._is_model_available = LlmService._is_model_available.__get__(
                    service, LlmService
                )
                service.get_model_effectiveness_report = (
                    LlmService.get_model_effectiveness_report.__get__(service, LlmService)
                )

                return service

    def test_select_model_fallback_on_error(self, mock_llm_service, mock_db):
        """Test that select_model_for_task falls back to default on error."""
        # Make the DB throw an exception
        mock_db.execute.side_effect = Exception("DB error")

        result = mock_llm_service.select_model_for_task("test_generation")

        assert result == "claude-sonnet-4-5"

    def test_select_model_with_custom_fallback(self, mock_llm_service, mock_db):
        """Test that custom fallback model is used."""
        mock_db.execute.side_effect = Exception("DB error")

        result = mock_llm_service.select_model_for_task("test_generation", fallback_model="gpt-4o")

        assert result == "gpt-4o"

    def test_is_model_available_anthropic(self, mock_llm_service):
        """Test _is_model_available for Anthropic models."""
        mock_llm_service.anthropic_builder = MagicMock()

        assert mock_llm_service._is_model_available("claude-sonnet-4-5") is True
        assert mock_llm_service._is_model_available("claude-opus-4-5") is True

    def test_is_model_available_openai(self, mock_llm_service):
        """Test _is_model_available for OpenAI models."""
        mock_llm_service.openai_builder = MagicMock()

        assert mock_llm_service._is_model_available("gpt-4o") is True
        assert mock_llm_service._is_model_available("o1-preview") is True

    def test_is_model_available_gemini_unavailable(self, mock_llm_service):
        """Test _is_model_available for unavailable Gemini."""
        mock_llm_service.gemini_builder = None

        assert mock_llm_service._is_model_available("gemini-1.5-pro") is False

    def test_is_model_available_unknown_model(self, mock_llm_service):
        """Test _is_model_available for unknown models defaults to True."""
        assert mock_llm_service._is_model_available("unknown-model-xyz") is True


class TestModelEffectivenessIntegration:
    """Integration tests for model effectiveness tracking."""

    def test_report_best_model_for_consistency(self):
        """Test that best_model_for is consistent with best_model_by_category."""
        report = ModelEffectivenessReport(
            stats_by_model_category={
                "model-a": {
                    "category-1": ModelCategoryStats(
                        model_id="model-a",
                        task_category="category-1",
                        success_rate=0.9,
                        avg_latency_ms=1000.0,
                        avg_tokens_used=1500.0,
                        cost_per_success=1666.67,
                        sample_count=10,
                    ),
                },
            },
            best_model_by_category={"category-1": "model-a"},
            overall_model_rankings={"model-a": 0.9},
            analysis_window_days=7,
            total_phases_analyzed=10,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # best_model_for should return what's in best_model_by_category
        assert report.best_model_for("category-1") == "model-a"

    def test_report_generated_at_is_valid_iso_format(self):
        """Test that generated_at is a valid ISO timestamp."""
        report = ModelEffectivenessReport(
            stats_by_model_category={},
            best_model_by_category={},
            overall_model_rankings={},
            analysis_window_days=7,
            total_phases_analyzed=0,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(report.generated_at.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)
