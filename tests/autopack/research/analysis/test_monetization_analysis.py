"""Tests for monetization analysis module.

Tests the MonetizationAnalyzer and related classes for generating
monetization recommendations for different project types.
"""

from autopack.research.analysis.budget_enforcement import BudgetEnforcer
from autopack.research.analysis.monetization_analysis import (
    MonetizationAnalysisResult,
    MonetizationAnalyzer,
    MonetizationModel,
    MonetizationModelFit,
    PricingStrategy,
    PricingTier,
    ProjectType,
    RevenueConfidence,
    RevenueProjection,
)


class TestPricingTier:
    """Tests for PricingTier dataclass."""

    def test_pricing_tier_creation(self):
        """Test basic PricingTier creation."""
        tier = PricingTier(
            name="Pro",
            price_monthly=49.0,
            price_yearly=490.0,
            features=["Feature A", "Feature B"],
            limits={"users": 10},
            target_audience="Growing teams",
        )

        assert tier.name == "Pro"
        assert tier.price_monthly == 49.0
        assert tier.price_yearly == 490.0
        assert len(tier.features) == 2
        assert tier.limits["users"] == 10

    def test_yearly_discount_calculation(self):
        """Test yearly discount percentage calculation."""
        tier = PricingTier(
            name="Pro",
            price_monthly=50.0,
            price_yearly=500.0,  # 2 months free
        )

        # Expected discount: (600 - 500) / 600 * 100 = 16.67%
        assert abs(tier.yearly_discount_percent - 16.67) < 0.1

    def test_yearly_discount_no_yearly_price(self):
        """Test yearly discount when no yearly price."""
        tier = PricingTier(name="Basic", price_monthly=10.0)
        assert tier.yearly_discount_percent == 0.0

    def test_to_dict(self):
        """Test PricingTier serialization."""
        tier = PricingTier(
            name="Starter",
            price_monthly=19.0,
            price_yearly=190.0,
            features=["Core features"],
            limits={"projects": 5},
            target_audience="Individuals",
            recommended=True,
        )

        data = tier.to_dict()
        assert data["name"] == "Starter"
        assert data["price_monthly"] == 19.0
        assert data["recommended"] is True
        assert "yearly_discount_percent" in data


class TestRevenueProjection:
    """Tests for RevenueProjection dataclass."""

    def test_revenue_projection_creation(self):
        """Test basic RevenueProjection creation."""
        projection = RevenueProjection(
            timeframe="year_1",
            users=5000,
            paying_users=150,
            mrr=4500.0,
            arr=54000.0,
            assumptions=["3% conversion rate"],
            confidence=RevenueConfidence.MEDIUM,
        )

        assert projection.timeframe == "year_1"
        assert projection.users == 5000
        assert projection.paying_users == 150
        assert projection.mrr == 4500.0

    def test_conversion_rate_calculation(self):
        """Test conversion rate property."""
        projection = RevenueProjection(
            timeframe="year_1",
            users=1000,
            paying_users=50,
            mrr=1500.0,
            arr=18000.0,
        )

        assert projection.conversion_rate == 5.0  # 50/1000 * 100

    def test_conversion_rate_zero_users(self):
        """Test conversion rate with zero users."""
        projection = RevenueProjection(
            timeframe="year_1",
            users=0,
            paying_users=0,
            mrr=0.0,
            arr=0.0,
        )

        assert projection.conversion_rate == 0.0


class TestMonetizationModelFit:
    """Tests for MonetizationModelFit dataclass."""

    def test_model_fit_creation(self):
        """Test MonetizationModelFit creation."""
        fit = MonetizationModelFit(
            model=MonetizationModel.SUBSCRIPTION,
            fit_score=8.5,
            pros=["Predictable revenue"],
            cons=["Churn risk"],
            requirements=["Billing system"],
        )

        assert fit.model == MonetizationModel.SUBSCRIPTION
        assert fit.fit_score == 8.5
        assert len(fit.pros) == 1
        assert len(fit.cons) == 1

    def test_to_dict(self):
        """Test serialization."""
        fit = MonetizationModelFit(
            model=MonetizationModel.FREEMIUM,
            fit_score=7.0,
        )

        data = fit.to_dict()
        assert data["model"] == "freemium"
        assert data["fit_score"] == 7.0


