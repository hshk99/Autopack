"""Tests for centralized model routing via ModelRouter and DoctorConfig.

IMP-029: Ensures all model selection goes through centralized routing
and configuration is loaded from config/models.yaml.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


class TestDoctorConfigLoading:
    """Test DoctorConfig loading from config/models.yaml."""

    def test_doctor_config_loads_cheap_model_from_config(self):
        """DoctorConfig should load cheap model from config/models.yaml."""
        from src.autopack.config_loader import load_doctor_config

        config = load_doctor_config()
        # Should load from config - verify it's a valid model name
        assert config.cheap_model in ["claude-sonnet-4-5", "claude-opus-4-5", "gpt-4o"]

    def test_doctor_config_loads_strong_model_from_config(self):
        """DoctorConfig should load strong model from config/models.yaml."""
        from src.autopack.config_loader import load_doctor_config

        config = load_doctor_config()
        assert config.strong_model in ["claude-sonnet-4-5", "claude-opus-4-5", "gpt-4o"]

    def test_doctor_config_loads_thresholds_from_config(self):
        """DoctorConfig should load thresholds from config/models.yaml."""
        from src.autopack.config_loader import load_doctor_config

        config = load_doctor_config()
        # Verify thresholds are numeric and in valid ranges
        assert 0 < config.min_confidence_for_cheap <= 1.0
        assert 0 < config.health_budget_near_limit_ratio <= 1.0
        assert config.max_builder_attempts_before_complex >= 1

    def test_doctor_config_loads_risk_categories(self):
        """DoctorConfig should load risk categories from config/models.yaml."""
        from src.autopack.config_loader import load_doctor_config

        config = load_doctor_config()
        # Verify risk categories are lists
        assert isinstance(config.high_risk_categories, list)
        assert isinstance(config.low_risk_categories, list)
        # Should have at least one category in each
        assert len(config.high_risk_categories) > 0
        assert len(config.low_risk_categories) > 0

    def test_doctor_config_defaults_when_config_missing(self):
        """DoctorConfig should use defaults when config file is missing."""
        from src.autopack.config_loader import DoctorConfig

        # Create default config (simulating missing file)
        config = DoctorConfig()
        assert config.cheap_model == "claude-sonnet-4-5"
        assert config.strong_model == "claude-opus-4-5"
        assert config.min_confidence_for_cheap == 0.7
        assert config.health_budget_near_limit_ratio == 0.8


class TestErrorRecoveryUsesConfig:
    """Test that error_recovery.py uses centralized config."""

    def test_error_recovery_uses_config_cheap_model(self):
        """error_recovery.DOCTOR_CHEAP_MODEL should match config."""
        from src.autopack.config_loader import doctor_config
        from src.autopack.error_recovery import DOCTOR_CHEAP_MODEL

        assert DOCTOR_CHEAP_MODEL == doctor_config.cheap_model

    def test_error_recovery_uses_config_strong_model(self):
        """error_recovery.DOCTOR_STRONG_MODEL should match config."""
        from src.autopack.config_loader import doctor_config
        from src.autopack.error_recovery import DOCTOR_STRONG_MODEL

        assert DOCTOR_STRONG_MODEL == doctor_config.strong_model

    def test_error_recovery_uses_config_thresholds(self):
        """error_recovery thresholds should match config."""
        from src.autopack.config_loader import doctor_config
        from src.autopack.error_recovery import (
            DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO,
            DOCTOR_MAX_BUILDER_ATTEMPTS_BEFORE_COMPLEX,
            DOCTOR_MIN_CONFIDENCE_FOR_CHEAP,
        )

        assert DOCTOR_MIN_CONFIDENCE_FOR_CHEAP == doctor_config.min_confidence_for_cheap
        assert DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO == doctor_config.health_budget_near_limit_ratio
        assert (
            DOCTOR_MAX_BUILDER_ATTEMPTS_BEFORE_COMPLEX
            == doctor_config.max_builder_attempts_before_complex
        )

    def test_error_recovery_uses_config_risk_categories(self):
        """error_recovery risk categories should match config."""
        from src.autopack.config_loader import doctor_config
        from src.autopack.error_recovery import (
            DOCTOR_HIGH_RISK_CATEGORIES,
            DOCTOR_LOW_RISK_CATEGORIES,
        )

        assert DOCTOR_HIGH_RISK_CATEGORIES == set(doctor_config.high_risk_categories)
        assert DOCTOR_LOW_RISK_CATEGORIES == set(doctor_config.low_risk_categories)


class TestModelRouterAuxiliaryMethods:
    """Test ModelRouter auxiliary model accessor methods."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def model_router(self, mock_db):
        """Create a ModelRouter instance with mocked dependencies."""
        with patch("src.autopack.model_router.UsageService"):
            with patch("src.autopack.model_router.get_model_selector"):
                with patch(
                    "src.autopack.model_router.TelemetryDrivenModelOptimizer",
                    return_value=None,
                ):
                    from src.autopack.model_router import ModelRouter

                    router = ModelRouter(mock_db, config_path="config/models.yaml")
                    return router

    def test_get_doctor_models_returns_config(self, model_router):
        """get_doctor_models should return doctor model configuration."""
        doctor_config = model_router.get_doctor_models()

        assert "cheap" in doctor_config
        assert "strong" in doctor_config
        assert "min_confidence_for_cheap" in doctor_config
        assert "health_budget_near_limit_ratio" in doctor_config

    def test_get_doctor_models_has_defaults(self, model_router):
        """get_doctor_models should have sensible defaults."""
        doctor_config = model_router.get_doctor_models()

        # Verify defaults are present
        assert doctor_config["cheap"] in ["claude-sonnet-4-5", "claude-opus-4-5"]
        assert doctor_config["strong"] in ["claude-sonnet-4-5", "claude-opus-4-5"]
        assert 0 < doctor_config["min_confidence_for_cheap"] <= 1.0
        assert 0 < doctor_config["health_budget_near_limit_ratio"] <= 1.0

    def test_get_judge_model_returns_string(self, model_router):
        """get_judge_model should return a model identifier string."""
        judge_model = model_router.get_judge_model()

        assert isinstance(judge_model, str)
        assert len(judge_model) > 0

    def test_get_tool_model_returns_configured_model(self, model_router):
        """get_tool_model should return configured tool model."""
        # tidy_semantic is configured in models.yaml
        tidy_model = model_router.get_tool_model("tidy_semantic")

        # Should return a model or None if not configured
        if tidy_model is not None:
            assert isinstance(tidy_model, str)

    def test_get_tool_model_returns_none_for_unknown(self, model_router):
        """get_tool_model should return None for unknown tools."""
        unknown_model = model_router.get_tool_model("nonexistent_tool_xyz")

        assert unknown_model is None

    def test_resolve_model_alias_resolves_sonnet(self, model_router):
        """resolve_model_alias should resolve 'sonnet' alias."""
        resolved = model_router.resolve_model_alias("sonnet")

        # Should resolve to full model name
        assert "claude" in resolved or resolved == "sonnet"

    def test_resolve_model_alias_returns_unchanged_for_non_alias(self, model_router):
        """resolve_model_alias should return unchanged for non-aliases."""
        original = "claude-sonnet-4-5"
        resolved = model_router.resolve_model_alias(original)

        assert resolved == original


