"""Smoke tests for all project type scenarios (IMP-BOOTSTRAP-001).

Tests that all project types mentioned in the Phase 1 README
(youtube, etsy, trading, dropshipping, creative-commerce, mobile)
are properly detected and processed through the bootstrap pipeline.
"""

import json

import pytest

from autopack.cli.commands.bootstrap import (
    READY_FOR_BUILD_MARKER,
    BootstrapOptions,
    BootstrapRunner,
)
from autopack.research.idea_parser import IdeaParser, ProjectType, RiskProfile

# ============================================================================
# Test Fixtures for Each Project Type
# ============================================================================


@pytest.fixture
def youtube_project_idea():
    """YouTube content creation project idea."""
    return """
    # YouTube Video Content Creator

    Build a YouTube video creation and publishing platform for content creators.

    ## Core Features
    - AI-powered video script generation
    - Text-to-speech for voiceovers
    - Video editing and assembly tools
    - Thumbnail generation with AI
    - Scheduled publishing to YouTube
    - Analytics tracking for video performance
    - Content calendar for creators

    ## Integrations
    - YouTube Data API for video uploads
    - OpenAI for content script generation
    - ElevenLabs for voice synthesis
    """


@pytest.fixture
def etsy_project_idea():
    """Etsy e-commerce automation project idea."""
    return """
    # Etsy Listing Automation Tool

    Create an AI-powered tool for managing Etsy shop listings.

    ## Features
    - Automated product listing creation
    - AI-generated product descriptions
    - SEO-optimized titles and tags
    - Inventory management integration
    - Order fulfillment tracking
    - Shop analytics dashboard
    - Bulk listing updates

    ## Requirements
    - Etsy Open API integration
    - Product image optimization
    - Shipping rate calculator
    """


@pytest.fixture
def trading_project_idea():
    """Trading/investment project idea."""
    return """
    # Crypto Trading Signal Bot

    Build an automated cryptocurrency trading signal system.

    ## Features
    - Real-time price monitoring across exchanges
    - Technical analysis indicators (RSI, MACD, Bollinger Bands)
    - Trading signal generation with confidence scores
    - Portfolio tracking and performance analytics
    - Risk management with position sizing
    - Backtesting engine for strategy validation
    - Notification system (Telegram, Discord)

    ## Integrations
    - Binance API
    - Coinbase Pro API
    - TradingView for charts
    """


@pytest.fixture
def dropshipping_project_idea():
    """Dropshipping e-commerce project idea."""
    return """
    # Automated Dropshipping Store

    Create an automated dropshipping business platform.

    ## Features
    - Product sourcing automation from suppliers
    - Automated store inventory sync
    - Order processing and fulfillment
    - Shipping tracking integration
    - Profit margin calculator
    - Supplier relationship management
    - Multi-channel selling (Shopify, Amazon, eBay)

    ## Requirements
    - Alibaba/AliExpress API integration
    - Shopify store management
    - Automated pricing rules
    """


@pytest.fixture
def creative_commerce_project_idea():
    """Creative commerce (content + e-commerce) project idea."""
    return """
    # AI Art Print Store

    Build a platform for creating and selling AI-generated art prints.

    ## Features
    - AI art generation with user prompts
    - Print-on-demand fulfillment integration
    - Online storefront for selling prints
    - Social media content scheduling
    - Customer gallery and collections
    - Licensing management for digital downloads
    - Creator collaboration marketplace

    ## Requirements
    - Stable Diffusion/DALL-E integration
    - Printful/Printify fulfillment
    - Stripe payment processing
    """


@pytest.fixture
def mobile_project_idea():
    """Mobile app project idea."""
    return """
    # Mobile Fitness Tracking App

    Build a comprehensive mobile fitness tracking application.

    ## Features
    - iOS and Android native apps
    - Workout logging and exercise library
    - Progress tracking with charts
    - Social features and challenges
    - Integration with wearables (Apple Watch, Fitbit)
    - Nutrition tracking and meal planning
    - Push notifications for reminders

    ## Technical Requirements
    - React Native or Flutter for cross-platform
    - Firebase for backend and auth
    - HealthKit/Google Fit integration
    """


# ============================================================================
# Project Type Detection Smoke Tests
# ============================================================================


