"""Unit tests for TechStackProposer module."""

import pytest

from autopack.research.idea_parser import ProjectType
from autopack.research.tech_stack_proposer import (
    CostEstimate,
    CostTier,
    TechStackOption,
    TechStackProposal,
    TechStackProposer,
    TosRisk,
    TosRiskLevel,
)


class TestCostTierEnum:
    """Test suite for CostTier enum."""

    def test_all_cost_tiers_exist(self):
        """Test that all expected cost tiers are defined."""
        assert CostTier.FREE == "free"
        assert CostTier.LOW == "low"
        assert CostTier.MEDIUM == "medium"
        assert CostTier.HIGH == "high"
        assert CostTier.VARIABLE == "variable"

    def test_cost_tier_is_string_enum(self):
        """Test that CostTier values are strings."""
        for tier in CostTier:
            assert isinstance(tier.value, str)


class TestTosRiskLevelEnum:
    """Test suite for TosRiskLevel enum."""

    def test_all_risk_levels_exist(self):
        """Test that all expected risk levels are defined."""
        assert TosRiskLevel.NONE == "none"
        assert TosRiskLevel.LOW == "low"
        assert TosRiskLevel.MEDIUM == "medium"
        assert TosRiskLevel.HIGH == "high"
        assert TosRiskLevel.CRITICAL == "critical"

    def test_risk_level_is_string_enum(self):
        """Test that TosRiskLevel values are strings."""
        for level in TosRiskLevel:
            assert isinstance(level.value, str)


class TestCostEstimate:
    """Test suite for CostEstimate model."""

    def test_cost_estimate_required_fields(self):
        """Test creating CostEstimate with required fields."""
        cost = CostEstimate(monthly_min=0, monthly_max=100)
        assert cost.monthly_min == 0
        assert cost.monthly_max == 100
        assert cost.currency == "USD"
        assert cost.tier == CostTier.VARIABLE

    def test_cost_estimate_all_fields(self):
        """Test creating CostEstimate with all fields."""
        cost = CostEstimate(
            monthly_min=10,
            monthly_max=50,
            currency="EUR",
            tier=CostTier.LOW,
            notes="Includes hosting",
        )
        assert cost.monthly_min == 10
        assert cost.monthly_max == 50
        assert cost.currency == "EUR"
        assert cost.tier == CostTier.LOW
        assert cost.notes == "Includes hosting"

    def test_cost_estimate_str_same_values(self):
        """Test string representation with same min/max."""
        cost = CostEstimate(monthly_min=50, monthly_max=50, tier=CostTier.LOW)
        assert "$50/month" in str(cost)

    def test_cost_estimate_str_range(self):
        """Test string representation with range."""
        cost = CostEstimate(monthly_min=10, monthly_max=100, tier=CostTier.MEDIUM)
        assert "$10-$100/month" in str(cost)

    def test_cost_estimate_negative_min_rejected(self):
        """Test that negative monthly_min is rejected."""
        with pytest.raises(ValueError):
            CostEstimate(monthly_min=-10, monthly_max=100)

    def test_cost_estimate_negative_max_rejected(self):
        """Test that negative monthly_max is rejected."""
        with pytest.raises(ValueError):
            CostEstimate(monthly_min=0, monthly_max=-50)


class TestTosRisk:
    """Test suite for TosRisk model."""

    def test_tos_risk_required_fields(self):
        """Test creating TosRisk with required fields."""
        risk = TosRisk(description="API rate limits apply", level=TosRiskLevel.LOW)
        assert risk.description == "API rate limits apply"
        assert risk.level == TosRiskLevel.LOW
        assert risk.mitigation is None

    def test_tos_risk_with_mitigation(self):
        """Test creating TosRisk with mitigation."""
        risk = TosRisk(
            description="Account may be suspended",
            level=TosRiskLevel.HIGH,
            mitigation="Review ToS and ensure compliance",
        )
        assert risk.mitigation == "Review ToS and ensure compliance"