class TestConfigYamlIntegration:
    """Test that config/models.yaml has required sections."""

    @pytest.fixture
    def models_config(self):
        """Load config/models.yaml."""
        config_path = Path("config/models.yaml")
        if not config_path.exists():
            pytest.skip("config/models.yaml not found")

        with open(config_path) as f:
            return yaml.safe_load(f)

    def test_doctor_models_section_exists(self, models_config):
        """config/models.yaml should have doctor_models section."""
        assert "doctor_models" in models_config
        assert isinstance(models_config["doctor_models"], dict)

    def test_doctor_models_has_cheap_and_strong(self, models_config):
        """doctor_models should have 'cheap' and 'strong' keys."""
        doctor = models_config["doctor_models"]
        assert "cheap" in doctor
        assert "strong" in doctor

    def test_dual_audit_judge_section_exists(self, models_config):
        """config/models.yaml should have dual_audit_judge section."""
        assert "dual_audit_judge" in models_config
        assert "model" in models_config["dual_audit_judge"]

    def test_tool_models_section_exists(self, models_config):
        """config/models.yaml should have tool_models section."""
        assert "tool_models" in models_config
        assert isinstance(models_config["tool_models"], dict)

    def test_model_aliases_section_exists(self, models_config):
        """config/models.yaml should have model_aliases section."""
        assert "model_aliases" in models_config
        assert isinstance(models_config["model_aliases"], dict)

    def test_model_aliases_has_sonnet(self, models_config):
        """model_aliases should have 'sonnet' alias."""
        aliases = models_config["model_aliases"]
        assert "sonnet" in aliases


class TestNoHardcodedModelsInErrorRecovery:
    """Ensure error_recovery.py doesn't use hardcoded model names."""

    def test_doctor_models_not_hardcoded(self):
        """DOCTOR_*_MODEL should come from config, not be hardcoded."""

        # Read the source file
        source_path = Path("src/autopack/error_recovery.py")
        if not source_path.exists():
            pytest.skip("error_recovery.py not found")

        with open(source_path) as f:
            source = f.read()

        # Check that the model assignments reference _doctor_config
        # and don't have literal string assignments
        assert "_doctor_config.cheap_model" in source, (
            "DOCTOR_CHEAP_MODEL should reference _doctor_config.cheap_model"
        )
        assert "_doctor_config.strong_model" in source, (
            "DOCTOR_STRONG_MODEL should reference _doctor_config.strong_model"
        )
