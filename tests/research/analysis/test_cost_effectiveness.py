"""
Comprehensive tests for cost_effectiveness analyzer module.

Tests cover:
- Data class initialization and serialization
- Cost projection calculations for all scaling models
- Multi-year TCO calculations
- AI token cost projections
- Break-even analysis
- Budget anchor generation
- Cost optimization strategies
- Vendor lock-in assessment
"""

import json

import pytest

pytestmark = pytest.mark.research

from autopack.research.analysis.cost_effectiveness import (
    AITokenCostProjection, ComponentCostData, CostCategory,
    CostEffectivenessAnalyzer, CostOptimizationStrategy, DecisionType,
    ProjectCostProjection, ScalingModel, VendorLockInLevel)


class TestCostCategory:
    """Tests for CostCategory enum."""

    def test_all_cost_categories_exist(self):
        """Test that all expected cost categories are defined."""
        categories = {c.value for c in CostCategory}
        expected = {
            "development",
            "infrastructure",
            "services",
            "ai_tokens",
            "operational",
            "hidden",
        }
        assert categories == expected

    def test_cost_category_values(self):
        """Test cost category enum values."""
        assert CostCategory.DEVELOPMENT.value == "development"
        assert CostCategory.INFRASTRUCTURE.value == "infrastructure"
        assert CostCategory.SERVICES.value == "services"
        assert CostCategory.AI_TOKENS.value == "ai_tokens"
        assert CostCategory.OPERATIONAL.value == "operational"
        assert CostCategory.HIDDEN.value == "hidden"


class TestScalingModel:
    """Tests for ScalingModel enum."""

    def test_all_scaling_models_exist(self):
        """Test that all expected scaling models are defined."""
        models = {m.value for m in ScalingModel}
        expected = {"flat", "linear", "step_function", "logarithmic", "exponential"}
        assert models == expected

    def test_scaling_model_values(self):
        """Test scaling model enum values."""
        assert ScalingModel.FLAT.value == "flat"
        assert ScalingModel.LINEAR.value == "linear"
        assert ScalingModel.STEP_FUNCTION.value == "step_function"
        assert ScalingModel.LOGARITHMIC.value == "logarithmic"
        assert ScalingModel.EXPONENTIAL.value == "exponential"