class TestMonetizationAnalysisResult:
    """Tests for MonetizationAnalysisResult dataclass."""

    def test_result_creation(self):
        """Test MonetizationAnalysisResult creation."""
        result = MonetizationAnalysisResult(
            project_type=ProjectType.AUTOMATION,
            recommended_model=MonetizationModel.SUBSCRIPTION,
            pricing_strategy=PricingStrategy.VALUE_BASED,
        )

        assert result.project_type == ProjectType.AUTOMATION
        assert result.recommended_model == MonetizationModel.SUBSCRIPTION
        assert result.pricing_strategy == PricingStrategy.VALUE_BASED

    def test_to_dict(self):
        """Test serialization."""
        result = MonetizationAnalysisResult(
            project_type=ProjectType.ECOMMERCE,
            recommended_model=MonetizationModel.MARKETPLACE_COMMISSION,
            pricing_tiers=[
                PricingTier(name="Basic", price_monthly=0),
                PricingTier(name="Pro", price_monthly=29),
            ],
        )

        data = result.to_dict()
        assert data["project_type"] == "ecommerce"
        assert data["recommended_model"] == "marketplace_commission"
        assert len(data["pricing_tiers"]) == 2


class TestMonetizationAnalyzer:
    """Tests for MonetizationAnalyzer class."""

    def test_analyzer_creation(self):
        """Test basic analyzer creation."""
        analyzer = MonetizationAnalyzer()
        assert analyzer._budget_enforcer is None
        assert analyzer._analysis_result is None

    def test_analyzer_with_budget_enforcer(self):
        """Test analyzer with budget enforcer."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)

        assert analyzer._budget_enforcer is budget_enforcer

    def test_can_analyze_without_budget(self):
        """Test can_analyze without budget enforcer."""
        analyzer = MonetizationAnalyzer()
        assert analyzer.can_analyze() is True

    def test_can_analyze_with_sufficient_budget(self):
        """Test can_analyze with sufficient budget."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)

        assert analyzer.can_analyze() is True

    def test_can_analyze_with_exhausted_budget(self):
        """Test can_analyze with exhausted budget."""
        budget_enforcer = BudgetEnforcer(total_budget=100.0)
        # Exhaust the budget
        budget_enforcer.record_cost("previous_analysis", 100.0)

        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)
        assert analyzer.can_analyze() is False

    def test_analyze_saas_project(self):
        """Test analysis for SaaS project type."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        assert result.project_type == ProjectType.AUTOMATION
        # SaaS should recommend subscription
        assert result.recommended_model == MonetizationModel.SUBSCRIPTION
        assert len(result.pricing_tiers) > 0
        assert len(result.revenue_projections) > 0

    def test_analyze_ecommerce_project(self):
        """Test analysis for e-commerce project type."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.ECOMMERCE)

        assert result.project_type == ProjectType.ECOMMERCE
        # E-commerce should recommend marketplace commission
        assert result.recommended_model == MonetizationModel.MARKETPLACE_COMMISSION

    def test_analyze_content_project(self):
        """Test analysis for content project type."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.CONTENT)

        assert result.project_type == ProjectType.CONTENT
        # Content should recommend subscription or advertising
        assert result.recommended_model in [
            MonetizationModel.SUBSCRIPTION,
            MonetizationModel.ADVERTISING,
        ]

    def test_analyze_api_service_project(self):
        """Test analysis for API service project type."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        assert result.project_type == ProjectType.AUTOMATION
        # Automation/API services recommend subscription as primary model
        assert result.recommended_model == MonetizationModel.SUBSCRIPTION

    def test_analyze_with_project_characteristics(self):
        """Test analysis with project characteristics."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            project_characteristics={
                "has_api": True,
                "is_b2b": True,
                "has_free_tier": True,
            },
        )

        assert result.project_type == ProjectType.AUTOMATION
        # Should have analyzed model fits
        assert len(result.model_fits) > 0

    def test_analyze_with_competitive_data(self):
        """Test analysis with competitive data."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            competitive_data={
                "competitors": [
                    {
                        "name": "Competitor A",
                        "pricing_model": "subscription",
                        "price_range": "$29-99/month",
                        "key_features": ["Feature 1", "Feature 2"],
                        "market_position": "leader",
                    },
                    {
                        "name": "Competitor B",
                        "pricing_model": "freemium",
                        "price_range": "Free-$49/month",
                        "key_features": ["Feature X"],
                        "market_position": "challenger",
                    },
                ]
            },
        )

        assert len(result.competitor_pricing) == 2
        assert result.competitor_pricing[0].competitor_name == "Competitor A"
        assert result.market_positioning != ""

    def test_analyze_pricing_tiers_generated(self):
        """Test that pricing tiers are generated."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should generate at least 2 tiers
        assert len(result.pricing_tiers) >= 2

        # Should have a recommended tier
        recommended = [t for t in result.pricing_tiers if t.recommended]
        assert len(recommended) == 1

    def test_analyze_revenue_projections(self):
        """Test that revenue projections are generated."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should have projections for multiple timeframes
        assert len(result.revenue_projections) >= 2

        # Projections should have increasing users over time
        timeframes = [p.timeframe for p in result.revenue_projections]
        assert "month_6" in timeframes or "year_1" in timeframes

    def test_analyze_budget_recording(self):
        """Test that analysis cost is recorded to budget."""
        budget_enforcer = BudgetEnforcer(total_budget=1000.0)
        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)

        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should have recorded the analysis cost
        assert result.analysis_cost > 0
        assert budget_enforcer.metrics.total_spent > 0

    def test_analyze_budget_insufficient(self):
        """Test analysis with insufficient budget returns minimal result."""
        budget_enforcer = BudgetEnforcer(total_budget=50.0)
        budget_enforcer.record_cost("previous", 50.0)  # Exhaust budget

        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should return minimal result
        assert result.confidence == RevenueConfidence.SPECULATIVE
        assert "budget" in result.key_assumptions[0].lower()

    def test_detect_project_type_saas(self):
        """Test project type detection for SaaS keywords."""
        analyzer = MonetizationAnalyzer()

        project_type = analyzer._detect_project_type(
            {
                "keywords": ["saas", "cloud", "software"],
                "features": ["user management", "analytics"],
                "description": "A cloud-based tool for teams",
            }
        )

        assert project_type == ProjectType.AUTOMATION

    def test_detect_project_type_ecommerce(self):
        """Test project type detection for e-commerce keywords."""
        analyzer = MonetizationAnalyzer()

        project_type = analyzer._detect_project_type(
            {
                "keywords": ["shop", "store", "products"],
                "description": "An online store for selling products with shopping cart",
            }
        )

        assert project_type == ProjectType.ECOMMERCE

    def test_detect_project_type_api(self):
        """Test project type detection for API keywords."""
        analyzer = MonetizationAnalyzer()

        project_type = analyzer._detect_project_type(
            {
                "keywords": ["api", "sdk", "developer"],
                "description": "REST API for integration with third-party services",
            }
        )

        assert project_type == ProjectType.AUTOMATION

    def test_get_analysis_summary(self):
        """Test getting analysis summary."""
        analyzer = MonetizationAnalyzer()
        analyzer.analyze(project_type=ProjectType.AUTOMATION)

        summary = analyzer.get_analysis_summary()

        assert "project_type" in summary
        assert "recommended_model" in summary
        assert "target_arpu" in summary
        assert "confidence" in summary

    def test_get_analysis_summary_no_analysis(self):
        """Test getting summary without analysis."""
        analyzer = MonetizationAnalyzer()
        summary = analyzer.get_analysis_summary()

        assert "error" in summary

    def test_generate_research_findings(self):
        """Test generating research findings for artifact generator."""
        analyzer = MonetizationAnalyzer()
        analyzer.analyze(project_type=ProjectType.AUTOMATION)

        findings = analyzer.generate_research_findings()

        assert "overview" in findings
        assert "models" in findings
        assert "pricing_benchmarks" in findings
        assert "revenue_potential" in findings
        assert "recommended_model" in findings

    def test_pricing_strategy_value_based(self):
        """Test value-based pricing strategy determination."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            market_data={},
            competitive_data={"competitors": []},  # No competitors
        )

        # With no competitors, should use value-based pricing
        assert result.pricing_strategy == PricingStrategy.VALUE_BASED

    def test_pricing_strategy_competitive(self):
        """Test competitive pricing strategy determination."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            competitive_data={"competitors": [{"name": f"Competitor {i}"} for i in range(6)]},
        )

        # With many competitors, should use competitive pricing
        assert result.pricing_strategy == PricingStrategy.COMPETITIVE

    def test_confidence_assessment_high(self):
        """Test high confidence with all data available."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            market_data={"tam": "1B"},
            competitive_data={"competitors": [{"name": "Comp"}]},
            target_audience={"segment": "SMB"},
        )

        assert result.confidence == RevenueConfidence.HIGH

    def test_confidence_assessment_low(self):
        """Test low confidence with minimal data."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            market_data={"tam": "1B"},  # Only one data point
        )

        assert result.confidence == RevenueConfidence.LOW

    def test_target_arpu_calculation(self):
        """Test target ARPU calculation."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should have calculated ARPU
        assert result.target_arpu > 0

    def test_target_ltv_calculation(self):
        """Test target LTV calculation."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # LTV should be greater than ARPU
        assert result.target_ltv > result.target_arpu

    def test_risks_identified(self):
        """Test that risks are identified."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should identify at least some risks
        assert len(result.risks) > 0

    def test_assumptions_identified(self):
        """Test that assumptions are identified."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Should identify assumptions
        assert len(result.key_assumptions) > 0
        # Should include the model assumption
        assert any("model" in a.lower() for a in result.key_assumptions)


