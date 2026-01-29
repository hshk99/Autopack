"""Unit tests for IdeaParser module."""

import pytest

from autopack.research.idea_parser import (
    IdeaParser,
    ParsedIdea,
    ProjectType,
    RiskProfile,
)


class TestProjectTypeEnum:
    """Test suite for ProjectType enum."""

    def test_all_project_types_exist(self):
        """Test that all expected project types are defined."""
        assert ProjectType.ECOMMERCE == "ecommerce"
        assert ProjectType.TRADING == "trading"
        assert ProjectType.CONTENT == "content"
        assert ProjectType.AUTOMATION == "automation"
        assert ProjectType.OTHER == "other"

    def test_project_type_is_string_enum(self):
        """Test that ProjectType values are strings."""
        for project_type in ProjectType:
            assert isinstance(project_type.value, str)


class TestRiskProfileEnum:
    """Test suite for RiskProfile enum."""

    def test_all_risk_profiles_exist(self):
        """Test that all expected risk profiles are defined."""
        assert RiskProfile.HIGH == "high"
        assert RiskProfile.MEDIUM == "medium"
        assert RiskProfile.LOW == "low"

    def test_risk_profile_is_string_enum(self):
        """Test that RiskProfile values are strings."""
        for risk_profile in RiskProfile:
            assert isinstance(risk_profile.value, str)


class TestParsedIdea:
    """Test suite for ParsedIdea model."""

    def test_parsed_idea_required_fields(self):
        """Test creating ParsedIdea with required fields."""
        idea = ParsedIdea(
            title="Test Project",
            description="A test project description",
        )
        assert idea.title == "Test Project"
        assert idea.description == "A test project description"
        assert idea.raw_requirements == []
        assert idea.detected_project_type == ProjectType.OTHER
        assert idea.risk_profile == RiskProfile.MEDIUM
        assert idea.dependencies == []

    def test_parsed_idea_all_fields(self):
        """Test creating ParsedIdea with all fields."""
        idea = ParsedIdea(
            title="E-commerce Platform",
            description="An online shopping platform",
            raw_requirements=["User authentication", "Payment processing"],
            detected_project_type=ProjectType.ECOMMERCE,
            risk_profile=RiskProfile.MEDIUM,
            dependencies=["Stripe", "Auth0"],
            confidence_score=0.85,
            raw_text="Original raw text",
        )
        assert idea.title == "E-commerce Platform"
        assert len(idea.raw_requirements) == 2
        assert idea.detected_project_type == ProjectType.ECOMMERCE
        assert idea.risk_profile == RiskProfile.MEDIUM
        assert len(idea.dependencies) == 2
        assert idea.confidence_score == 0.85

    def test_confidence_score_bounds(self):
        """Test that confidence score is bounded between 0 and 1."""
        with pytest.raises(ValueError):
            ParsedIdea(
                title="Test",
                description="Test",
                confidence_score=1.5,
            )

        with pytest.raises(ValueError):
            ParsedIdea(
                title="Test",
                description="Test",
                confidence_score=-0.1,
            )


class TestIdeaParserBasic:
    """Test suite for basic IdeaParser functionality."""

    def test_parser_initialization(self):
        """Test IdeaParser initialization with defaults."""
        parser = IdeaParser()
        assert parser.llm_fallback_enabled is True
        assert parser.confidence_threshold == 0.7

    def test_parser_initialization_custom(self):
        """Test IdeaParser initialization with custom settings."""
        parser = IdeaParser(llm_fallback_enabled=False, confidence_threshold=0.5)
        assert parser.llm_fallback_enabled is False
        assert parser.confidence_threshold == 0.5

    def test_parse_empty_input(self):
        """Test parsing empty input returns empty list."""
        parser = IdeaParser()
        assert parser.parse("") == []
        assert parser.parse("   ") == []
        assert parser.parse(None) == []  # type: ignore

    def test_parse_single_returns_none_for_empty(self):
        """Test parse_single returns None for empty input."""
        parser = IdeaParser()
        assert parser.parse_single("") is None


class TestIdeaParserSingleProject:
    """Test suite for parsing single project ideas."""

    def test_parse_simple_idea(self):
        """Test parsing a simple idea."""
        parser = IdeaParser()
        raw_text = """
        # My Online Store

        Build an e-commerce platform for selling handmade crafts.

        - User registration and login
        - Product catalog with search
        - Shopping cart functionality
        - Payment processing with Stripe
        """

        ideas = parser.parse(raw_text)
        assert len(ideas) == 1

        idea = ideas[0]
        assert "online store" in idea.title.lower() or "store" in idea.title.lower()
        assert idea.detected_project_type == ProjectType.ECOMMERCE
        assert len(idea.raw_requirements) >= 2

    def test_parse_single_convenience_method(self):
        """Test parse_single convenience method."""
        parser = IdeaParser()
        raw_text = "Create a blog platform for tech writers with content management features."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.CONTENT