class TestComponentCostData:
    """Tests for ComponentCostData data class."""

    def test_basic_initialization(self):
        """Test basic initialization with required fields."""
        component = ComponentCostData(component="Database", description="PostgreSQL database")
        assert component.component == "Database"
        assert component.description == "PostgreSQL database"
        assert component.decision == DecisionType.BUILD
        assert component.initial_cost == 0.0
        assert component.monthly_ongoing == 0.0

    def test_full_initialization(self):
        """Test initialization with all fields."""
        component = ComponentCostData(
            component="Auth Service",
            description="Third-party auth",
            decision=DecisionType.BUY,
            service_name="Auth0",
            initial_cost=1000.0,
            monthly_ongoing=99.0,
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=0.5,
            vendor_lock_in_level=VendorLockInLevel.HIGH,
            migration_cost=5000.0,
            migration_time="2 weeks",
            alternatives=["Okta", "AWS Cognito"],
            is_core_differentiator=False,
            rationale="Industry standard solution",
        )
        assert component.component == "Auth Service"
        assert component.service_name == "Auth0"
        assert component.decision == DecisionType.BUY
        assert component.initial_cost == 1000.0
        assert component.scaling_factor == 0.5
        assert component.vendor_lock_in_level == VendorLockInLevel.HIGH
        assert len(component.alternatives) == 2

    def test_calculate_projections_flat_scaling(self):
        """Test cost projections with flat scaling model."""
        component = ComponentCostData(
            component="Monitoring",
            initial_cost=500.0,
            monthly_ongoing=100.0,
            scaling_model=ScalingModel.FLAT,
        )
        component.calculate_projections(year_1_users=1000, year_3_users=10000, year_5_users=50000)

        # Flat: initial + (monthly * months)
        expected_year_1 = 500.0 + (100.0 * 12)
        expected_year_3 = 500.0 + (100.0 * 36)
        expected_year_5 = 500.0 + (100.0 * 60)

        assert component.year_1_total == expected_year_1
        assert component.year_3_total == expected_year_3
        assert component.year_5_total == expected_year_5

    def test_calculate_projections_linear_scaling(self):
        """Test cost projections with linear scaling model."""
        component = ComponentCostData(
            component="Compute",
            initial_cost=0.0,
            monthly_ongoing=100.0,
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=0.01,  # $0.01 per user per month
        )
        component.calculate_projections(year_1_users=1000, year_3_users=10000, year_5_users=50000)

        # Linear: initial + (monthly * months) + (scaling_factor * users * months)
        expected_year_1 = 0.0 + (100.0 * 12) + (0.01 * 1000 * 12)
        expected_year_3 = 0.0 + (100.0 * 36) + (0.01 * 10000 * 36)
        expected_year_5 = 0.0 + (100.0 * 60) + (0.01 * 50000 * 60)

        assert component.year_1_total == expected_year_1
        assert component.year_3_total == expected_year_3
        assert component.year_5_total == expected_year_5

    def test_calculate_projections_step_function_scaling(self):
        """Test cost projections with step function scaling model."""
        component = ComponentCostData(
            component="Database",
            initial_cost=0.0,
            monthly_ongoing=50.0,
            scaling_model=ScalingModel.STEP_FUNCTION,
            scaling_factor=1000.0,  # $1000 per step
        )
        component.calculate_projections(year_1_users=1000, year_3_users=10000, year_5_users=50000)

        # Step function: steps at 1k, 10k, 100k
        # Year 1: 1k users = 0 steps, Year 3: 10k users = 1 step, Year 5: 50k users = 2 steps
        expected_year_1 = 0.0 + (50.0 * 12) + (1000.0 * 0 * 12)  # 600
        expected_year_3 = 0.0 + (50.0 * 36) + (1000.0 * 1 * 36)  # 37800
        expected_year_5 = 0.0 + (50.0 * 60) + (1000.0 * 2 * 60)  # 123000

        assert component.year_1_total == pytest.approx(expected_year_1)
        assert component.year_3_total == pytest.approx(expected_year_3)
        assert component.year_5_total == pytest.approx(expected_year_5)

    def test_calculate_projections_logarithmic_scaling(self):
        """Test cost projections with logarithmic scaling model."""
        import math

        component = ComponentCostData(
            component="Analytics",
            initial_cost=0.0,
            monthly_ongoing=50.0,
            scaling_model=ScalingModel.LOGARITHMIC,
            scaling_factor=1000.0,
        )
        component.calculate_projections(year_1_users=1000, year_3_users=10000, year_5_users=50000)

        # Logarithmic: initial + (monthly * months) + (scaling_factor * log10(users) * months)
        expected_year_1 = 0.0 + (50.0 * 12) + (1000.0 * math.log10(1000) * 12)
        expected_year_3 = 0.0 + (50.0 * 36) + (1000.0 * math.log10(10000) * 36)
        expected_year_5 = 0.0 + (50.0 * 60) + (1000.0 * math.log10(50000) * 60)

        assert component.year_1_total == pytest.approx(expected_year_1)
        assert component.year_3_total == pytest.approx(expected_year_3)
        assert component.year_5_total == pytest.approx(expected_year_5)

    def test_calculate_projections_exponential_scaling(self):
        """Test cost projections with exponential scaling (uses base cost only)."""
        component = ComponentCostData(
            component="Infrastructure",
            initial_cost=1000.0,
            monthly_ongoing=200.0,
            scaling_model=ScalingModel.EXPONENTIAL,
            scaling_factor=0.1,
        )
        component.calculate_projections(year_1_users=1000, year_3_users=10000, year_5_users=50000)

        # Exponential falls through to base calculation (no exponential handling)
        expected_year_1 = 1000.0 + (200.0 * 12)
        expected_year_3 = 1000.0 + (200.0 * 36)
        expected_year_5 = 1000.0 + (200.0 * 60)

        assert component.year_1_total == expected_year_1
        assert component.year_3_total == expected_year_3
        assert component.year_5_total == expected_year_5

    def test_calculate_projections_with_zero_users(self):
        """Test cost projections with zero users."""
        component = ComponentCostData(
            component="Service",
            initial_cost=100.0,
            monthly_ongoing=50.0,
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=1.0,
        )
        component.calculate_projections(year_1_users=0, year_3_users=0, year_5_users=0)

        expected_year_1 = 100.0 + (50.0 * 12)
        assert component.year_1_total == expected_year_1


