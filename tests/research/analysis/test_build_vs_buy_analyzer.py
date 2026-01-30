"""
Tests for BuildVsBuyAnalyzer.

Covers:
- Basic analysis functionality
- Cost comparison calculations
- Risk assessment
- Multiple component analysis
- Edge cases and boundary conditions
"""

import pytest

from autopack.research.analysis.build_vs_buy_analyzer import (
    BuildVsBuyAnalysis,
    BuildVsBuyAnalyzer,
    ComponentRequirements,
    CostEstimate,
    DecisionRecommendation,
    RiskAssessment,
    RiskCategory,
    StrategicImportance,
    VendorOption,
)


@pytest.fixture
def analyzer():
    """Create a BuildVsBuyAnalyzer instance."""
    return BuildVsBuyAnalyzer(hourly_rate=100.0)


@pytest.fixture
def basic_requirements():
    """Create basic component requirements."""
    return ComponentRequirements(
        component_name="authentication",
        description="User authentication system",
        required_features=["login", "logout", "password_reset"],
        strategic_importance=StrategicImportance.SUPPORTING,
        team_expertise_level="medium",
    )


@pytest.fixture
def core_requirements():
    """Create requirements for a core differentiator."""
    return ComponentRequirements(
        component_name="recommendation_engine",
        description="AI-powered recommendation engine",
        required_features=["personalization", "real_time", "a_b_testing"],
        nice_to_have_features=["ml_feedback", "analytics"],
        strategic_importance=StrategicImportance.CORE_DIFFERENTIATOR,
        team_expertise_level="high",
    )


@pytest.fixture
def commodity_requirements():
    """Create requirements for a commodity component."""
    return ComponentRequirements(
        component_name="email_service",
        description="Transactional email delivery",
        required_features=["send", "templates", "tracking"],
        strategic_importance=StrategicImportance.COMMODITY,
        team_expertise_level="low",
        time_constraint_weeks=2.0,
    )


@pytest.fixture
def vendor_options():
    """Create sample vendor options."""
    return [
        VendorOption(
            name="Auth0",
            pricing_model="subscription",
            monthly_cost=200.0,
            initial_cost=0.0,
            features=["login", "logout", "password_reset", "mfa"],
            lock_in_risk="medium",
            integration_complexity="low",
            support_quality="high",
            documentation_quality="high",
        ),
        VendorOption(
            name="Firebase Auth",
            pricing_model="freemium",
            monthly_cost=50.0,
            initial_cost=0.0,
            features=["login", "logout"],
            lock_in_risk="high",
            integration_complexity="medium",
            support_quality="medium",
            documentation_quality="high",
        ),
    ]


class TestBuildVsBuyAnalyzerBasics:
    """Test basic analyzer functionality."""

    def test_analyzer_initialization(self, analyzer):
        """Test analyzer initializes with correct settings."""
        assert analyzer.hourly_rate == 100.0
        assert analyzer.COST_WEIGHT == 0.25
        assert analyzer.TIME_WEIGHT == 0.20

    def test_analyze_returns_analysis(self, analyzer, basic_requirements):
        """Test analyze method returns BuildVsBuyAnalysis."""
        result = analyzer.analyze(basic_requirements)

        assert isinstance(result, BuildVsBuyAnalysis)
        assert result.component == "authentication"
        assert result.recommendation in DecisionRecommendation

    def test_analyze_calculates_build_cost(self, analyzer, basic_requirements):
        """Test that build cost is calculated."""
        result = analyzer.analyze(basic_requirements)

        assert result.build_cost.initial_cost > 0
        assert result.build_cost.year_1_total > result.build_cost.initial_cost
        assert result.build_cost.year_5_total > result.build_cost.year_1_total

    def test_analyze_calculates_buy_cost(self, analyzer, basic_requirements, vendor_options):
        """Test that buy cost is calculated with vendor options."""
        result = analyzer.analyze(basic_requirements, vendor_options)

        assert result.buy_cost.monthly_recurring > 0
        assert result.buy_cost.year_1_total > 0
        assert result.buy_cost.year_5_total > result.buy_cost.year_1_total

    def test_analyze_provides_rationale(self, analyzer, basic_requirements):
        """Test that analysis includes rationale."""
        result = analyzer.analyze(basic_requirements)

        assert result.rationale
        assert len(result.rationale) > 20

    def test_analysis_to_dict_serialization(self, analyzer, basic_requirements):
        """Test analysis can be serialized to dictionary."""
        result = analyzer.analyze(basic_requirements)
        result_dict = result.to_dict()

        assert result_dict["component"] == "authentication"
        assert "recommendation" in result_dict
        assert "build_cost" in result_dict
        assert "buy_cost" in result_dict
        assert "risks" in result_dict