class TestProjectTypeDetectionSmoke:
    """Smoke tests for project type detection across all mentioned types."""

    def test_youtube_project_detected_as_content(self, youtube_project_idea):
        """Test that YouTube project is detected as CONTENT type."""
        parser = IdeaParser()
        parsed = parser.parse_single(youtube_project_idea)

        assert parsed is not None
        # YouTube content projects should be CONTENT type
        assert parsed.detected_project_type == ProjectType.CONTENT
        assert parsed.confidence_score >= 0.5
        # YouTube content should have video/publish/content keywords detected
        assert any(
            kw in parsed.raw_text.lower() for kw in ["video", "publish", "content", "youtube"]
        )

    def test_etsy_project_detected_as_ecommerce(self, etsy_project_idea):
        """Test that Etsy project is detected as ECOMMERCE type."""
        parser = IdeaParser()
        parsed = parser.parse_single(etsy_project_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.ECOMMERCE
        assert parsed.confidence_score >= 0.6
        # Etsy projects should have shop/listing/product keywords
        assert any(
            kw in parsed.raw_text.lower() for kw in ["shop", "listing", "product", "inventory"]
        )

    def test_trading_project_detected_as_trading(self, trading_project_idea):
        """Test that trading project is detected as TRADING type with HIGH risk."""
        parser = IdeaParser()
        parsed = parser.parse_single(trading_project_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.TRADING
        assert parsed.risk_profile == RiskProfile.HIGH
        assert parsed.confidence_score >= 0.6

    def test_dropshipping_project_detected_as_ecommerce(self, dropshipping_project_idea):
        """Test that dropshipping project is detected as ECOMMERCE type."""
        parser = IdeaParser()
        parsed = parser.parse_single(dropshipping_project_idea)

        assert parsed is not None
        assert parsed.detected_project_type == ProjectType.ECOMMERCE
        assert parsed.confidence_score >= 0.6
        # Dropshipping should have shipping/order/store keywords
        assert any(kw in parsed.raw_text.lower() for kw in ["shipping", "order", "store", "sell"])

    def test_creative_commerce_detected_correctly(self, creative_commerce_project_idea):
        """Test that creative commerce project is detected (CONTENT or ECOMMERCE)."""
        parser = IdeaParser()
        parsed = parser.parse_single(creative_commerce_project_idea)

        assert parsed is not None
        # Creative commerce blends content and e-commerce, should be one of these
        assert parsed.detected_project_type in [ProjectType.CONTENT, ProjectType.ECOMMERCE]
        assert parsed.confidence_score >= 0.5

    def test_mobile_project_detection(self, mobile_project_idea):
        """Test that mobile project is detected with appropriate type."""
        parser = IdeaParser()
        parsed = parser.parse_single(mobile_project_idea)

        assert parsed is not None
        # Mobile projects may be OTHER or match a specific category
        assert parsed.detected_project_type in list(ProjectType)
        assert parsed.confidence_score >= 0.5
        # Should extract mobile-related requirements
        assert len(parsed.raw_requirements) > 0


# ============================================================================
# Full Pipeline Smoke Tests for Each Project Type
# ============================================================================


class TestFullPipelineProjectTypeSmoke:
    """End-to-end smoke tests for each project type through the bootstrap pipeline."""

    def test_youtube_project_full_pipeline(self, tmp_path, youtube_project_idea):
        """Test full pipeline for YouTube content project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "youtube_project",
        )

        result = runner.run(options)

        assert result.success, f"YouTube project pipeline failed: {result.errors}"
        assert result.project_dir.exists()
        assert result.anchor_path.exists()
        assert (result.project_dir / READY_FOR_BUILD_MARKER).exists()

        # Verify anchor content reflects content type
        anchor_data = json.loads(result.anchor_path.read_text())
        assert anchor_data["format_version"] == "v2"

        # Verify marker file
        marker_data = json.loads((result.project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data["status"] == "ready"
        assert marker_data["bootstrap_complete"] is True

    def test_etsy_project_full_pipeline(self, tmp_path, etsy_project_idea):
        """Test full pipeline for Etsy e-commerce project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=etsy_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "etsy_project",
        )

        result = runner.run(options)

        assert result.success, f"Etsy project pipeline failed: {result.errors}"
        assert result.project_dir.exists()
        assert result.anchor_path.exists()

        # Verify marker indicates e-commerce type
        marker_data = json.loads((result.project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data["project_type"] == "ecommerce"

    def test_trading_project_full_pipeline(self, tmp_path, trading_project_idea):
        """Test full pipeline for trading project with proper risk handling."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=trading_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "trading_project",
        )

        result = runner.run(options)

        assert result.success, f"Trading project pipeline failed: {result.errors}"
        assert result.parsed_idea.detected_project_type == ProjectType.TRADING
        assert result.parsed_idea.risk_profile == RiskProfile.HIGH

        # Verify high-risk handling
        marker_data = json.loads((result.project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data["project_type"] == "trading"

    def test_dropshipping_project_full_pipeline(self, tmp_path, dropshipping_project_idea):
        """Test full pipeline for dropshipping project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=dropshipping_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "dropshipping_project",
        )

        result = runner.run(options)

        assert result.success, f"Dropshipping project pipeline failed: {result.errors}"
        assert result.project_dir.exists()

        # Should be categorized as e-commerce
        assert result.parsed_idea.detected_project_type == ProjectType.ECOMMERCE

    def test_creative_commerce_project_full_pipeline(
        self, tmp_path, creative_commerce_project_idea
    ):
        """Test full pipeline for creative commerce project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=creative_commerce_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "creative_commerce_project",
        )

        result = runner.run(options)

        assert result.success, f"Creative commerce pipeline failed: {result.errors}"
        assert result.project_dir.exists()
        assert result.anchor_path.exists()

    def test_mobile_project_full_pipeline(self, tmp_path, mobile_project_idea):
        """Test full pipeline for mobile app project."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=mobile_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "mobile_project",
        )

        result = runner.run(options)

        assert result.success, f"Mobile project pipeline failed: {result.errors}"
        assert result.project_dir.exists()
        assert (result.project_dir / READY_FOR_BUILD_MARKER).exists()


# ============================================================================
# Cross-Project Type Consistency Tests
# ============================================================================


class TestProjectTypeConsistency:
    """Tests for consistent behavior across all project types."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "youtube_project_idea",
            "etsy_project_idea",
            "trading_project_idea",
            "dropshipping_project_idea",
            "creative_commerce_project_idea",
            "mobile_project_idea",
        ],
    )
    def test_all_projects_extract_requirements(self, fixture_name, request):
        """Test that all project types extract at least some requirements."""
        idea = request.getfixturevalue(fixture_name)
        parser = IdeaParser()
        parsed = parser.parse_single(idea)

        assert parsed is not None
        assert len(parsed.raw_requirements) >= 3, (
            f"{fixture_name} should extract at least 3 requirements, "
            f"got {len(parsed.raw_requirements)}"
        )

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "youtube_project_idea",
            "etsy_project_idea",
            "trading_project_idea",
            "dropshipping_project_idea",
            "creative_commerce_project_idea",
            "mobile_project_idea",
        ],
    )
    def test_all_projects_have_valid_title(self, fixture_name, request):
        """Test that all project types extract a valid title."""
        idea = request.getfixturevalue(fixture_name)
        parser = IdeaParser()
        parsed = parser.parse_single(idea)

        assert parsed is not None
        assert parsed.title is not None
        assert len(parsed.title) > 10
        assert not parsed.title.endswith("...")

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "youtube_project_idea",
            "etsy_project_idea",
            "trading_project_idea",
            "dropshipping_project_idea",
            "creative_commerce_project_idea",
            "mobile_project_idea",
        ],
    )
    def test_all_projects_have_description(self, fixture_name, request):
        """Test that all project types extract a description."""
        idea = request.getfixturevalue(fixture_name)
        parser = IdeaParser()
        parsed = parser.parse_single(idea)

        assert parsed is not None
        assert parsed.description is not None
        assert len(parsed.description) > 20


# ============================================================================
# Marker File Validation Tests
# ============================================================================


class TestMarkerFileProjectTypes:
    """Tests for READY_FOR_BUILD marker file across project types."""

    def test_marker_includes_correct_project_type_youtube(self, tmp_path, youtube_project_idea):
        """Test marker file includes correct project type for YouTube."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        # YouTube video content projects should be detected as CONTENT type
        assert marker_data["project_type"] == "content"

    def test_marker_includes_correct_project_type_etsy(self, tmp_path, etsy_project_idea):
        """Test marker file includes correct project type for Etsy."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=etsy_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        assert marker_data["project_type"] == "ecommerce"

    def test_marker_includes_correct_project_type_trading(self, tmp_path, trading_project_idea):
        """Test marker file includes correct project type for trading."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=trading_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        marker_data = json.loads(marker_path.read_text())

        assert marker_data["project_type"] == "trading"