class TestAITokenCostProjection:
    """Tests for AITokenCostProjection data class."""

    def test_basic_initialization(self):
        """Test basic initialization."""
        projection = AITokenCostProjection(
            feature="Search",
            model="claude-sonnet",
            avg_input_tokens=500,
            avg_output_tokens=1000,
            requests_per_user_monthly=20,
        )
        assert projection.feature == "Search"
        assert projection.model == "claude-sonnet"
        assert projection.input_price_per_million == 3.0  # Default
        assert projection.output_price_per_million == 15.0  # Default

    def test_cost_per_request_calculation(self):
        """Test cost per request calculation."""
        projection = AITokenCostProjection(
            feature="Search",
            model="claude-sonnet",
            avg_input_tokens=1_000_000,  # 1M tokens
            avg_output_tokens=1_000_000,  # 1M tokens
            requests_per_user_monthly=1,
            input_price_per_million=3.0,
            output_price_per_million=15.0,
        )
        # Cost: (1M / 1M) * 3 + (1M / 1M) * 15 = 3 + 15 = 18
        assert projection.cost_per_request == 18.0

    def test_cost_per_request_with_custom_pricing(self):
        """Test cost per request with custom pricing."""
        projection = AITokenCostProjection(
            feature="Summarization",
            model="claude-haiku",
            avg_input_tokens=500_000,
            avg_output_tokens=250_000,
            requests_per_user_monthly=10,
            input_price_per_million=0.8,
            output_price_per_million=4.0,
        )
        # Cost: (500k / 1M) * 0.8 + (250k / 1M) * 4.0 = 0.4 + 1.0 = 1.4
        assert projection.cost_per_request == pytest.approx(1.4)

    def test_monthly_cost_for_users(self):
        """Test monthly cost calculation for given user count."""
        projection = AITokenCostProjection(
            feature="Search",
            model="claude-sonnet",
            avg_input_tokens=500_000,
            avg_output_tokens=500_000,
            requests_per_user_monthly=10,
            input_price_per_million=3.0,
            output_price_per_million=15.0,
        )
        # Cost per request: (500k/1M)*3 + (500k/1M)*15 = 1.5 + 7.5 = 9
        # Monthly for 100 users: 9 * 10 * 100 = 9000
        monthly_cost = projection.monthly_cost_for_users(100)
        assert monthly_cost == pytest.approx(9000.0)

    def test_monthly_cost_scales_linearly(self):
        """Test that monthly cost scales linearly with user count."""
        projection = AITokenCostProjection(
            feature="Generation",
            model="claude-sonnet",
            avg_input_tokens=1000,
            avg_output_tokens=2000,
            requests_per_user_monthly=5,
        )
        cost_100 = projection.monthly_cost_for_users(100)
        cost_1000 = projection.monthly_cost_for_users(1000)

        # Cost should scale linearly with users
        assert cost_1000 == pytest.approx(cost_100 * 10)


class TestCostOptimizationStrategy:
    """Tests for CostOptimizationStrategy data class."""

    def test_basic_initialization(self):
        """Test basic initialization."""
        strategy = CostOptimizationStrategy(
            strategy="Response caching",
            description="Cache AI responses for common queries",
            potential_savings_percent=0.35,
            implementation_effort="1-2 days",
        )
        assert strategy.strategy == "Response caching"
        assert strategy.potential_savings_percent == 0.35
        assert strategy.priority == "medium"  # Default

    def test_initialization_with_priority(self):
        """Test initialization with custom priority."""
        strategy = CostOptimizationStrategy(
            strategy="Model downgrade",
            description="Use cheaper models for simple queries",
            potential_savings_percent=0.45,
            implementation_effort="2-3 days",
            priority="high",
        )
        assert strategy.priority == "high"