class TestRecommendationLogic:
    """Test recommendation decision logic."""

    def test_core_differentiator_favors_build(self, analyzer, core_requirements):
        """Test that core differentiators lean toward build."""
        result = analyzer.analyze(core_requirements)

        # Core differentiators with high expertise should favor build
        assert result.build_score >= result.buy_score - 10
        assert result.strategic_importance == StrategicImportance.CORE_DIFFERENTIATOR

    def test_commodity_favors_buy(self, analyzer, commodity_requirements, vendor_options):
        """Test that commodity components lean toward buy."""
        result = analyzer.analyze(commodity_requirements, vendor_options)

        # Commodity with tight timeline and low expertise should favor buy
        assert result.recommendation in [
            DecisionRecommendation.BUY,
            DecisionRecommendation.HYBRID,
        ]

    def test_tight_deadline_affects_recommendation(self, analyzer):
        """Test that tight deadlines influence recommendation."""
        requirements = ComponentRequirements(
            component_name="urgent_feature",
            description="Time-sensitive feature",
            required_features=["feature1", "feature2"],
            strategic_importance=StrategicImportance.SUPPORTING,
            time_constraint_weeks=1.0,  # Very tight deadline
        )
        vendor = VendorOption(
            name="QuickService",
            pricing_model="subscription",
            monthly_cost=300.0,
            integration_complexity="low",
        )

        result = analyzer.analyze(requirements, [vendor])

        # With very tight deadline and easy integration, should favor buy
        assert "time" in result.rationale.lower() or result.buy_score > result.build_score

    def test_high_expertise_affects_build_score(self, analyzer):
        """Test that high team expertise improves build score."""
        low_expertise = ComponentRequirements(
            component_name="test_component",
            required_features=["feature1"],
            team_expertise_level="low",
        )
        high_expertise = ComponentRequirements(
            component_name="test_component",
            required_features=["feature1"],
            team_expertise_level="high",
        )

        low_result = analyzer.analyze(low_expertise)
        high_result = analyzer.analyze(high_expertise)

        assert high_result.build_score > low_result.build_score

    def test_hybrid_recommendation_for_close_scores(self, analyzer):
        """Test that close scores can lead to hybrid recommendation."""
        requirements = ComponentRequirements(
            component_name="balanced_component",
            required_features=["feature1", "feature2"],
            strategic_importance=StrategicImportance.SUPPORTING,
            team_expertise_level="medium",
        )
        vendor = VendorOption(
            name="BalancedService",
            pricing_model="subscription",
            monthly_cost=100.0,
            integration_complexity="medium",
            lock_in_risk="low",
        )

        result = analyzer.analyze(requirements, [vendor])

        # If scores are close, hybrid might be recommended
        if abs(result.build_score - result.buy_score) < 10:
            assert result.recommendation == DecisionRecommendation.HYBRID


class TestCostComparison:
    """Test cost comparison functionality."""

    def test_cost_comparison_returns_breakdown(self, analyzer, basic_requirements, vendor_options):
        """Test cost comparison provides detailed breakdown."""
        comparison = analyzer.cost_comparison(basic_requirements, vendor_options)

        assert "cost_comparison" in comparison
        assert "build" in comparison["cost_comparison"]
        assert "buy" in comparison["cost_comparison"]
        assert "analysis" in comparison["cost_comparison"]

    def test_cost_comparison_includes_all_years(self, analyzer, basic_requirements):
        """Test cost comparison includes multi-year projections."""
        comparison = analyzer.cost_comparison(basic_requirements)

        build = comparison["cost_comparison"]["build"]
        assert "year_1" in build
        assert "year_3" in build
        assert "year_5" in build
        assert build["year_5"] >= build["year_3"] >= build["year_1"]

    def test_cost_comparison_calculates_savings(self, analyzer, basic_requirements, vendor_options):
        """Test cost comparison calculates savings."""
        comparison = analyzer.cost_comparison(basic_requirements, vendor_options)

        analysis = comparison["cost_comparison"]["analysis"]
        assert "year_1_savings_build" in analysis
        assert "year_5_savings_build" in analysis

    def test_break_even_calculation(self, analyzer, basic_requirements, vendor_options):
        """Test break-even point is calculated when applicable."""
        comparison = analyzer.cost_comparison(basic_requirements, vendor_options)

        analysis = comparison["cost_comparison"]["analysis"]
        # Break-even may or may not be applicable
        assert "break_even_months" in analysis