class TestProjectTypeDetection:
    """Test suite for project type detection."""

    def test_detect_ecommerce(self):
        """Test detection of e-commerce projects."""
        parser = IdeaParser()
        raw_text = """
        Build an online store with shopping cart, checkout, and payment integration.
        Users can browse products, add to cart, and complete purchases.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.ECOMMERCE

    def test_detect_trading(self):
        """Test detection of trading projects."""
        parser = IdeaParser()
        raw_text = """
        Create an algorithmic trading bot for cryptocurrency markets.
        Should support multiple exchanges, portfolio management, and automated trades.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.TRADING

    def test_detect_content(self):
        """Test detection of content projects."""
        parser = IdeaParser()
        raw_text = """
        Build a content management system for publishing blog posts and articles.
        Writers can create, edit, and publish content with rich text editing.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.CONTENT

    def test_detect_automation(self):
        """Test detection of automation projects."""
        parser = IdeaParser()
        raw_text = """
        Create a workflow automation tool that triggers tasks based on webhooks.
        Should support cron scheduling and CI/CD pipeline integration.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.AUTOMATION

    def test_detect_other_for_ambiguous(self):
        """Test that ambiguous projects get OTHER type."""
        parser = IdeaParser()
        raw_text = "Create something useful for users."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.detected_project_type == ProjectType.OTHER


class TestRiskProfileAssignment:
    """Test suite for risk profile assignment."""

    def test_trading_high_risk(self):
        """Test that trading projects get HIGH risk profile."""
        parser = IdeaParser()
        raw_text = "Build a stock trading platform with real-time market data."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.risk_profile == RiskProfile.HIGH

    def test_content_low_risk(self):
        """Test that content projects get LOW risk profile."""
        parser = IdeaParser()
        raw_text = "Create a simple blog publishing platform for writers."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.risk_profile == RiskProfile.LOW

    def test_ecommerce_medium_risk(self):
        """Test that e-commerce projects get MEDIUM risk profile."""
        parser = IdeaParser()
        raw_text = "Build an online store for selling digital products."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.risk_profile == RiskProfile.MEDIUM

    def test_high_risk_keywords_elevate_risk(self):
        """Test that high-risk keywords elevate the risk profile."""
        parser = IdeaParser()
        raw_text = """
        Create a content platform that handles sensitive personal data,
        credit card information, and requires GDPR compliance.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        # Should be elevated from LOW to at least MEDIUM due to keywords
        assert idea.risk_profile in [RiskProfile.MEDIUM, RiskProfile.HIGH]


class TestRequirementsExtraction:
    """Test suite for requirements extraction."""

    def test_extract_bullet_requirements(self):
        """Test extraction of bullet point requirements."""
        parser = IdeaParser()
        raw_text = """
        Project: Task Manager

        Requirements:
        - User authentication system
        - Task creation and editing
        - Due date reminders
        - Team collaboration features
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert len(idea.raw_requirements) >= 4
        assert any("authentication" in req.lower() for req in idea.raw_requirements)

    def test_extract_numbered_requirements(self):
        """Test extraction of numbered list requirements."""
        parser = IdeaParser()
        raw_text = """
        Build a note-taking app with:
        1. Rich text editing
        2. Folder organization
        3. Search functionality
        4. Cloud sync
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert len(idea.raw_requirements) >= 4

    def test_extract_modal_requirements(self):
        """Test extraction of requirements with modal verbs."""
        parser = IdeaParser()
        raw_text = """
        The system must support multiple users.
        It should have a responsive design.
        Users need to be able to export their data.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert len(idea.raw_requirements) >= 2