class TestProjectCostProjection:
    """Tests for ProjectCostProjection and calculation methods."""

    @pytest.fixture
    def basic_projection(self):
        """Create a basic projection for testing."""
        return ProjectCostProjection(
            project_name="TestProject",
            year_1_users=1000,
            year_3_users=10000,
            year_5_users=50000,
        )

    def test_initialization(self, basic_projection):
        """Test basic initialization."""
        assert basic_projection.project_name == "TestProject"
        assert basic_projection.year_1_users == 1000
        assert basic_projection.year_3_users == 10000
        assert basic_projection.year_5_users == 50000
        assert len(basic_projection.components) == 0
        assert len(basic_projection.ai_features) == 0

    def test_calculate_all_returns_complete_analysis(self, basic_projection):
        """Test that calculate_all returns all required sections."""
        result = basic_projection.calculate_all()

        expected_sections = {
            "executive_summary",
            "component_analysis",
            "ai_token_projection",
            "infrastructure_projection",
            "development_costs",
            "total_cost_of_ownership",
            "cost_optimization_roadmap",
            "risk_adjusted_costs",
            "break_even_analysis",
            "vendor_lock_in_assessment",
        }
        assert set(result.keys()) == expected_sections

    def test_executive_summary_structure(self, basic_projection):
        """Test executive summary structure."""
        result = basic_projection.calculate_all()
        summary = result["executive_summary"]

        assert "total_year_1_cost" in summary
        assert "total_year_3_cost" in summary
        assert "total_year_5_cost" in summary
        assert "primary_cost_drivers" in summary
        assert "key_recommendations" in summary
        assert "cost_confidence" in summary

    def test_component_analysis_with_components(self, basic_projection):
        """Test component analysis with actual components."""
        component = ComponentCostData(
            component="Auth Service",
            description="Third-party auth",
            decision=DecisionType.BUY,
            service_name="Auth0",
            monthly_ongoing=99.0,
        )
        basic_projection.components.append(component)

        result = basic_projection.calculate_all()
        analysis = result["component_analysis"]

        assert len(analysis) == 1
        assert analysis[0]["component"] == "Auth Service"
        assert analysis[0]["decision"] == "buy"
        assert analysis[0]["service"] == "Auth0"

    def test_ai_projection_with_features(self, basic_projection):
        """Test AI projection with features."""
        feature = AITokenCostProjection(
            feature="Search",
            model="claude-sonnet",
            avg_input_tokens=500,
            avg_output_tokens=1000,
            requests_per_user_monthly=10,
        )
        basic_projection.ai_features.append(feature)

        result = basic_projection.calculate_all()
        ai_proj = result["ai_token_projection"]

        assert "projections" in ai_proj
        assert "year_1" in ai_proj["projections"]
        assert "year_3" in ai_proj["projections"]
        assert "year_5" in ai_proj["projections"]

    def test_ai_projection_empty_features(self, basic_projection):
        """Test AI projection with no features."""
        result = basic_projection.calculate_all()
        ai_proj = result["ai_token_projection"]

        assert "note" in ai_proj
        assert "No AI features" in ai_proj["note"]

    def test_infrastructure_projection_structure(self, basic_projection):
        """Test infrastructure projection has correct structure."""
        result = basic_projection.calculate_all()
        infra = result["infrastructure_projection"]

        assert "hosting" in infra
        assert "database" in infra
        assert "total_monthly_base" in infra
        assert "year_1_total" in infra
        assert "year_5_total" in infra

    def test_development_costs_structure(self, basic_projection):
        """Test development costs structure."""
        result = basic_projection.calculate_all()
        dev = result["development_costs"]

        assert "mvp_development" in dev
        assert "ongoing_development" in dev
        assert "year_1_total" in dev
        assert "year_5_total" in dev

    def test_total_cost_of_ownership_structure(self, basic_projection):
        """Test total cost of ownership structure."""
        result = basic_projection.calculate_all()
        tco = result["total_cost_of_ownership"]

        assert "year_1" in tco
        assert "year_3_cumulative" in tco
        assert "year_5_cumulative" in tco

    def test_cost_optimization_roadmap_structure(self, basic_projection):
        """Test cost optimization roadmap structure."""
        result = basic_projection.calculate_all()
        roadmap = result["cost_optimization_roadmap"]

        assert len(roadmap) >= 3  # At least 3 phases
        assert all("phase" in item for item in roadmap)
        assert all("focus" in item for item in roadmap)
        assert all("actions" in item for item in roadmap)

    def test_risk_adjusted_costs_structure(self, basic_projection):
        """Test risk-adjusted costs structure."""
        result = basic_projection.calculate_all()
        risk = result["risk_adjusted_costs"]

        assert "optimistic" in risk
        assert "expected" in risk
        assert "pessimistic" in risk

    def test_break_even_analysis_structure(self, basic_projection):
        """Test break-even analysis structure."""
        result = basic_projection.calculate_all()
        breakeven = result["break_even_analysis"]

        assert "required_mrr_to_cover_costs" in breakeven
        assert "users_needed_at_29_mo" in breakeven

    def test_vendor_lock_in_assessment_empty(self, basic_projection):
        """Test vendor lock-in assessment with no bought components."""
        result = basic_projection.calculate_all()
        vendor = result["vendor_lock_in_assessment"]

        assert isinstance(vendor, list)
        assert len(vendor) == 0

    def test_vendor_lock_in_assessment_with_components(self, basic_projection):
        """Test vendor lock-in assessment with bought components."""
        component = ComponentCostData(
            component="Payment Processing",
            decision=DecisionType.BUY,
            service_name="Stripe",
            vendor_lock_in_level=VendorLockInLevel.MEDIUM,
            migration_cost=1000.0,
            alternatives=["PayPal", "Square"],
        )
        basic_projection.components.append(component)

        result = basic_projection.calculate_all()
        vendor = result["vendor_lock_in_assessment"]

        assert len(vendor) == 1
        assert vendor[0]["vendor"] == "Stripe"
        assert vendor[0]["lock_in_level"] == "medium"

    def test_year_projections_increase_monotonically(self, basic_projection):
        """Test that year projections increase monotonically."""
        result = basic_projection.calculate_all()
        tco = result["total_cost_of_ownership"]

        year_1 = tco["year_1"]["total"]
        year_3 = tco["year_3_cumulative"]["total"]
        year_5 = tco["year_5_cumulative"]["total"]

        assert year_1 > 0
        assert year_3 >= year_1
        assert year_5 >= year_3


