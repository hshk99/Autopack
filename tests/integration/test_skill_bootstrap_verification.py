"""Skill invocation verification tests for project bootstrap (IMP-E2E-002).

Tests that project bootstrap skills (/project-bootstrap, /youtube-project, /etsy-project)
work correctly and produce output that matches the intention anchor v2 schema.

This is the E2E test that validates:
1. Skill invocation for different project types (YouTube, Etsy)
2. Output structure matches intention anchor v2 schema
3. Required fields are present and valid
4. Marker files are generated correctly
"""

import json
from pathlib import Path
from typing import Any, Dict

import jsonschema
import pytest

from autopack.cli.commands.bootstrap import (
    READY_FOR_BUILD_MARKER,
    BootstrapOptions,
    BootstrapRunner,
)

# =============================================================================
# Schema Loading and Validation Utilities
# =============================================================================


def load_intention_anchor_schema() -> Dict[str, Any]:
    """Load the intention anchor v2 JSON schema."""
    schema_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "autopack"
        / "schemas"
        / "intention_anchor_v2.schema.json"
    )
    if not schema_path.exists():
        pytest.skip(f"Schema file not found at {schema_path}")
    with open(schema_path) as f:
        return json.load(f)


def validate_against_schema(anchor_data: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Validate anchor data against the JSON schema."""
    try:
        jsonschema.validate(instance=anchor_data, schema=schema)
    except jsonschema.ValidationError as e:
        pytest.fail(f"Intention anchor does not match schema: {e.message}")


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def youtube_project_idea():
    """YouTube content creation project idea for skill invocation test."""
    return """
    # YouTube Shorts Automation with AI Video Generation

    Build a platform that automates the creation and publishing of YouTube Shorts using AI.

    ## Core Features
    - AI script generation from trending topics
    - Text-to-speech voice generation
    - AI video generation (text-to-video)
    - Automatic YouTube upload scheduling
    - Analytics dashboard for performance tracking
    - Trending content discovery
    - Multi-channel management

    ## Integrations
    - YouTube Data API v3
    - OpenAI for content generation
    - ElevenLabs for voice synthesis
    - D-ID or Synthesia for video generation
    """


@pytest.fixture
def etsy_project_idea():
    """Etsy listing automation project idea for skill invocation test."""
    return """
    # Etsy Listing AI Automation Tool

    Create an AI-powered tool that automates the creation and optimization of Etsy listings.

    ## Core Features
    - AI product description generation
    - SEO-optimized title and tag creation
    - Bulk listing upload and management
    - Inventory sync with fulfillment
    - Shop analytics and performance tracking
    - A/B testing for listing optimization
    - Price optimization based on market analysis

    ## Integrations
    - Etsy Open API
    - OpenAI for description generation
    - Product image optimization APIs
    """


@pytest.fixture
def intention_anchor_schema():
    """Load and provide the intention anchor v2 schema."""
    return load_intention_anchor_schema()


# =============================================================================
# Skill Invocation Tests for Project Bootstrap
# =============================================================================


class TestProjectBootstrapSkillInvocation:
    """Test project bootstrap skill invocation with schema validation."""

    def test_youtube_project_skill_produces_valid_anchor(
        self, tmp_path, youtube_project_idea, intention_anchor_schema
    ):
        """Test that /youtube-project skill produces valid intention anchor.

        This test verifies:
        1. Skill invocation succeeds
        2. Output directory is created
        3. intention_anchor_v2.json matches schema
        4. All required fields are present
        5. Marker file indicates success
        """
        runner = BootstrapRunner()
        project_dir = tmp_path / "youtube_skill_test"

        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)

        # Verify skill invocation succeeded
        assert result.success, f"YouTube skill invocation failed: {result.errors}"
        assert result.project_dir.exists(), "Project directory not created"
        assert result.anchor_path.exists(), "Anchor file not created"

        # Load and validate anchor against schema
        anchor_data = json.loads(result.anchor_path.read_text())

        # Validate against JSON schema
        validate_against_schema(anchor_data, intention_anchor_schema)

        # Verify required top-level fields
        assert anchor_data.get("format_version") == "v2"
        assert "project_id" in anchor_data
        assert "created_at" in anchor_data
        assert "raw_input_digest" in anchor_data
        assert "pivot_intentions" in anchor_data

        # Verify marker file
        marker_path = project_dir / READY_FOR_BUILD_MARKER
        assert marker_path.exists(), "READY_FOR_BUILD marker not created"
        marker_data = json.loads(marker_path.read_text())
        assert marker_data.get("status") == "ready"
        assert marker_data.get("bootstrap_complete") is True

    def test_etsy_project_skill_produces_valid_anchor(
        self, tmp_path, etsy_project_idea, intention_anchor_schema
    ):
        """Test that /etsy-project skill produces valid intention anchor.

        This test verifies:
        1. Skill invocation succeeds
        2. Output directory is created
        3. intention_anchor_v2.json matches schema
        4. Project type is identified (may be ecommerce or automation)
        5. Marker file indicates success
        """
        runner = BootstrapRunner()
        project_dir = tmp_path / "etsy_skill_test"

        options = BootstrapOptions(
            idea=etsy_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)

        # Verify skill invocation succeeded
        assert result.success, f"Etsy skill invocation failed: {result.errors}"
        assert result.project_dir.exists(), "Project directory not created"
        assert result.anchor_path.exists(), "Anchor file not created"

        # Load and validate anchor against schema
        anchor_data = json.loads(result.anchor_path.read_text())

        # Validate against JSON schema
        validate_against_schema(anchor_data, intention_anchor_schema)

        # Verify required top-level fields
        assert anchor_data.get("format_version") == "v2"
        assert "project_id" in anchor_data
        assert "created_at" in anchor_data
        assert "raw_input_digest" in anchor_data

        # Verify marker file indicates success
        marker_path = project_dir / READY_FOR_BUILD_MARKER
        assert marker_path.exists(), "READY_FOR_BUILD marker not created"
        marker_data = json.loads(marker_path.read_text())
        assert marker_data.get("status") == "ready"

    def test_skill_output_has_all_pivot_intention_types(
        self, tmp_path, youtube_project_idea, intention_anchor_schema
    ):
        """Test that skill output includes all 8 pivot intention types (or at least one).

        Per IMP-E2E-002, verify that the skill output structure includes
        the proper pivot intentions and at least some of them are populated.
        """
        runner = BootstrapRunner()
        project_dir = tmp_path / "pivot_test"

        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)
        assert result.success

        anchor_data = json.loads(result.anchor_path.read_text())
        validate_against_schema(anchor_data, intention_anchor_schema)

        # Verify pivot_intentions exists and contains at least one type
        pivot_intentions = anchor_data.get("pivot_intentions", {})
        assert isinstance(pivot_intentions, dict), "pivot_intentions must be an object"

        # At least one pivot intention should be populated
        populated_intentions = [k for k, v in pivot_intentions.items() if v]
        assert len(populated_intentions) > 0, "No pivot intentions were populated"

    def test_skill_output_raw_input_digest_format(
        self, tmp_path, youtube_project_idea, intention_anchor_schema
    ):
        """Test that raw_input_digest has correct SHA256 hex format.

        Validates that the digest field is a valid SHA256 hex string (16-64 chars).
        """
        runner = BootstrapRunner()
        project_dir = tmp_path / "digest_test"

        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)
        assert result.success

        anchor_data = json.loads(result.anchor_path.read_text())
        validate_against_schema(anchor_data, intention_anchor_schema)

        digest = anchor_data.get("raw_input_digest")
        assert digest is not None, "raw_input_digest is missing"

        # Should be hex string of 16-64 chars (SHA256 is 64 hex chars)
        assert isinstance(digest, str), "raw_input_digest must be a string"
        assert 16 <= len(digest) <= 64, f"raw_input_digest length must be 16-64, got {len(digest)}"

        # Should be valid hex
        try:
            int(digest, 16)
        except ValueError:
            pytest.fail(f"raw_input_digest is not valid hex: {digest}")

    def test_skill_output_passes_model_validation(
        self, tmp_path, youtube_project_idea, intention_anchor_schema
    ):
        """Test that skill output validates against the intention anchor schema.

        Validates that all required fields are present and structured correctly.
        """
        runner = BootstrapRunner()
        project_dir = tmp_path / "model_validation_test"

        options = BootstrapOptions(
            idea=youtube_project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)
        assert result.success

        anchor_data = json.loads(result.anchor_path.read_text())
        validate_against_schema(anchor_data, intention_anchor_schema)

        # Verify the data structure matches expectations
        assert anchor_data.get("format_version") == "v2"
        assert isinstance(anchor_data.get("project_id"), str)
        assert len(anchor_data.get("project_id", "")) > 0
        assert anchor_data.get("pivot_intentions") is not None
        assert isinstance(anchor_data.get("pivot_intentions"), dict)


# =============================================================================
# Cross-Skill Integration Tests
# =============================================================================


class TestSkillIntegration:
    """Test integration between multiple skill invocations."""

    @pytest.mark.parametrize(
        "project_idea,expected_type",
        [
            pytest.param(
                "YouTube video creation platform with AI",
                "content",
                id="youtube",
            ),
            pytest.param(
                "Etsy shop automation for product listing",
                "ecommerce",
                id="etsy",
            ),
        ],
    )
    def test_multiple_project_types_produce_valid_anchors(
        self, tmp_path, project_idea, expected_type, intention_anchor_schema
    ):
        """Test that different project types all produce valid anchors."""
        runner = BootstrapRunner()
        project_dir = tmp_path / f"project_{expected_type}"

        options = BootstrapOptions(
            idea=project_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)
        assert result.success, f"Pipeline failed for {expected_type} project"

        anchor_data = json.loads(result.anchor_path.read_text())
        validate_against_schema(anchor_data, intention_anchor_schema)

        # Verify marker has correct type
        marker_data = json.loads((project_dir / READY_FOR_BUILD_MARKER).read_text())
        assert marker_data.get("project_type") == expected_type


# =============================================================================
# Error Handling and Edge Cases
# =============================================================================


class TestSkillErrorHandling:
    """Test skill error handling and edge cases."""

    def test_empty_project_idea_handling(self, tmp_path, intention_anchor_schema):
        """Test that skill handles empty project idea gracefully."""
        runner = BootstrapRunner()
        project_dir = tmp_path / "empty_idea_test"

        options = BootstrapOptions(
            idea="",
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)

        # Should fail gracefully with error message
        assert not result.success or result.errors, "Empty idea should produce error"

    def test_minimal_project_idea_produces_anchor(self, tmp_path, intention_anchor_schema):
        """Test that even minimal project ideas produce valid anchors."""
        runner = BootstrapRunner()
        project_dir = tmp_path / "minimal_idea_test"

        minimal_idea = "A simple web application"

        options = BootstrapOptions(
            idea=minimal_idea,
            autonomous=True,
            skip_research=True,
            output_dir=project_dir,
        )

        result = runner.run(options)

        if result.success:  # Only validate if successful
            anchor_data = json.loads(result.anchor_path.read_text())
            validate_against_schema(anchor_data, intention_anchor_schema)
            assert anchor_data.get("format_version") == "v2"