class TestMultiProjectParsing:
    """Test suite for parsing multi-project documents."""

    def test_parse_multiple_projects_with_headers(self):
        """Test parsing document with multiple projects using headers."""
        parser = IdeaParser()
        raw_text = """
        ## Project: E-commerce Store

        Build an online marketplace for local artisans to sell their products.

        - Product listings
        - Shopping cart
        - Payment processing

        ## Project: Blog Platform

        Create a blogging platform for food enthusiasts to share recipes.

        - Recipe creation
        - Photo galleries
        - Comments and ratings
        """

        ideas = parser.parse(raw_text)
        assert len(ideas) == 2

        # Verify first project
        ecommerce_idea = next(
            (i for i in ideas if i.detected_project_type == ProjectType.ECOMMERCE), None
        )
        assert ecommerce_idea is not None

        # Verify second project
        content_idea = next(
            (i for i in ideas if i.detected_project_type == ProjectType.CONTENT), None
        )
        assert content_idea is not None

    def test_parse_multiple_projects_with_separators(self):
        """Test parsing document with separator-delimited projects."""
        parser = IdeaParser()
        raw_text = """
        Trading Bot

        Create an automated trading system for forex markets.

        ---

        Content Aggregator

        Build a news aggregator that collects tech articles from various sources.
        """

        ideas = parser.parse(raw_text)
        assert len(ideas) == 2

    def test_parse_numbered_projects(self):
        """Test parsing document with numbered projects."""
        parser = IdeaParser()
        raw_text = """
        1. Project: Inventory System

        Track inventory levels for a warehouse.

        2. Project: Order Management

        Manage customer orders and shipments.
        """

        ideas = parser.parse(raw_text)
        assert len(ideas) == 2


class TestDependencyExtraction:
    """Test suite for dependency extraction."""

    def test_extract_api_dependencies(self):
        """Test extraction of API dependencies."""
        parser = IdeaParser()
        raw_text = """
        Build a payment system that integrates with Stripe API
        and uses Auth0 for authentication.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        deps_lower = [d.lower() for d in idea.dependencies]
        assert any("stripe" in d for d in deps_lower)

    def test_extract_service_integrations(self):
        """Test extraction of service integrations."""
        parser = IdeaParser()
        raw_text = """
        The application needs to connect to AWS S3 for storage
        and integration with Twilio for SMS notifications.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert len(idea.dependencies) >= 1


class TestConfidenceScore:
    """Test suite for confidence score calculation."""

    def test_high_confidence_for_complete_idea(self):
        """Test that well-formed ideas get high confidence."""
        parser = IdeaParser()
        raw_text = """
        # E-commerce Marketplace

        A comprehensive online marketplace for buying and selling handmade goods.
        Sellers can create storefronts, manage inventory, and process orders.
        Buyers can browse, purchase, and leave reviews.

        Requirements:
        - User registration and profiles
        - Product catalog with categories
        - Shopping cart and checkout
        - Payment processing
        - Order tracking
        - Review and rating system
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.confidence_score >= 0.7

    def test_lower_confidence_for_minimal_idea(self):
        """Test that minimal ideas get lower confidence."""
        parser = IdeaParser()
        raw_text = "Make an app."

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.confidence_score < 0.7


class TestHelperMethods:
    """Test suite for IdeaParser helper methods."""

    def test_get_supported_project_types(self):
        """Test getting list of supported project types."""
        parser = IdeaParser()
        types = parser.get_supported_project_types()

        assert len(types) == 5
        assert ProjectType.ECOMMERCE in types
        assert ProjectType.TRADING in types
        assert ProjectType.CONTENT in types
        assert ProjectType.AUTOMATION in types
        assert ProjectType.OTHER in types

    def test_get_risk_profile_for_type(self):
        """Test getting default risk profile for project type."""
        parser = IdeaParser()

        assert parser.get_risk_profile_for_type(ProjectType.TRADING) == RiskProfile.HIGH
        assert parser.get_risk_profile_for_type(ProjectType.CONTENT) == RiskProfile.LOW
        assert parser.get_risk_profile_for_type(ProjectType.ECOMMERCE) == RiskProfile.MEDIUM


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_unicode_content(self):
        """Test parsing content with unicode characters."""
        parser = IdeaParser()
        raw_text = """
        # Caf\u00e9 Management System

        Build a system for managing caf\u00e9 operations in M\u00fcnchen.

        - Menu management with \u20ac pricing
        - Customer \u2764\ufe0f loyalty program
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.title is not None

    def test_very_long_content(self):
        """Test parsing very long content."""
        parser = IdeaParser()
        raw_text = "Build an app. " * 1000

        idea = parser.parse_single(raw_text)
        assert idea is not None
        # Description should be truncated
        assert len(idea.description) <= 500

    def test_special_characters_in_title(self):
        """Test parsing content with special characters."""
        parser = IdeaParser()
        raw_text = """
        # AI-Powered Task Manager (v2.0) - Beta

        A task management app with AI features.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert idea.title is not None

    def test_mixed_formatting(self):
        """Test parsing content with mixed formatting styles."""
        parser = IdeaParser()
        raw_text = """
        ### Project Title

        **Description**: Build something amazing.

        *Requirements*:
        - First requirement
        * Second requirement
        1. Third requirement

        `Code examples` might be included.
        """

        idea = parser.parse_single(raw_text)
        assert idea is not None
        assert len(idea.raw_requirements) >= 3
