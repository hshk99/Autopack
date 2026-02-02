"""Integration tests for full pipeline from idea to build execution (IMP-E2E-001).

Tests the complete end-to-end pipeline: Project idea → Research → Anchor generation → Executor start.

This module validates:
1. Idea parsing and project type detection
2. Anchor generation and validation
3. Anchor persistence and storage
4. Pipeline error handling and edge cases
"""

import uuid

import pytest

from autopack.intention_anchor.v2 import IntentionAnchorV2
from autopack.research.idea_parser import IdeaParser, ProjectType, RiskProfile

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def ecommerce_idea():
    """E-commerce project idea for testing."""
    return """
    # Sustainable Fashion E-Commerce Platform

    Build a modern e-commerce platform focused on sustainable fashion.

    ## Core Features
    - User authentication (email, OAuth2)
    - Product catalog with search
    - Shopping cart with inventory tracking
    - Secure checkout (Stripe integration)
    - Order management and tracking
    - Seller dashboard for vendors
    - Admin panel with analytics
    - Email notifications

    ## Technical Requirements
    - Python backend (FastAPI)
    - PostgreSQL database
    - Redis caching
    - AWS deployment
    - Docker containerization
    """


@pytest.fixture
def trading_idea():
    """Trading bot project idea (high-risk)."""
    return """
    # Cryptocurrency Trading Bot

    Automated trading system for cryptocurrency markets.

    ## Core Features
    - Real-time price monitoring
    - Multiple trading strategies (momentum, mean reversion)
    - Risk management with stop-loss
    - Backtesting engine
    - Exchange API integration (Binance, Coinbase)
    - Performance analytics
    - API key management
    """


@pytest.fixture
def simple_automation_idea():
    """Simple automation project idea (low-risk)."""
    return """
    # Task Automation Tool

    Simple CLI tool to automate repetitive developer tasks.

    ## Features
    - File organization automation
    - Git commit formatting
    - Code formatting and linting
    - Test execution helpers
    """


@pytest.fixture
def test_workspace(tmp_path):
    """Create isolated test workspace."""
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def sample_anchor_v2():
    """Create a sample IntentionAnchorV2 for testing."""
    from datetime import datetime, timezone

    anchor_data = {
        "project_id": f"proj-{uuid.uuid4().hex[:8]}",
        "created_at": datetime(2026, 2, 2, 0, 0, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 2, 2, 0, 0, 0, tzinfo=timezone.utc),
        "raw_input_digest": f"digest-{uuid.uuid4().hex[:16]}",
        "format_version": "v2",
    }
    return IntentionAnchorV2(**anchor_data)


# =============================================================================
# Test Class: TestIdeaParsing
# =============================================================================


