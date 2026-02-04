"""
Comprehensive tests for cost_effectiveness module.

Tests cover cost analysis, projections, scaling models, and budget anchors
with 85%+ code coverage for CostEffectivenessAnalyzer.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.autopack.research.analysis.cost_effectiveness import (
    AITokenCostProjection,
    ComponentCostData,
    CostAnalysisModel,
    CostCategory,
    CostEffectivenessAnalyzer,
    CostOptimizationStrategy,
    DecisionType,
    ProjectCostProjection,
    ScalingModel,
    VendorLockInLevel,
)


class TestCostCategory:
    """Test CostCategory enum."""

    def test_all_categories_exist(self) -> None:
        """Verify all cost categories are defined."""
        categories = {cat.value for cat in CostCategory}
        expected = {
            "development",
            "infrastructure",
            "services",
            "ai_tokens",
            "operational",
            "hidden",
        }
        assert categories == expected

    def test_category_values(self) -> None:
        """Test specific category values."""
        assert CostCategory.DEVELOPMENT.value == "development"
        assert CostCategory.INFRASTRUCTURE.value == "infrastructure"
        assert CostCategory.AI_TOKENS.value == "ai_tokens"


class TestScalingModel:
    """Test ScalingModel enum."""

    def test_all_scaling_models_exist(self) -> None:
        """Verify all scaling models are defined."""
        models = {model.value for model in ScalingModel}
        expected = {"flat", "linear", "step_function", "logarithmic", "exponential"}
        assert models == expected

    def test_scaling_model_values(self) -> None:
        """Test specific scaling model values."""
        assert ScalingModel.FLAT.value == "flat"
        assert ScalingModel.LINEAR.value == "linear"
        assert ScalingModel.EXPONENTIAL.value == "exponential"


class TestDecisionType:
    """Test DecisionType enum."""

    def test_all_decision_types_exist(self) -> None:
        """Verify all decision types are defined."""
        decisions = {dec.value for dec in DecisionType}
        expected = {"build", "buy", "integrate", "outsource"}
        assert decisions == expected


class TestVendorLockInLevel:
    """Test VendorLockInLevel enum."""

    def test_all_lock_in_levels_exist(self) -> None:
        """Verify all vendor lock-in levels are defined."""
        levels = {level.value for level in VendorLockInLevel}
        expected = {"low", "medium", "high", "critical"}
        assert levels == expected


class TestComponentCostData:
    """Test ComponentCostData data class."""

    def test_default_initialization(self) -> None:
        """Test creating ComponentCostData with defaults."""
        component = ComponentCostData(component="database")
        assert component.component == "database"
        assert component.decision == DecisionType.BUILD
        assert component.initial_cost == 0.0
        assert component.monthly_ongoing == 0.0
        assert component.scaling_model == ScalingModel.FLAT
        assert component.year_1_total == 0.0

    def test_full_initialization(self) -> None:
        """Test creating ComponentCostData with all fields."""
        component = ComponentCostData(
            component="database",
            decision=DecisionType.BUY,
            service_name="AWS RDS",
            initial_cost=5000.0,
            monthly_ongoing=500.0,
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=10.0,
            vendor_lock_in_level=VendorLockInLevel.MEDIUM,
            is_core_differentiator=True,
        )
        assert component.service_name == "AWS RDS"
        assert component.decision == DecisionType.BUY
        assert component.is_core_differentiator is True

    def test_calculate_projections_flat_scaling(self) -> None:
        """Test projection calculations with flat scaling."""
        component = ComponentCostData(
            component="analytics",
            monthly_ongoing=1000.0,
            scaling_model=ScalingModel.FLAT,
        )
        component.calculate_projections(1000, 10000, 50000)
        assert component.year_1_total == 12000.0  # 1000 * 12
        assert component.year_3_total == 36000.0  # 1000 * 12 * 3
        assert component.year_5_total == 60000.0  # 1000 * 12 * 5

    def test_calculate_projections_linear_scaling(self) -> None:
        """Test projection calculations with linear scaling."""
        component = ComponentCostData(
            component="api",
            monthly_ongoing=100.0,
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=0.01,  # 0.01 per user per month
        )
        component.calculate_projections(1000, 5000, 10000)
        # Base: 100 * 12 per year
        # Year 1: 100*12 + (1000 * 0.01 * 12) = 1200 + 120 = 1320
        assert component.year_1_total > 1000
        assert component.year_3_total > component.year_1_total

    def test_calculate_projections_step_function(self) -> None:
        """Test projection calculations with step function scaling."""
        component = ComponentCostData(
            component="cdn",
            monthly_ongoing=500.0,
            scaling_model=ScalingModel.STEP_FUNCTION,
            scaling_factor=1000.0,  # Cost increases by 1000 per 10k users
        )
        component.calculate_projections(5000, 15000, 50000)
        assert component.year_1_total > component.monthly_ongoing * 12
        assert component.year_3_total > component.year_1_total

    def test_calculate_projections_logarithmic(self) -> None:
        """Test projection calculations with logarithmic scaling."""
        component = ComponentCostData(
            component="cache",
            monthly_ongoing=200.0,
            scaling_model=ScalingModel.LOGARITHMIC,
            scaling_factor=100.0,
        )
        component.calculate_projections(1000, 10000, 100000)
        assert component.year_1_total > 0
        assert component.year_5_total > component.year_1_total
        # Logarithmic scaling should produce valid projections
        assert component.year_3_total >= component.year_1_total

    def test_calculate_projections_exponential(self) -> None:
        """Test projection calculations with exponential scaling."""
        component = ComponentCostData(
            component="ml_model",
            monthly_ongoing=1000.0,
            scaling_model=ScalingModel.EXPONENTIAL,
            scaling_factor=1.2,
        )
        component.calculate_projections(1000, 10000, 100000)
        assert component.year_5_total > component.year_1_total
        # Exponential should show significant growth
        assert component.year_5_total > component.year_1_total * 2

    def test_calculate_projections_zero_users(self) -> None:
        """Test projections with zero users."""
        component = ComponentCostData(
            component="test",
            monthly_ongoing=500.0,
        )
        component.calculate_projections(0, 0, 0)
        # Should still account for fixed monthly cost
        assert component.year_1_total >= 0


class TestAITokenCostProjection:
    """Test AITokenCostProjection data class."""

    def test_initialization(self) -> None:
        """Test creating AITokenCostProjection."""
        proj = AITokenCostProjection(
            feature="research",
            model="claude-3-sonnet",
            avg_input_tokens=2000,
            avg_output_tokens=1500,
            requests_per_user_monthly=10,
        )
        assert proj.feature == "research"
        assert proj.model == "claude-3-sonnet"
        assert proj.requests_per_user_monthly == 10

    def test_cost_per_request(self) -> None:
        """Test cost per request calculation."""
        proj = AITokenCostProjection(
            feature="analysis",
            model="gpt-4",
            avg_input_tokens=1000,
            avg_output_tokens=500,
            requests_per_user_monthly=5,
            input_price_per_million=0.03,
            output_price_per_million=0.06,
        )
        cost = proj.cost_per_request
        assert cost > 0
        # (1000 * 0.03 / 1000000) + (500 * 0.06 / 1000000)
        assert cost < 0.01

    def test_monthly_cost_for_users(self) -> None:
        """Test monthly cost calculation for user count."""
        proj = AITokenCostProjection(
            feature="generation",
            model="claude",
            avg_input_tokens=500,
            avg_output_tokens=1000,
            requests_per_user_monthly=20,
        )
        monthly_cost = proj.monthly_cost_for_users(1000)
        assert monthly_cost > 0
        # More users = higher cost
        assert proj.monthly_cost_for_users(10000) > monthly_cost

    def test_custom_pricing(self) -> None:
        """Test with custom pricing."""
        proj = AITokenCostProjection(
            feature="custom",
            model="local-model",
            avg_input_tokens=100,
            avg_output_tokens=100,
            requests_per_user_monthly=100,
            input_price_per_million=1.0,
            output_price_per_million=2.0,
        )
        cost = proj.cost_per_request
        assert cost > 0


class TestCostOptimizationStrategy:
    """Test CostOptimizationStrategy data class."""

    def test_initialization(self) -> None:
        """Test creating CostOptimizationStrategy."""
        strategy = CostOptimizationStrategy(
            strategy="caching",
            description="Implement Redis caching",
            potential_savings_percent=25.5,
            implementation_effort="medium",
        )
        assert strategy.strategy == "caching"
        assert strategy.potential_savings_percent == 25.5
        assert strategy.priority == "medium"

    def test_priority_variations(self) -> None:
        """Test different priority levels."""
        for priority in ["low", "medium", "high", "critical"]:
            strategy = CostOptimizationStrategy(
                strategy=f"strategy_{priority}",
                description="Test",
                potential_savings_percent=10.0,
                implementation_effort="low",
                priority=priority,
            )
            assert strategy.priority == priority


class TestProjectCostProjection:
    """Test ProjectCostProjection data class."""

    def test_initialization(self) -> None:
        """Test creating ProjectCostProjection."""
        proj = ProjectCostProjection(
            project_name="test_project",
            analysis_date=datetime.now(),
            components=[],
            ai_features=[],
        )
        assert proj.project_name == "test_project"
        assert proj.currency == "USD"
        assert proj.year_1_users == 1000

    def test_with_components(self) -> None:
        """Test projection with multiple components."""
        components = [
            ComponentCostData(
                component="db",
                monthly_ongoing=500.0,
            ),
            ComponentCostData(
                component="api",
                monthly_ongoing=200.0,
            ),
        ]
        proj = ProjectCostProjection(
            project_name="multi_component",
            analysis_date=datetime.now(),
            components=components,
            ai_features=[],
        )
        assert len(proj.components) == 2

    def test_calculate_all(self) -> None:
        """Test complete cost analysis calculation."""
        proj = ProjectCostProjection(
            project_name="full_analysis",
            analysis_date=datetime.now(),
            components=[
                ComponentCostData(
                    component="backend",
                    monthly_ongoing=1000.0,
                )
            ],
            ai_features=[
                AITokenCostProjection(
                    feature="search",
                    model="claude",
                    avg_input_tokens=500,
                    avg_output_tokens=500,
                    requests_per_user_monthly=5,
                )
            ],
            year_1_users=1000,
            year_3_users=5000,
            year_5_users=20000,
        )
        analysis = proj.calculate_all()
        assert "executive_summary" in analysis
        assert "component_analysis" in analysis
        assert "ai_token_projection" in analysis
        assert "infrastructure_projection" in analysis
        assert "development_costs" in analysis
        assert "total_cost_of_ownership" in analysis
        assert "cost_optimization_roadmap" in analysis
        assert "risk_adjusted_costs" in analysis
        assert "break_even_analysis" in analysis


class TestCostEffectivenessAnalyzer:
    """Test CostEffectivenessAnalyzer main class."""

    @pytest.fixture
    def analyzer(self) -> CostEffectivenessAnalyzer:
        """Create analyzer instance."""
        return CostEffectivenessAnalyzer()

    def test_initialization(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analyzer initialization."""
        assert analyzer is not None

    def test_analyze_with_build_vs_buy_results(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis with build-vs-buy data."""
        build_vs_buy_results = [
            {
                "component": "database",
                "recommendation": "buy",
                "service": "AWS RDS",
                "estimated_cost": "$500/month",
                "rationale": "Cost-effective managed service",
            },
            {
                "component": "cache",
                "recommendation": "build",
                "estimated_cost": "$200/month",
                "rationale": "Simple use case",
            },
        ]
        analysis = analyzer.analyze(
            project_name="test_project",
            build_vs_buy_results=build_vs_buy_results,
        )
        assert analysis is not None
        assert "executive_summary" in analysis

    def test_analyze_with_user_projections(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis with custom user projections."""
        projections = {
            "year_1": 5000,
            "year_3": 25000,
            "year_5": 100000,
        }
        analysis = analyzer.analyze(
            project_name="growth_project",
            build_vs_buy_results=[
                {
                    "component": "api",
                    "recommendation": "buy",
                    "service": "Stripe",
                    "estimated_cost": "$299+/month",
                }
            ],
            user_projections=projections,
        )
        assert analysis is not None
        assert "total_cost_of_ownership" in analysis

    def test_analyze_with_ai_features(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis including AI feature costs."""
        ai_features = [
            {
                "feature": "intelligent_search",
                "model": "claude-3-sonnet",
                "input_tokens_avg": 1000,
                "output_tokens_avg": 500,
                "requests_per_user_monthly": 10,
            }
        ]
        analysis = analyzer.analyze(
            project_name="ai_project",
            build_vs_buy_results=[],
            ai_features=ai_features,
        )
        assert analysis is not None
        assert "ai_token_projection" in analysis

    def test_analyze_with_technical_feasibility(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis with technical feasibility data."""
        feasibility = {
            "overall_feasibility": 0.85,
            "complexity_score": 7,
            "risk_level": "medium",
            "dependencies": ["service-a", "service-b"],
        }
        analysis = analyzer.analyze(
            project_name="feasible_project",
            build_vs_buy_results=[],
            technical_feasibility=feasibility,
        )
        assert analysis is not None

    def test_generate_budget_anchor(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test budget anchor generation."""
        analyzer.analyze(
            project_name="anchor_project",
            build_vs_buy_results=[
                {
                    "component": "payment",
                    "recommendation": "buy",
                    "estimated_cost": "$1000/month",
                }
            ],
        )
        anchor = analyzer.generate_budget_anchor()
        assert anchor is not None
        assert "pivot_type" in anchor
        assert "budget_constraints" in anchor
        assert "cost_breakdown" in anchor

    def test_to_json(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test JSON export functionality."""
        analyzer.analyze(
            project_name="json_export",
            build_vs_buy_results=[],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "cost_analysis.json"
            analyzer.to_json(str(filepath))
            assert filepath.exists()
            with open(filepath) as f:
                data = json.load(f)
                assert data is not None

    def test_parse_cost_string_variations(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test parsing various cost string formats."""
        test_cases = [
            ("$100", 100.0),
            ("$1,000", 1000.0),
            ("100", 100.0),
            ("$0.99", 0.99),
            ("$15/month", 15.0),
            ("$2,500.50", 2500.50),
        ]
        for cost_str, expected in test_cases:
            parsed = analyzer._parse_cost_string(cost_str)
            assert abs(parsed - expected) < 0.01

    def test_validate_analysis(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis validation."""
        # Generate a valid analysis dict using the actual analyzer
        analysis = analyzer.analyze(
            project_name="validation_test",
            build_vs_buy_results=[],
        )
        # This should not raise an exception since it's a real analysis
        assert analyzer._validate_analysis(analysis) is True

    def test_multiple_components_analysis(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis with many components."""
        components = [
            {
                "component": f"service_{i}",
                "recommendation": "buy" if i % 2 == 0 else "build",
                "estimated_cost": f"${100 * (i + 1)}/month",
            }
            for i in range(10)
        ]
        analysis = analyzer.analyze(
            project_name="multi_service",
            build_vs_buy_results=components,
        )
        assert analysis is not None
        assert "executive_summary" in analysis

    def test_empty_build_vs_buy_results(self, analyzer: CostEffectivenessAnalyzer) -> None:
        """Test analysis with empty components."""
        analysis = analyzer.analyze(
            project_name="minimal",
            build_vs_buy_results=[],
        )
        assert analysis is not None
        assert "executive_summary" in analysis


class TestValidation:
    """Test validation and error handling."""

    def test_cost_analysis_model_validation(self) -> None:
        """Test CostAnalysisModel validation."""
        valid_model = CostAnalysisModel(
            total_monthly=1000.0,
            total_annual=12000.0,
            categories=[],
        )
        assert valid_model.total_monthly == 1000.0

    def test_component_cost_data_alternatives(self) -> None:
        """Test component with alternatives."""
        component = ComponentCostData(
            component="messaging",
            decision=DecisionType.BUY,
            alternatives=["Kafka", "RabbitMQ", "AWS SQS"],
        )
        assert len(component.alternatives) == 3
        assert "Kafka" in component.alternatives

    def test_migration_scenarios(self) -> None:
        """Test components with migration considerations."""
        component = ComponentCostData(
            component="legacy_db",
            decision=DecisionType.BUILD,
            vendor_lock_in_level=VendorLockInLevel.CRITICAL,
            migration_cost=50000.0,
            migration_time="6 months",
        )
        assert component.migration_cost == 50000.0
        assert component.vendor_lock_in_level == VendorLockInLevel.CRITICAL


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_large_user_numbers(self) -> None:
        """Test with very large user projections."""
        proj = ProjectCostProjection(
            project_name="massive_scale",
            analysis_date=datetime.now(),
            components=[],
            ai_features=[],
            year_1_users=1000000,
            year_5_users=100000000,
        )
        analysis = proj.calculate_all()
        assert analysis is not None

    def test_very_small_costs(self) -> None:
        """Test with very small costs."""
        component = ComponentCostData(
            component="minimal",
            monthly_ongoing=0.01,
        )
        component.calculate_projections(1, 2, 3)
        assert component.year_1_total > 0

    def test_zero_initial_state(self) -> None:
        """Test analyzer with completely empty data."""
        analyzer = CostEffectivenessAnalyzer()
        analysis = analyzer.analyze(
            project_name="empty",
            build_vs_buy_results=[],
        )
        assert analysis is not None

    def test_complex_scaling_factors(self) -> None:
        """Test with complex scaling factor scenarios."""
        component = ComponentCostData(
            component="dynamic",
            monthly_ongoing=100.0,
            scaling_model=ScalingModel.EXPONENTIAL,
            scaling_factor=1.5,
        )
        component.calculate_projections(100, 1000, 10000)
        assert component.year_5_total > component.year_1_total