class TestCostEffectivenessAnalyzer:
    """Tests for CostEffectivenessAnalyzer main class."""

    @pytest.fixture
    def analyzer(self):
        """Create a CostEffectivenessAnalyzer instance."""
        return CostEffectivenessAnalyzer()

    def test_initialization(self, analyzer):
        """Test analyzer initialization."""
        assert analyzer.projection is None

    def test_analyze_basic(self, analyzer):
        """Test basic analysis without components."""
        result = analyzer.analyze(
            project_name="SimpleProject",
            build_vs_buy_results=[],
        )

        assert "executive_summary" in result
        assert "total_cost_of_ownership" in result
        assert analyzer.projection is not None
        assert analyzer.projection.project_name == "SimpleProject"

    def test_analyze_with_ai_features(self, analyzer):
        """Test analysis with AI features."""
        ai_features = [
            {
                "feature": "Search",
                "model": "claude-sonnet",
                "avg_input_tokens": 500,
                "avg_output_tokens": 1000,
                "requests_per_user_monthly": 10,
            }
        ]

        result = analyzer.analyze(
            project_name="AIProject",
            build_vs_buy_results=[],
            ai_features=ai_features,
        )

        ai_proj = result["ai_token_projection"]
        assert "projections" in ai_proj
        assert "year_1" in ai_proj["projections"]

    def test_analyze_with_custom_user_projections(self, analyzer):
        """Test analysis with custom user projections."""
        user_projections = {
            "year_1": 500,
            "year_3": 5000,
            "year_5": 25000,
        }

        result = analyzer.analyze(
            project_name="ScaledProject",
            build_vs_buy_results=[],
            user_projections=user_projections,
        )

        result["total_cost_of_ownership"]
        # With fewer users, costs should be lower
        assert analyzer.projection.year_1_users == 500

    def test_parse_cost_string_simple(self, analyzer):
        """Test parsing simple cost strings."""
        assert analyzer._parse_cost_string("$1,000") == 1000.0
        assert analyzer._parse_cost_string("$5,000.50") == 5000.50
        assert analyzer._parse_cost_string("100") == 100.0

    def test_parse_cost_string_range(self, analyzer):
        """Test parsing cost strings with ranges."""
        # Range should return average
        result = analyzer._parse_cost_string("$1,000-2,000")
        assert result == pytest.approx(1500.0)

    def test_parse_cost_string_empty(self, analyzer):
        """Test parsing empty cost strings."""
        assert analyzer._parse_cost_string("") == 0.0
        assert analyzer._parse_cost_string(None) == 0.0

    def test_parse_cost_string_invalid(self, analyzer):
        """Test parsing invalid cost strings."""
        assert analyzer._parse_cost_string("abc") == 0.0
        assert analyzer._parse_cost_string("no numbers here") == 0.0

    def test_generate_budget_anchor(self, analyzer):
        """Test budget anchor generation."""
        analyzer.analyze(
            project_name="BudgetProject",
            build_vs_buy_results=[],
        )

        anchor = analyzer.generate_budget_anchor()

        assert anchor["pivot_type"] == "BudgetCost"
        assert "budget_constraints" in anchor
        assert "cost_breakdown" in anchor
        assert "cost_optimization_strategies" in anchor

    def test_generate_budget_anchor_no_projection(self, analyzer):
        """Test budget anchor generation without projection."""
        anchor = analyzer.generate_budget_anchor()
        assert anchor == {}

    def test_to_json(self, analyzer, tmp_path):
        """Test saving analysis to JSON file."""
        analyzer.analyze(
            project_name="JSONProject",
            build_vs_buy_results=[],
        )

        json_file = tmp_path / "analysis.json"
        analyzer.to_json(str(json_file))

        assert json_file.exists()

        # Verify it's valid JSON
        with open(json_file, "r") as f:
            data = json.load(f)
            assert "executive_summary" in data

    def test_parse_component_build_decision(self, analyzer):
        """Test parsing component with build decision."""
        result = {
            "component": "Custom Auth",
            "description": "Custom authentication",
            "recommendation": {"choice": "build", "rationale": ["Custom logic needed"]},
            "cost_data": {"initial_cost": 5000, "monthly_ongoing": 500},
        }

        component = analyzer._parse_component(result)

        assert component is not None
        assert component.component == "Custom Auth"
        assert component.decision == DecisionType.BUILD

    def test_parse_component_buy_decision(self, analyzer):
        """Test parsing component with buy decision."""
        result = {
            "component": "Authentication",
            "recommendation": {
                "choice": "buy",
                "specific": "Auth0",
                "rationale": ["Industry standard"],
            },
            "cost_data": {"year_5_total": 10000},
            "vendor_lock_in": {"level": "high", "migration_cost": 5000},
            "is_core": False,
        }

        component = analyzer._parse_component(result)

        assert component is not None
        assert component.decision == DecisionType.BUY
        assert component.service_name == "Auth0"
        assert component.vendor_lock_in_level == VendorLockInLevel.HIGH

    def test_parse_component_invalid_decision(self, analyzer):
        """Test parsing component with invalid decision."""
        result = {
            "component": "Service",
            "recommendation": {"choice": "invalid_choice"},
        }

        component = analyzer._parse_component(result)

        assert component is not None
        assert component.decision == DecisionType.BUILD  # Falls back to BUILD

    def test_parse_component_invalid_lock_in_level(self, analyzer):
        """Test parsing component with invalid vendor lock-in level."""
        result = {
            "component": "Service",
            "vendor_lock_in": {"level": "invalid_level"},
        }

        component = analyzer._parse_component(result)

        assert component is not None
        assert component.vendor_lock_in_level == VendorLockInLevel.LOW  # Falls back to LOW

    def test_parse_component_error_handling(self, analyzer):
        """Test error handling in component parsing."""
        result = {
            "component": "Service",
            # Missing recommendation field - should handle gracefully
        }

        component = analyzer._parse_component(result)

        # Should return a component despite missing data
        assert component is not None
        assert component.component == "Service"