class TestMonetizationIntegration:
    """Integration tests for monetization analysis."""

    def test_full_analysis_flow(self):
        """Test complete analysis flow with all inputs."""
        budget_enforcer = BudgetEnforcer(total_budget=5000.0)
        analyzer = MonetizationAnalyzer(budget_enforcer=budget_enforcer)

        result = analyzer.analyze(
            project_type=ProjectType.AUTOMATION,
            project_characteristics={
                "has_api": True,
                "is_b2b": True,
                "has_free_tier": True,
                "features": ["analytics", "reporting", "integrations"],
            },
            market_data={
                "tam": "10B",
                "growth_rate": "15%",
                "segments": ["SMB", "Enterprise"],
            },
            competitive_data={
                "competitors": [
                    {
                        "name": "Competitor A",
                        "pricing_model": "subscription",
                        "price_range": "$49-199/month",
                        "market_position": "leader",
                    },
                    {
                        "name": "Competitor B",
                        "pricing_model": "freemium",
                        "price_range": "Free-$99/month",
                        "market_position": "challenger",
                    },
                ]
            },
            target_audience={
                "primary_segment": "SMB",
                "decision_makers": ["CTO", "VP Engineering"],
                "pain_points": ["manual processes", "lack of visibility"],
            },
            cost_structure={
                "infrastructure": 500,
                "development": 5000,
                "marketing": 2000,
            },
        )

        # Verify comprehensive result
        assert result.project_type == ProjectType.AUTOMATION
        assert result.recommended_model in [
            MonetizationModel.SUBSCRIPTION,
            MonetizationModel.TIERED_PRICING,
        ]
        assert len(result.model_fits) >= 2
        assert len(result.pricing_tiers) >= 2
        assert len(result.revenue_projections) >= 2
        assert len(result.competitor_pricing) == 2
        assert result.confidence == RevenueConfidence.HIGH
        assert result.analysis_cost > 0

        # Verify budget was updated
        assert budget_enforcer.metrics.total_spent > 0

    def test_serialization_roundtrip(self):
        """Test that analysis result can be serialized and used."""
        analyzer = MonetizationAnalyzer()
        result = analyzer.analyze(project_type=ProjectType.AUTOMATION)

        # Convert to dict
        data = result.to_dict()

        # Verify all expected keys present
        expected_keys = [
            "project_type",
            "recommended_model",
            "model_fits",
            "pricing_strategy",
            "pricing_tiers",
            "revenue_projections",
            "target_arpu",
            "target_ltv",
            "confidence",
            "key_assumptions",
            "risks",
        ]

        for key in expected_keys:
            assert key in data, f"Missing key: {key}"

    def test_generate_findings_for_generator(self):
        """Test that generated findings work with MonetizationStrategyGenerator."""
        analyzer = MonetizationAnalyzer()
        analyzer.analyze(project_type=ProjectType.AUTOMATION)

        findings = analyzer.generate_research_findings()

        # Verify structure matches what MonetizationStrategyGenerator expects
        assert "overview" in findings
        assert isinstance(findings["models"], list)
        assert isinstance(findings["pricing_benchmarks"], dict)
        assert "recommended_model" in findings
        assert "model" in findings["recommended_model"]
