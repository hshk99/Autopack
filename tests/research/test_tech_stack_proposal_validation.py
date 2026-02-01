"""Tests for tech stack proposal artifact validation (IMP-SCHEMA-001).

Tests ensure that tech stack proposal artifacts are properly validated
against the schema before being written to disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autopack.research.artifact_generators import (
    TechStackProposalValidator, get_tech_stack_proposal_validator)
from autopack.research.idea_parser import ProjectType
from autopack.research.tech_stack_proposer import TechStackProposer
from autopack.research.validators.artifact_validator import (ArtifactValidator,
                                                             ValidationError,
                                                             ValidationResult)


class TestArtifactValidator:
    """Test the core ArtifactValidator class."""

    def test_validator_loads_schema(self) -> None:
        """Test that validator successfully loads the schema."""
        validator = ArtifactValidator()
        assert validator._schema is not None
        assert (
            validator._schema.get("$id")
            == "https://autopack.dev/schemas/tech_stack_proposal.schema.json"
        )

    def test_validate_valid_tech_stack_proposal(self) -> None:
        """Test validation of a valid tech stack proposal."""
        validator = ArtifactValidator()

        valid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Shopify + Custom App",
                    "category": "Hosted E-commerce Platform",
                    "description": "Shopify with custom integrations",
                    "estimated_cost": {
                        "monthly_min": 29,
                        "monthly_max": 299,
                        "tier": "medium",
                    },
                },
                {
                    "name": "Custom Next.js + Stripe",
                    "category": "Custom Stack",
                    "description": "Self-hosted with modern tech",
                    "estimated_cost": {
                        "monthly_min": 0,
                        "monthly_max": 100,
                        "tier": "low",
                    },
                },
            ],
            "confidence_score": 0.85,
        }

        result = validator.validate(valid_proposal)
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_invalid_project_type(self) -> None:
        """Test validation fails with invalid project type."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "invalid_type",
            "options": [
                {
                    "name": "Option 1",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_insufficient_options(self) -> None:
        """Test validation fails with less than 2 options."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Option 1",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_missing_required_option_fields(self) -> None:
        """Test validation fails when option is missing required fields."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Option 1",
                    # Missing 'category' and 'description'
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_invalid_cost_range(self) -> None:
        """Test validation catches when min cost > max cost."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Expensive Option",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {
                        "monthly_min": 500,
                        "monthly_max": 100,  # Invalid: min > max
                    },
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        # Should have semantic validation error about cost range
        assert any("estimated_cost" in e.path and "monthly" in e.message for e in result.errors)

    def test_validate_invalid_recommendation(self) -> None:
        """Test validation fails when recommendation doesn't match any option."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Option 1",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
            "recommendation": "Non-existent Option",  # Invalid recommendation
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        assert any("recommendation" in e.path for e in result.errors)

    def test_validate_invalid_confidence_score(self) -> None:
        """Test validation fails with invalid confidence score."""
        validator = ArtifactValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Option 1",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
            "confidence_score": 1.5,  # Invalid: > 1.0
        }

        result = validator.validate(invalid_proposal)
        assert not result.is_valid
        assert any("confidence_score" in e.path for e in result.errors)

    def test_validate_critical_tos_risk_warning(self) -> None:
        """Test that critical ToS risks generate warnings."""
        validator = ArtifactValidator()

        proposal_with_critical_risk = {
            "project_type": "trading",
            "options": [
                {
                    "name": "CCXT + PostgreSQL",
                    "category": "Trading",
                    "description": "Trading stack",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 50},
                    "tos_risks": [
                        {
                            "description": "Regulatory compliance required",
                            "level": "critical",
                        }
                    ],
                },
                {
                    "name": "Option 2",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
            "recommendation": "CCXT + PostgreSQL",  # Recommended but has critical risk
        }

        result = validator.validate(proposal_with_critical_risk)
        # Should still be valid but with warnings
        assert result.is_valid
        assert len(result.warnings) > 0
        assert any("critical" in w.lower() for w in result.warnings)


class TestTechStackProposalValidator:
    """Test the TechStackProposalValidator convenience class."""

    def test_validate_tech_stack_proposal(self) -> None:
        """Test validating a tech stack proposal."""
        validator = TechStackProposalValidator()

        valid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Shopify",
                    "category": "Platform",
                    "description": "Hosted platform",
                    "estimated_cost": {"monthly_min": 29, "monthly_max": 299},
                },
                {
                    "name": "Custom",
                    "category": "Custom",
                    "description": "Custom stack",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        is_valid = validator.validate_tech_stack_proposal(valid_proposal)
        assert is_valid

    def test_validate_tech_stack_proposal_invalid(self) -> None:
        """Test that invalid proposals fail validation."""
        validator = TechStackProposalValidator()

        invalid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Only Option",
                    "category": "Category",
                    "description": "Description",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
                # Missing second option
            ],
        }

        is_valid = validator.validate_tech_stack_proposal(invalid_proposal)
        assert not is_valid

    def test_validate_before_write(self, tmp_path: Path) -> None:
        """Test validating before writing to disk."""
        validator = TechStackProposalValidator()
        artifact_path = tmp_path / "tech_stack_proposal.json"

        valid_proposal = {
            "project_type": "ecommerce",
            "options": [
                {
                    "name": "Shopify",
                    "category": "Platform",
                    "description": "Hosted",
                    "estimated_cost": {"monthly_min": 29, "monthly_max": 299},
                },
                {
                    "name": "Custom",
                    "category": "Custom",
                    "description": "Self-hosted",
                    "estimated_cost": {"monthly_min": 0, "monthly_max": 100},
                },
            ],
        }

        is_valid = validator.validate_before_write(valid_proposal, artifact_path)
        assert is_valid