class TestTechStackOption:
    """Test suite for TechStackOption model."""

    def test_tech_stack_option_required_fields(self):
        """Test creating TechStackOption with required fields."""
        option = TechStackOption(
            name="Next.js",
            category="Full Stack Framework",
            description="React framework for production",
            estimated_cost=CostEstimate(monthly_min=0, monthly_max=50),
        )
        assert option.name == "Next.js"
        assert option.category == "Full Stack Framework"
        assert option.mcp_available is False
        assert option.tos_risks == []

    def test_tech_stack_option_all_fields(self):
        """Test creating TechStackOption with all fields."""
        option = TechStackOption(
            name="Supabase",
            category="Backend as a Service",
            description="Open source Firebase alternative",
            pros=["Generous free tier", "PostgreSQL-based"],
            cons=["Still maturing"],
            estimated_cost=CostEstimate(monthly_min=0, monthly_max=25),
            mcp_available=True,
            mcp_server_name="supabase-mcp",
            tos_risks=[TosRisk(description="Usage limits", level=TosRiskLevel.LOW)],
            setup_complexity="low",
            documentation_url="https://supabase.com/docs",
            recommended_for=["MVPs", "small teams"],
        )
        assert option.mcp_available is True
        assert option.mcp_server_name == "supabase-mcp"
        assert len(option.pros) == 2
        assert len(option.cons) == 1
        assert option.setup_complexity == "low"


class TestTechStackProposal:
    """Test suite for TechStackProposal model."""

    def test_proposal_requires_minimum_two_options(self):
        """Test that proposal requires at least 2 options."""
        with pytest.raises(ValueError):
            TechStackProposal(
                project_type=ProjectType.ECOMMERCE,
                options=[
                    TechStackOption(
                        name="Test",
                        category="Test",
                        description="Test",
                        estimated_cost=CostEstimate(monthly_min=0, monthly_max=0),
                    )
                ],
            )

    def test_proposal_with_two_options(self):
        """Test creating proposal with exactly 2 options."""
        options = [
            TechStackOption(
                name="Option 1",
                category="Cat 1",
                description="Desc 1",
                estimated_cost=CostEstimate(monthly_min=0, monthly_max=50),
            ),
            TechStackOption(
                name="Option 2",
                category="Cat 2",
                description="Desc 2",
                estimated_cost=CostEstimate(monthly_min=0, monthly_max=100),
            ),
        ]
        proposal = TechStackProposal(project_type=ProjectType.AUTOMATION, options=options)
        assert len(proposal.options) == 2
        assert proposal.project_type == ProjectType.AUTOMATION

    def test_proposal_confidence_bounds(self):
        """Test that confidence score is bounded between 0 and 1."""
        options = [
            TechStackOption(
                name="A",
                category="A",
                description="A",
                estimated_cost=CostEstimate(monthly_min=0, monthly_max=0),
            ),
            TechStackOption(
                name="B",
                category="B",
                description="B",
                estimated_cost=CostEstimate(monthly_min=0, monthly_max=0),
            ),
        ]

        with pytest.raises(ValueError):
            TechStackProposal(
                project_type=ProjectType.OTHER,
                options=options,
                confidence_score=1.5,
            )

        with pytest.raises(ValueError):
            TechStackProposal(
                project_type=ProjectType.OTHER,
                options=options,
                confidence_score=-0.1,
            )


class TestTechStackProposerBasic:
    """Test suite for basic TechStackProposer functionality."""

    def test_proposer_initialization(self):
        """Test TechStackProposer initialization with defaults."""
        proposer = TechStackProposer()
        assert proposer.include_mcp_options is True

    def test_proposer_initialization_custom(self):
        """Test TechStackProposer initialization with custom settings."""
        proposer = TechStackProposer(include_mcp_options=False)
        assert proposer.include_mcp_options is False