class TestRiskAssessment:
    """Test risk assessment functionality."""

    def test_risk_assessment_returns_risks(self, analyzer, basic_requirements, vendor_options):
        """Test risk assessment identifies risks."""
        risks = analyzer.risk_assessment(basic_requirements, vendor_options)

        assert isinstance(risks, list)
        for risk in risks:
            assert isinstance(risk, RiskAssessment)
            assert risk.category in RiskCategory
            assert risk.severity in ["low", "medium", "high", "critical"]

    def test_low_expertise_creates_technical_debt_risk(self, analyzer):
        """Test that low expertise creates technical debt risk."""
        requirements = ComponentRequirements(
            component_name="test",
            team_expertise_level="low",
        )

        risks = analyzer.risk_assessment(requirements)

        technical_debt_risks = [r for r in risks if r.category == RiskCategory.TECHNICAL_DEBT]
        assert len(technical_debt_risks) > 0
        assert technical_debt_risks[0].severity in ["high", "critical"]

    def test_tight_deadline_creates_time_risk(self, analyzer):
        """Test that tight deadline creates time-to-market risk."""
        requirements = ComponentRequirements(
            component_name="test",
            time_constraint_weeks=2.0,
        )

        risks = analyzer.risk_assessment(requirements)

        time_risks = [r for r in risks if r.category == RiskCategory.TIME_TO_MARKET]
        assert len(time_risks) > 0

    def test_high_lock_in_vendor_creates_risk(self, analyzer):
        """Test that high lock-in vendors create vendor lock-in risk."""
        requirements = ComponentRequirements(component_name="test")
        vendor = VendorOption(
            name="LockedInService",
            pricing_model="subscription",
            monthly_cost=100.0,
            lock_in_risk="high",
        )

        risks = analyzer.risk_assessment(requirements, [vendor])

        lock_in_risks = [r for r in risks if r.category == RiskCategory.VENDOR_LOCK_IN]
        assert len(lock_in_risks) > 0
        assert any(r.severity in ["high", "critical"] for r in lock_in_risks)

    def test_security_requirements_create_security_risk(self, analyzer):
        """Test that security requirements create security consideration."""
        requirements = ComponentRequirements(
            component_name="secure_component",
            security_requirements=["encryption", "audit_logging"],
        )

        risks = analyzer.risk_assessment(requirements)

        security_risks = [r for r in risks if r.category == RiskCategory.SECURITY]
        assert len(security_risks) > 0

    def test_compliance_requirements_create_compliance_risk(self, analyzer):
        """Test that compliance requirements create compliance consideration."""
        requirements = ComponentRequirements(
            component_name="compliant_component",
            compliance_requirements=["GDPR", "SOC2"],
        )

        risks = analyzer.risk_assessment(requirements)

        compliance_risks = [r for r in risks if r.category == RiskCategory.COMPLIANCE]
        assert len(compliance_risks) > 0