class TestCostEffectivenessIntegration:
    """Integration tests for cost effectiveness analysis."""

    def test_complete_analysis_with_multiple_components(self):
        """Test complete analysis with multiple components and AI features."""
        analyzer = CostEffectivenessAnalyzer()

        build_vs_buy_results = [
            {
                "component": "Database",
                "recommendation": {"choice": "buy", "specific": "AWS RDS"},
                "cost_data": {"initial_cost": 1000, "monthly_ongoing": 200},
                "is_core": False,
            },
            {
                "component": "Authentication",
                "recommendation": {"choice": "buy", "specific": "Auth0"},
                "cost_data": {"monthly_ongoing": 99},
                "vendor_lock_in": {"level": "high"},
                "is_core": False,
            },
        ]

        ai_features = [
            {
                "feature": "Recommendation Engine",
                "model": "claude-sonnet",
                "avg_input_tokens": 1000,
                "avg_output_tokens": 500,
                "requests_per_user_monthly": 5,
            }
        ]

        result = analyzer.analyze(
            project_name="CompleteProject",
            build_vs_buy_results=build_vs_buy_results,
            ai_features=ai_features,
            user_projections={"year_1": 1000, "year_3": 10000, "year_5": 50000},
        )

        # Verify all sections are present
        assert "executive_summary" in result
        assert "component_analysis" in result
        assert len(result["component_analysis"]) == 2
        assert "ai_token_projection" in result
        assert "projections" in result["ai_token_projection"]

        # Verify budget anchor
        anchor = analyzer.generate_budget_anchor()
        assert anchor["pivot_type"] == "BudgetCost"
        assert len(anchor["cost_optimization_strategies"]) > 0

    def test_analysis_consistency_across_calls(self):
        """Test that multiple analyses are consistent."""
        analyzer = CostEffectivenessAnalyzer()

        # First analysis
        result1 = analyzer.analyze(
            project_name="TestProject",
            build_vs_buy_results=[],
            user_projections={"year_1": 1000, "year_3": 10000, "year_5": 50000},
        )

        # Second analysis with same parameters
        result2 = analyzer.analyze(
            project_name="TestProject",
            build_vs_buy_results=[],
            user_projections={"year_1": 1000, "year_3": 10000, "year_5": 50000},
        )

        # Results should be identical
        assert (
            result1["executive_summary"]["total_year_1_cost"]
            == result2["executive_summary"]["total_year_1_cost"]
        )

    def test_cost_scales_with_users(self):
        """Test that costs scale appropriately with user projections."""
        analyzer1 = CostEffectivenessAnalyzer()
        analyzer2 = CostEffectivenessAnalyzer()

        # Both use same AI features to see scaling effect
        ai_features = [
            {
                "feature": "Analysis",
                "model": "claude-sonnet",
                "avg_input_tokens": 1000,
                "avg_output_tokens": 500,
                "requests_per_user_monthly": 5,
            }
        ]

        # Small scale
        result1 = analyzer1.analyze(
            project_name="SmallProject",
            build_vs_buy_results=[],
            ai_features=ai_features,
            user_projections={"year_1": 100, "year_3": 1000, "year_5": 5000},
        )

        # Large scale
        result2 = analyzer2.analyze(
            project_name="LargeProject",
            build_vs_buy_results=[],
            ai_features=ai_features,
            user_projections={"year_1": 10000, "year_3": 100000, "year_5": 500000},
        )

        # Larger scale should have higher costs due to AI usage
        cost1 = result1["total_cost_of_ownership"]["year_1"]["total"]
        cost2 = result2["total_cost_of_ownership"]["year_1"]["total"]

        # Cost2 should be larger due to more users triggering more AI requests
        assert cost2 > cost1


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_component_costs(self):
        """Test handling of components with zero costs."""
        projection = ProjectCostProjection(project_name="ZeroCostProject")
        component = ComponentCostData(component="Free Service")
        projection.components.append(component)

        result = projection.calculate_all()
        analysis = result["component_analysis"]

        assert analysis[0]["year_1_cost"] == 0.0
        assert analysis[0]["year_5_cost"] == 0.0

    def test_very_high_scaling_factor(self):
        """Test handling of very high scaling factors."""
        component = ComponentCostData(
            component="Expensive Service",
            scaling_model=ScalingModel.LINEAR,
            scaling_factor=1000.0,  # Very high
        )
        component.calculate_projections(
            year_1_users=100000, year_3_users=1000000, year_5_users=10000000
        )

        # Projections should be large but calculable
        assert component.year_5_total > component.year_1_total
        # year_5: initial=0 + (monthly=0 * 60) + (scaling_factor=1000 * users=10000000 * months=60)
        assert component.year_5_total == pytest.approx(1000.0 * 10000000 * 60)

    def test_floating_point_precision(self):
        """Test floating-point precision in calculations."""
        projection = AITokenCostProjection(
            feature="Precision Test",
            model="test",
            avg_input_tokens=333333,
            avg_output_tokens=333333,
            requests_per_user_monthly=1,
            input_price_per_million=0.001,
            output_price_per_million=0.001,
        )

        # Should not have rounding errors
        monthly_100 = projection.monthly_cost_for_users(100)
        monthly_1000 = projection.monthly_cost_for_users(1000)

        assert monthly_1000 == pytest.approx(monthly_100 * 10, rel=1e-6)