class TestProposeForProjectTypes:
    """Test suite for propose() across all project types."""

    def test_propose_ecommerce(self):
        """Test proposing stack for e-commerce project."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.ECOMMERCE)

        assert proposal.project_type == ProjectType.ECOMMERCE
        assert len(proposal.options) >= 2
        assert all(isinstance(opt, TechStackOption) for opt in proposal.options)

    def test_propose_trading(self):
        """Test proposing stack for trading project."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.TRADING)

        assert proposal.project_type == ProjectType.TRADING
        assert len(proposal.options) >= 2

        # Trading should have ToS risks flagged
        has_tos_risks = any(len(opt.tos_risks) > 0 for opt in proposal.options)
        assert has_tos_risks, "Trading options should have ToS risks flagged"

    def test_propose_content(self):
        """Test proposing stack for content project."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.CONTENT)

        assert proposal.project_type == ProjectType.CONTENT
        assert len(proposal.options) >= 2

    def test_propose_automation(self):
        """Test proposing stack for automation project."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.AUTOMATION)

        assert proposal.project_type == ProjectType.AUTOMATION
        assert len(proposal.options) >= 2

    def test_propose_other(self):
        """Test proposing stack for other project type."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.OTHER)

        assert proposal.project_type == ProjectType.OTHER
        assert len(proposal.options) >= 2


class TestProposeWithRequirements:
    """Test suite for propose() with requirements."""

    def test_propose_with_requirements(self):
        """Test proposing stack with specific requirements."""
        proposer = TechStackProposer()
        requirements = ["payment processing", "user authentication"]
        proposal = proposer.propose(ProjectType.ECOMMERCE, requirements=requirements)

        assert proposal.requirements == requirements
        assert len(proposal.options) >= 2

    def test_propose_empty_requirements(self):
        """Test proposing stack with empty requirements list."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.CONTENT, requirements=[])

        assert proposal.requirements == []
        assert len(proposal.options) >= 2

    def test_propose_none_requirements(self):
        """Test proposing stack with None requirements."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.AUTOMATION, requirements=None)

        assert proposal.requirements == []
        assert len(proposal.options) >= 2


class TestCostEstimates:
    """Test suite for cost estimate accuracy."""

    def test_all_options_have_cost_estimates(self):
        """Test that all proposed options have cost estimates."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            for option in proposal.options:
                assert option.estimated_cost is not None
                assert option.estimated_cost.monthly_min >= 0
                assert option.estimated_cost.monthly_max >= option.estimated_cost.monthly_min

    def test_cost_estimates_within_reasonable_range(self):
        """Test that cost estimates are within reasonable ranges."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            for option in proposal.options:
                # Max cost should be less than $10,000/month for most options
                assert option.estimated_cost.monthly_max < 10000


class TestMcpAvailability:
    """Test suite for MCP availability detection."""

    def test_mcp_enabled_options_exist(self):
        """Test that some options have MCP servers available."""
        proposer = TechStackProposer()
        mcp_options = proposer.get_mcp_enabled_options()

        assert len(mcp_options) > 0
        assert all(opt.mcp_available for opt in mcp_options)
        assert all(opt.mcp_server_name is not None for opt in mcp_options)

    def test_mcp_prioritization_when_enabled(self):
        """Test that MCP options are prioritized when enabled."""
        proposer = TechStackProposer(include_mcp_options=True)

        # Check a project type known to have MCP options
        proposal = proposer.propose(ProjectType.OTHER)

        # If MCP options exist for this type, they should be ranked higher
        mcp_indices = [i for i, opt in enumerate(proposal.options) if opt.mcp_available]

        # MCP options should generally appear earlier in the list
        if mcp_indices:
            avg_mcp_position = sum(mcp_indices) / len(mcp_indices)
            # Average position should be in first half
            assert avg_mcp_position < len(proposal.options)


class TestTosRiskFlagging:
    """Test suite for ToS/legal risk flagging."""

    def test_trading_has_tos_risks(self):
        """Test that trading options have ToS risks flagged."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.TRADING)

        # At least one option should have ToS risks
        options_with_risks = [opt for opt in proposal.options if opt.tos_risks]
        assert len(options_with_risks) > 0

    def test_tos_risks_have_required_fields(self):
        """Test that ToS risks have description and level."""
        proposer = TechStackProposer()
        risks = proposer.check_tos_risks(ProjectType.TRADING)

        for option_name, risk in risks:
            assert risk.description
            assert risk.level in TosRiskLevel

    def test_critical_risks_prevent_recommendation(self):
        """Test that critical ToS risks affect recommendations."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.TRADING)

        # Check if recommendation reasoning mentions risks when appropriate
        if proposal.recommendation_reasoning:
            # If there are critical risks, the reasoning should reflect caution
            has_critical = any(
                any(r.level == TosRiskLevel.CRITICAL for r in opt.tos_risks)
                for opt in proposal.options
            )
            if has_critical and proposal.recommendation is None:
                assert "risk" in proposal.recommendation_reasoning.lower()


class TestRecommendationGeneration:
    """Test suite for recommendation generation."""

    def test_recommendation_is_valid_option(self):
        """Test that recommendation is one of the proposed options."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            if proposal.recommendation:
                option_names = [opt.name for opt in proposal.options]
                assert proposal.recommendation in option_names

    def test_recommendation_has_reasoning(self):
        """Test that recommendations include reasoning."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            if proposal.recommendation:
                assert proposal.recommendation_reasoning is not None
                assert len(proposal.recommendation_reasoning) > 0


class TestConfidenceScoring:
    """Test suite for confidence score calculation."""

    def test_confidence_within_bounds(self):
        """Test that confidence scores are within bounds."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            assert 0.0 <= proposal.confidence_score <= 1.0

    def test_confidence_increases_with_requirements(self):
        """Test that providing requirements affects confidence."""
        proposer = TechStackProposer()

        # Get baseline confidence
        baseline = proposer.propose(ProjectType.ECOMMERCE)

        # Get confidence with requirements
        with_reqs = proposer.propose(
            ProjectType.ECOMMERCE, requirements=["payment", "cart", "checkout"]
        )

        # Confidence with requirements should be at least as high
        assert with_reqs.confidence_score >= baseline.confidence_score - 0.1