class TestMultipleComponentAnalysis:
    """Test analysis of multiple components."""

    def test_analyze_multiple_components(self, analyzer):
        """Test analyzing multiple components at once."""
        components = [
            ComponentRequirements(component_name="auth", required_features=["login"]),
            ComponentRequirements(component_name="email", required_features=["send"]),
            ComponentRequirements(component_name="storage", required_features=["upload"]),
        ]

        results = analyzer.analyze_multiple(components)

        assert len(results) == 3
        assert "auth" in results
        assert "email" in results
        assert "storage" in results

    def test_analyze_multiple_with_vendor_options(self, analyzer):
        """Test analyzing multiple components with vendor options."""
        components = [
            ComponentRequirements(component_name="auth"),
            ComponentRequirements(component_name="email"),
        ]
        vendor_map = {
            "auth": [VendorOption(name="Auth0", pricing_model="subscription", monthly_cost=100.0)],
            "email": [VendorOption(name="SendGrid", pricing_model="usage", monthly_cost=50.0)],
        }

        results = analyzer.analyze_multiple(components, vendor_map)

        assert all(isinstance(r, BuildVsBuyAnalysis) for r in results.values())

    def test_generate_summary_report(self, analyzer):
        """Test generating summary report for multiple analyses."""
        components = [
            ComponentRequirements(
                component_name="core_feature",
                strategic_importance=StrategicImportance.CORE_DIFFERENTIATOR,
                team_expertise_level="high",
            ),
            ComponentRequirements(
                component_name="commodity",
                strategic_importance=StrategicImportance.COMMODITY,
                time_constraint_weeks=2.0,
            ),
        ]
        vendor_map = {
            "commodity": [
                VendorOption(
                    name="Service",
                    pricing_model="subscription",
                    monthly_cost=50.0,
                    integration_complexity="low",
                )
            ],
        }

        analyses = analyzer.analyze_multiple(components, vendor_map)
        report = analyzer.generate_summary_report(analyses)

        assert "build_vs_buy_summary" in report
        summary = report["build_vs_buy_summary"]
        assert summary["total_components"] == 2
        assert "recommendations" in summary
        assert "estimated_5_year_costs" in summary


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_requirements(self, analyzer):
        """Test handling of minimal requirements."""
        requirements = ComponentRequirements(component_name="minimal")

        result = analyzer.analyze(requirements)

        assert result is not None
        assert result.component == "minimal"

    def test_no_vendor_options(self, analyzer, basic_requirements):
        """Test analysis with no vendor options uses defaults."""
        result = analyzer.analyze(basic_requirements, vendor_options=[])

        assert result.buy_cost.monthly_recurring > 0

    def test_many_features_affects_build_time(self, analyzer):
        """Test that many features increase build time estimate."""
        few_features = ComponentRequirements(
            component_name="simple",
            required_features=["feature1"],
        )
        many_features = ComponentRequirements(
            component_name="complex",
            required_features=["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"],
        )

        simple_result = analyzer.analyze(few_features)
        complex_result = analyzer.analyze(many_features)

        assert complex_result.build_time_weeks > simple_result.build_time_weeks

    def test_custom_build_hours_estimate(self, analyzer, basic_requirements):
        """Test using custom build hours estimate."""
        result = analyzer.analyze(basic_requirements, build_estimate_hours=200.0)

        expected_time = 200.0 / 40  # 5 weeks
        assert result.build_time_weeks == expected_time

    def test_budget_constraint_appears_in_factors(self, analyzer):
        """Test that budget constraint is captured in key factors."""
        requirements = ComponentRequirements(
            component_name="budgeted",
            budget_constraint=10000.0,
        )

        result = analyzer.analyze(requirements)

        assert any("budget" in f.lower() for f in result.key_factors)

    def test_confidence_is_reasonable(self, analyzer, basic_requirements):
        """Test that confidence is within expected range."""
        result = analyzer.analyze(basic_requirements)

        assert 0.0 <= result.confidence <= 1.0

    def test_scores_are_bounded(self, analyzer, basic_requirements):
        """Test that scores are bounded 0-100."""
        result = analyzer.analyze(basic_requirements)

        assert 0 <= result.build_score <= 100
        assert 0 <= result.buy_score <= 100


class TestCostEstimate:
    """Test CostEstimate dataclass."""

    def test_cost_estimate_creation(self):
        """Test CostEstimate can be created with all fields."""
        estimate = CostEstimate(
            initial_cost=5000.0,
            monthly_recurring=200.0,
            year_1_total=7400.0,
            year_3_total=12200.0,
            year_5_total=17000.0,
            cost_drivers=["Development time", "Maintenance"],
            assumptions=["No major rework"],
        )

        assert estimate.initial_cost == 5000.0
        assert estimate.monthly_recurring == 200.0
        assert len(estimate.cost_drivers) == 2


class TestVendorOption:
    """Test VendorOption dataclass."""

    def test_vendor_option_creation(self):
        """Test VendorOption can be created."""
        vendor = VendorOption(
            name="TestService",
            pricing_model="subscription",
            monthly_cost=150.0,
            features=["feature1", "feature2"],
            lock_in_risk="medium",
        )

        assert vendor.name == "TestService"
        assert vendor.monthly_cost == 150.0
        assert len(vendor.features) == 2

    def test_vendor_option_defaults(self):
        """Test VendorOption has sensible defaults."""
        vendor = VendorOption(
            name="MinimalVendor",
            pricing_model="usage",
            monthly_cost=50.0,
        )

        assert vendor.initial_cost == 0.0
        assert vendor.lock_in_risk == "medium"
        assert vendor.integration_complexity == "medium"