class TestTechStackProposerIntegration:
    """Integration tests with TechStackProposer."""

    def test_tech_stack_proposer_output_validates(self) -> None:
        """Test that TechStackProposer output validates against schema."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.ECOMMERCE, requirements=["fast setup"])

        # Convert Pydantic model to dict
        proposal_dict = proposal.model_dump()

        validator = TechStackProposalValidator()
        is_valid = validator.validate_tech_stack_proposal(proposal_dict)
        assert is_valid

    def test_tech_stack_proposer_with_recommendation(self) -> None:
        """Test TechStackProposer with recommendation validates."""
        proposer = TechStackProposer()
        proposal = proposer.propose(ProjectType.TRADING)

        proposal_dict = proposal.model_dump()
        validator = TechStackProposalValidator()
        is_valid = validator.validate_tech_stack_proposal(proposal_dict)
        assert is_valid


class TestGetTechStackProposalValidator:
    """Test the convenience function."""

    def test_get_tech_stack_proposal_validator(self) -> None:
        """Test getting a validator instance."""
        validator = get_tech_stack_proposal_validator()
        assert isinstance(validator, TechStackProposalValidator)

    def test_get_validator_with_custom_schema_path(self, tmp_path: Path) -> None:
        """Test getting a validator with custom schema path."""
        # Note: This will fail if schema path doesn't exist, which is expected
        with pytest.raises(FileNotFoundError):
            get_tech_stack_proposal_validator(tmp_path / "nonexistent.json")


class TestValidationResult:
    """Test the ValidationResult dataclass."""

    def test_valid_result_summary(self) -> None:
        """Test summary for valid result."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        assert "Valid" in result.summary
        assert "error" not in result.summary.lower()

    def test_valid_result_with_warnings_summary(self) -> None:
        """Test summary for valid result with warnings."""
        result = ValidationResult(is_valid=True, errors=[], warnings=["Warning 1", "Warning 2"])
        assert "Valid" in result.summary
        assert "2" in result.summary

    def test_invalid_result_summary(self) -> None:
        """Test summary for invalid result."""
        errors = [
            ValidationError(path="field1", message="Error 1"),
            ValidationError(path="field2", message="Error 2"),
        ]
        result = ValidationResult(is_valid=False, errors=errors, warnings=[])
        assert "Invalid" in result.summary
        assert "2" in result.summary
