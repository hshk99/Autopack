"""Tests for cost analysis schema validation."""

import json
import math
from pathlib import Path
from typing import Any, Dict

import pytest

from src.autopack.research.analysis.cost_effectiveness import (
    AITokenCostProjection, ComponentCostData, CostEffectivenessAnalyzer,
    CostOptimizationStrategy, ProjectCostProjection)


class TestCostAnalysisValidation:
    """Test cost analysis validation functionality."""

    @pytest.fixture
    def analyzer(self) -> CostEffectivenessAnalyzer:
        """Create a cost effectiveness analyzer."""
        return CostEffectivenessAnalyzer()

    @pytest.fixture
    def valid_component_data(self) -> Dict[str, Any]:
        """Create valid component data for testing."""
        return {
            "component": "Authentication Service",
            "description": "User authentication and authorization",
            "recommendation": {
                "choice": "buy",
                "specific": "Auth0",
                "rationale": ["Industry standard", "Reduces development time"],
            },
            "cost_data": {
                "initial_cost": 5000.0,
                "monthly_ongoing": 500.0,
                "scaling_model": "linear",
                "year_1_total": 11000.0,
                "year_3_total": 25000.0,
                "year_5_total": 45000.0,
            },
            "options": {
                "buy": {"total_cost_estimate": {"initial": "$5,000", "5_year_total": "$45,000"}}
            },
            "vendor_lock_in": {
                "level": "high",
                "migration_cost": 10000,
                "migration_time": "2-3 months",
                "alternatives": ["Firebase", "Okta"],
            },
            "is_core": False,
        }

    def test_valid_cost_analysis_passes_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that valid cost analysis passes validation."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            components=[
                ComponentCostData(
                    component="Test Component",
                    initial_cost=1000.0,
                    monthly_ongoing=100.0,
                    year_1_total=2200.0,
                    year_3_total=5000.0,
                    year_5_total=10000.0,
                )
            ],
        )

        analysis = analyzer.projection.calculate_all()
        assert analyzer._validate_analysis(analysis) is True

    def test_nan_cost_values_fail_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that NaN cost values fail validation."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")
        analysis = analyzer.projection.calculate_all()

        # Inject NaN value
        analysis["total_cost_of_ownership"]["year_1"]["total"] = float("nan")

        with pytest.raises(ValueError, match="cannot be NaN or Infinity"):
            analyzer._validate_analysis(analysis)

    def test_infinity_cost_values_fail_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that Infinity cost values fail validation."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")
        analysis = analyzer.projection.calculate_all()

        # Inject infinity value
        analysis["total_cost_of_ownership"]["year_5_cumulative"]["total"] = float("inf")

        with pytest.raises(ValueError, match="cannot be NaN or Infinity"):
            analyzer._validate_analysis(analysis)

    def test_negative_cost_values_fail_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that negative cost values fail validation."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")
        analysis = analyzer.projection.calculate_all()

        # Inject negative value
        analysis["total_cost_of_ownership"]["year_1"]["development"] = -1000.0

        with pytest.raises(ValueError, match="cannot be negative"):
            analyzer._validate_analysis(analysis)

    def test_missing_tco_fails_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that missing TCO data fails validation."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")
        analysis = analyzer.projection.calculate_all()

        # Remove TCO
        del analysis["total_cost_of_ownership"]

        with pytest.raises(ValueError, match="Missing total_cost_of_ownership"):
            analyzer._validate_analysis(analysis)

    def test_to_json_validates_before_saving(
        self, analyzer: CostEffectivenessAnalyzer, tmp_path: Path
    ):
        """Test that to_json validates analysis before saving."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            components=[
                ComponentCostData(
                    component="Test Component",
                    initial_cost=1000.0,
                    monthly_ongoing=100.0,
                    year_1_total=2200.0,
                    year_3_total=5000.0,
                    year_5_total=10000.0,
                )
            ],
        )

        output_file = str(tmp_path / "analysis.json")
        analyzer.to_json(output_file)

        # Verify file was created
        assert Path(output_file).exists()

        # Verify content is valid JSON
        with open(output_file) as f:
            saved_data = json.load(f)
            assert "total_cost_of_ownership" in saved_data

    def test_to_json_rejects_nan_values(self, analyzer: CostEffectivenessAnalyzer, tmp_path: Path):
        """Test that to_json rejects analysis with NaN values."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")

        # Mock the calculate_all method to inject NaN
        original_calculate = analyzer.projection.calculate_all

        def mock_calculate():
            result = original_calculate()
            result["total_cost_of_ownership"]["year_1"]["total"] = float("nan")
            return result

        analyzer.projection.calculate_all = mock_calculate

        output_file = str(tmp_path / "analysis.json")

        with pytest.raises(ValueError, match="cannot be NaN or Infinity"):
            analyzer.to_json(output_file)

    def test_budget_anchor_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that budget anchor passes validation with valid data."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            components=[
                ComponentCostData(
                    component="Test Component",
                    initial_cost=1000.0,
                    monthly_ongoing=100.0,
                    year_1_total=2200.0,
                    year_3_total=5000.0,
                    year_5_total=10000.0,
                )
            ],
            optimizations=[
                CostOptimizationStrategy(
                    strategy="Caching",
                    description="Cache responses",
                    potential_savings_percent=0.2,
                    implementation_effort="1 week",
                )
            ],
        )

        anchor = analyzer.generate_budget_anchor()
        assert anchor["pivot_type"] == "BudgetCost"
        assert "cost_breakdown" in anchor
        assert all(v >= 0 for v in anchor["cost_breakdown"].values())

    def test_budget_anchor_rejects_negative_costs(self, analyzer: CostEffectivenessAnalyzer):
        """Test that budget anchor validation rejects negative costs."""
        analyzer.projection = ProjectCostProjection(project_name="Test Project")

        # Manually inject negative cost by mocking
        original_calculate = analyzer.projection.calculate_all

        def mock_calculate():
            result = original_calculate()
            result["total_cost_of_ownership"]["year_1"]["development"] = -1000.0
            return result

        analyzer.projection.calculate_all = mock_calculate

        with pytest.raises(ValueError, match="Invalid BudgetCost anchor"):
            analyzer.generate_budget_anchor()

    def test_ai_projection_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test validation of AI token cost projections."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            ai_features=[
                AITokenCostProjection(
                    feature="Text Generation",
                    model="claude-sonnet",
                    avg_input_tokens=500,
                    avg_output_tokens=1000,
                    requests_per_user_monthly=20,
                    input_price_per_million=3.0,
                    output_price_per_million=15.0,
                )
            ],
        )

        analysis = analyzer.projection.calculate_all()
        assert analyzer._validate_analysis(analysis) is True

        # Check that costs are valid numbers
        ai_proj = analysis["ai_token_projection"]["projections"]
        for year_data in ai_proj.values():
            assert year_data["monthly_cost"] >= 0
            assert year_data["yearly_cost"] >= 0
            assert not math.isnan(year_data["monthly_cost"])
            assert not math.isinf(year_data["monthly_cost"])

    def test_breakeven_analysis_validation(self, analyzer: CostEffectivenessAnalyzer):
        """Test that break-even analysis values are validated."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            components=[
                ComponentCostData(
                    component="Test Component",
                    initial_cost=1000.0,
                    monthly_ongoing=100.0,
                    year_1_total=2200.0,
                    year_3_total=5000.0,
                    year_5_total=10000.0,
                )
            ],
        )

        analysis = analyzer.projection.calculate_all()
        assert analyzer._validate_analysis(analysis) is True

        # Verify break-even values are positive
        breakeven = analysis["break_even_analysis"]
        mrr = breakeven["required_mrr_to_cover_costs"]
        for value in mrr.values():
            assert value >= 0
            assert not math.isnan(value)

    def test_analysis_roundtrip(self, analyzer: CostEffectivenessAnalyzer, tmp_path: Path):
        """Test that analysis can be saved and loaded from JSON."""
        analyzer.projection = ProjectCostProjection(
            project_name="Test Project",
            components=[
                ComponentCostData(
                    component="Test Component",
                    initial_cost=1000.0,
                    monthly_ongoing=100.0,
                    year_1_total=2200.0,
                    year_3_total=5000.0,
                    year_5_total=10000.0,
                )
            ],
        )

        output_file = str(tmp_path / "analysis.json")
        analyzer.to_json(output_file)

        # Load and verify
        with open(output_file) as f:
            loaded = json.load(f)
            assert loaded["total_cost_of_ownership"]["year_1"]["total"] > 0

    def test_empty_projection_raises_error(
        self, analyzer: CostEffectivenessAnalyzer, tmp_path: Path
    ):
        """Test that saving without projection raises error."""
        output_file = str(tmp_path / "analysis.json")

        with pytest.raises(ValueError, match="No projection data available"):
            analyzer.to_json(output_file)

    def test_no_projection_for_anchor_raises_error(self, analyzer: CostEffectivenessAnalyzer):
        """Test that generating anchor without projection raises error."""
        with pytest.raises(ValueError, match="No projection data available"):
            analyzer.generate_budget_anchor()