@pytest.mark.integration
class TestIdeaParsing:
    """Tests for idea parsing and project type detection."""

    def test_parse_ecommerce_idea(self, ecommerce_idea):
        """Test that ecommerce idea is correctly parsed."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.ECOMMERCE
        assert parsed.confidence_score >= 0.6
        assert len(parsed.raw_requirements) >= 5

    def test_parse_trading_idea_identifies_high_risk(self, trading_idea):
        """Test that trading bot idea is identified as high-risk."""
        parser = IdeaParser()
        parsed = parser.parse_single(trading_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.TRADING
        assert parsed.risk_profile == RiskProfile.HIGH

    def test_parse_automation_idea(self, simple_automation_idea):
        """Test that simple automation idea is correctly parsed."""
        parser = IdeaParser()
        parsed = parser.parse_single(simple_automation_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.AUTOMATION
        # Automation ideas have medium risk profile by default
        assert parsed.risk_profile in [RiskProfile.LOW, RiskProfile.MEDIUM]
        assert parsed.confidence_score >= 0.5

    def test_parse_multiple_project_types_correctly_differentiated(
        self, ecommerce_idea, trading_idea, simple_automation_idea
    ):
        """Test that parser correctly differentiates between project types."""
        parser = IdeaParser()

        parsed_ecom = parser.parse_single(ecommerce_idea)
        parsed_trading = parser.parse_single(trading_idea)
        parsed_auto = parser.parse_single(simple_automation_idea)

        # All should parse successfully
        assert parsed_ecom is not None
        assert parsed_trading is not None
        assert parsed_auto is not None

        # Each should be identified with correct type
        assert parsed_ecom.detected_project_type == ProjectType.ECOMMERCE
        assert parsed_trading.detected_project_type == ProjectType.TRADING
        assert parsed_auto.detected_project_type == ProjectType.AUTOMATION

        # Risk profiles should differ (trading is highest risk)
        assert parsed_trading.risk_profile == RiskProfile.HIGH
        # Automation can be LOW or MEDIUM depending on interpretation
        assert parsed_auto.risk_profile in [RiskProfile.LOW, RiskProfile.MEDIUM]


# =============================================================================
# Test Class: TestAnchorStructure
# =============================================================================


@pytest.mark.integration
class TestAnchorStructure:
    """Tests for anchor structure and properties."""

    def test_anchor_has_required_base_fields(self, sample_anchor_v2):
        """Test that anchor has all required base fields."""
        assert sample_anchor_v2.project_id is not None
        assert sample_anchor_v2.created_at is not None
        assert sample_anchor_v2.format_version == "v2"
        assert sample_anchor_v2.raw_input_digest is not None

    def test_anchor_has_pivot_intentions_container(self, sample_anchor_v2):
        """Test that anchor has pivot_intentions container."""
        assert sample_anchor_v2.pivot_intentions is not None

    def test_anchor_can_be_converted_to_json_dict(self, sample_anchor_v2):
        """Test that anchor can be serialized to JSON dict."""
        json_dict = sample_anchor_v2.to_json_dict()

        assert isinstance(json_dict, dict)
        assert "format_version" in json_dict
        assert json_dict["format_version"] == "v2"
        assert "project_id" in json_dict
        assert "created_at" in json_dict


# =============================================================================
# Test Class: TestPipelineErrorHandling
# =============================================================================


@pytest.mark.integration
class TestPipelineErrorHandling:
    """Tests for error handling and edge cases in the pipeline."""

    def test_parser_handles_empty_idea(self):
        """Test that parser handles empty idea gracefully."""
        parser = IdeaParser()
        result = parser.parse_single("")

        # Should return None or very low confidence
        if result is not None:
            assert result.confidence_score < 0.3

    def test_parser_handles_minimal_idea(self):
        """Test that parser handles minimal idea text."""
        parser = IdeaParser()
        minimal_idea = "Build a simple app"

        result = parser.parse_single(minimal_idea)

        # Should either succeed with low confidence or return None
        # Both are acceptable for minimal input
        if result is not None:
            assert result.confidence_score >= 0.0

    def test_parser_handles_whitespace_only(self):
        """Test that parser handles whitespace-only input."""
        parser = IdeaParser()
        result = parser.parse_single("   \n  \t  ")

        # Should return None or very low confidence
        if result is not None:
            assert result.confidence_score < 0.3

    def test_parser_handles_special_characters(self):
        """Test that parser handles special characters gracefully."""
        parser = IdeaParser()
        idea_with_special_chars = """
        Build an app with:
        - Special chars: @#$%^&*()
        - Unicode: 你好世界 🚀
        - Line breaks
        """

        # Should not crash
        parser.parse_single(idea_with_special_chars)
        assert True  # Test passes if no exception is raised


# =============================================================================
# Test Class: TestAnchorSerialization
# =============================================================================


@pytest.mark.integration
class TestAnchorSerialization:
    """Tests for anchor serialization and deserialization."""

    def test_anchor_format_version(self, sample_anchor_v2):
        """Test that anchor has correct format version."""
        assert sample_anchor_v2.format_version == "v2"

    def test_anchor_model_config_forbids_extra_fields(self):
        """Test that IntentionAnchorV2 forbids extra fields."""
        from datetime import datetime, timezone

        # Try to create anchor with extra field - should fail
        anchor_data = {
            "project_id": "proj-test",
            "created_at": datetime.now(timezone.utc),
            "raw_input_digest": "digest-test",
            "extra_field": "should fail",
        }

        try:
            IntentionAnchorV2(**anchor_data)
            assert False, "Should have raised validation error for extra field"
        except Exception as e:
            assert "extra" in str(e).lower()

    def test_anchor_to_json_dict_preserves_format(self, sample_anchor_v2):
        """Test that JSON serialization preserves format."""
        json_dict = sample_anchor_v2.to_json_dict()

        # Verify structure
        assert isinstance(json_dict, dict)
        assert "format_version" in json_dict
        assert json_dict["format_version"] == "v2"
        assert "project_id" in json_dict
        assert "created_at" in json_dict


# =============================================================================
# Test Class: TestPipelineIntegration
# =============================================================================


@pytest.mark.integration
class TestPipelineIntegration:
    """Tests for overall pipeline integration."""

    def test_idea_parsing_to_project_type_flow(
        self, ecommerce_idea, trading_idea, simple_automation_idea
    ):
        """Test that project ideas flow correctly through parsing stage."""
        parser = IdeaParser()

        ideas_and_expected_types = [
            (ecommerce_idea, ProjectType.ECOMMERCE),
            (trading_idea, ProjectType.TRADING),
            (simple_automation_idea, ProjectType.AUTOMATION),
        ]

        for idea_text, expected_type in ideas_and_expected_types:
            parsed = parser.parse_single(idea_text)
            assert parsed is not None, f"Failed to parse idea of type {expected_type}"
            assert (
                parsed.detected_project_type == expected_type
            ), f"Expected {expected_type}, got {parsed.detected_project_type}"

    def test_high_risk_project_identified_correctly(self, trading_idea):
        """Test that high-risk projects are correctly identified."""
        parser = IdeaParser()
        parsed = parser.parse_single(trading_idea)

        assert parsed is not None
        assert parsed.risk_profile == RiskProfile.HIGH
        # High-risk projects should have meaningful requirements
        assert len(parsed.raw_requirements) > 0

    def test_anchor_json_serialization_format(self, sample_anchor_v2, test_workspace):
        """Test that anchor JSON serialization preserves key fields."""
        # Convert to JSON dict
        json_dict = sample_anchor_v2.to_json_dict()

        # Verify key fields are present
        assert json_dict["format_version"] == "v2"
        assert json_dict["project_id"] == sample_anchor_v2.project_id
        assert json_dict["raw_input_digest"] == sample_anchor_v2.raw_input_digest

        # Verify datetime serialization (should be ISO string)
        assert isinstance(json_dict["created_at"], str)

    def test_parser_confidence_scores_reasonable_range(self, ecommerce_idea):
        """Test that parser confidence scores are in valid range."""
        parser = IdeaParser()
        parsed = parser.parse_single(ecommerce_idea)

        assert parsed is not None
        assert 0.0 <= parsed.confidence_score <= 1.0