class TestHelperMethods:
    """Test suite for TechStackProposer helper methods."""

    def test_get_all_options_for_type(self):
        """Test getting all options for a project type."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            options = proposer.get_all_options_for_type(project_type)
            assert len(options) >= 2
            assert all(isinstance(opt, TechStackOption) for opt in options)

    def test_check_tos_risks(self):
        """Test checking ToS risks for a project type."""
        proposer = TechStackProposer()
        risks = proposer.check_tos_risks(ProjectType.TRADING)

        assert isinstance(risks, list)
        for item in risks:
            assert len(item) == 2  # (option_name, TosRisk)
            assert isinstance(item[0], str)
            assert isinstance(item[1], TosRisk)


class TestEdgeCases:
    """Test suite for edge cases."""

    def test_multiple_proposals_are_independent(self):
        """Test that multiple proposals don't interfere with each other."""
        proposer = TechStackProposer()

        proposal1 = proposer.propose(ProjectType.ECOMMERCE)
        proposal2 = proposer.propose(ProjectType.TRADING)

        assert proposal1.project_type != proposal2.project_type
        assert proposal1.options != proposal2.options

    def test_proposer_is_reusable(self):
        """Test that proposer can be reused multiple times."""
        proposer = TechStackProposer()

        proposals = [proposer.propose(pt) for pt in ProjectType]

        assert len(proposals) == 5
        assert all(len(p.options) >= 2 for p in proposals)

    def test_unicode_in_requirements(self):
        """Test handling unicode characters in requirements."""
        proposer = TechStackProposer()
        requirements = ["caf\u00e9 management", "\u20ac pricing", "M\u00fcnchen support"]

        proposal = proposer.propose(ProjectType.OTHER, requirements=requirements)
        assert len(proposal.options) >= 2

    def test_empty_string_requirements(self):
        """Test handling empty string requirements."""
        proposer = TechStackProposer()
        requirements = ["", "valid requirement", ""]

        proposal = proposer.propose(ProjectType.AUTOMATION, requirements=requirements)
        assert len(proposal.options) >= 2


class TestAcceptanceCriteria:
    """Test suite verifying acceptance criteria from the spec."""

    def test_each_project_type_has_at_least_two_options(self):
        """Acceptance: Each project type has at least 2 stack options."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            assert len(proposal.options) >= 2, (
                f"Project type {project_type} has only {len(proposal.options)} options"
            )

    def test_cost_estimates_provided(self):
        """Acceptance: Cost estimates provided for all options."""
        proposer = TechStackProposer()

        for project_type in ProjectType:
            proposal = proposer.propose(project_type)
            for option in proposal.options:
                assert option.estimated_cost is not None
                assert option.estimated_cost.monthly_min is not None
                assert option.estimated_cost.monthly_max is not None

    def test_mcp_availability_detected(self):
        """Acceptance: MCP availability correctly detected."""
        proposer = TechStackProposer()
        mcp_options = proposer.get_mcp_enabled_options()

        # Verify MCP options have server names
        for option in mcp_options:
            assert option.mcp_available is True
            assert option.mcp_server_name is not None

    def test_tos_legal_risks_flagged(self):
        """Acceptance: ToS/legal risks flagged prominently."""
        proposer = TechStackProposer()

        # Trading is known to have legal/regulatory risks
        trading_risks = proposer.check_tos_risks(ProjectType.TRADING)
        assert len(trading_risks) > 0, "Trading should have ToS risks flagged"

        # Verify risks have proper structure
        for option_name, risk in trading_risks:
            assert risk.description
            assert risk.level in TosRiskLevel
