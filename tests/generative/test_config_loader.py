"""Tests for configuration loader."""

import os
import tempfile

import pytest
import yaml

from autopack.generative.config_loader import ConfigLoader
from autopack.generative.exceptions import InvalidConfigurationError


@pytest.fixture
def sample_config() -> dict:
    """Create a sample configuration."""
    return {
        "providers": {
            "test_provider": {
                "endpoint": "https://api.example.com",
                "api_key_env": "TEST_API_KEY",
                "timeout_seconds": 120,
                "max_retries": 3,
            }
        },
        "capabilities": {
            "image_generation": {
                "default_model": "test_model",
                "fallback_chain": ["test_model", "fallback_model"],
                "min_acceptable_quality": 0.8,
                "prefer_open_source_if_above": 0.85,
                "models": {
                    "test_model": {
                        "provider": "test_provider",
                        "name": "Test Model",
                        "quality_score": 0.9,
                        "cost_per_unit": 0.001,
                        "license": "MIT",
                    },
                    "fallback_model": {
                        "provider": "test_provider",
                        "name": "Fallback Model",
                        "quality_score": 0.75,
                        "cost_per_unit": 0.0005,
                        "license": "Apache 2.0",
                    },
                },
            }
        },
        "quality_thresholds": {
            "min_acceptable": 0.8,
            "prefer_open_source_if_above": 0.85,
        },
    }


@pytest.fixture
def temp_config_file(sample_config) -> str:
    """Create a temporary config file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    if os.path.exists(temp_path):
        os.remove(temp_path)


class TestConfigLoader:
    """Test configuration loader."""

    def test_load_config_from_file(self, temp_config_file):
        """Test loading configuration from file."""
        loader = ConfigLoader(temp_config_file)
        registry = loader.get_registry()

        # Check providers
        assert "test_provider" in registry.list_providers()

        # Check capabilities
        assert "image_generation" in registry.list_capabilities()

    def test_load_config_with_invalid_path(self):
        """Test loading from invalid path raises error."""
        with pytest.raises(InvalidConfigurationError):
            ConfigLoader("/nonexistent/path/config.yaml")

    def test_config_provider_loading(self, temp_config_file):
        """Test provider configuration loading."""
        loader = ConfigLoader(temp_config_file)
        registry = loader.get_registry()

        provider = registry.get_provider("test_provider")
        assert provider.name == "test_provider"
        assert provider.endpoint == "https://api.example.com"
        assert provider.api_key_env == "TEST_API_KEY"
        assert provider.timeout_seconds == 120
        assert provider.max_retries == 3

    def test_config_capability_loading(self, temp_config_file):
        """Test capability configuration loading."""
        loader = ConfigLoader(temp_config_file)
        registry = loader.get_registry()

        capability = registry.get_capability("image_generation")
        assert capability.capability_type == "image_generation"
        assert capability.default_model == "test_model"
        assert len(capability.fallback_chain) == 2
        assert len(capability.models) == 2

    def test_config_model_loading(self, temp_config_file):
        """Test model configuration loading."""
        loader = ConfigLoader(temp_config_file)
        registry = loader.get_registry()

        capability = registry.get_capability("image_generation")
        test_model = capability.models["test_model"]

        assert test_model.model_id == "test_model"
        assert test_model.provider == "test_provider"
        assert test_model.quality_score == 0.9
        assert test_model.cost_per_unit == 0.001

    def test_config_quality_thresholds(self, temp_config_file):
        """Test quality threshold loading."""
        loader = ConfigLoader(temp_config_file)
        registry = loader.get_registry()

        thresholds = registry.quality_thresholds
        assert thresholds["min_acceptable"] == 0.8
        assert thresholds["prefer_open_source_if_above"] == 0.85

    def test_config_with_missing_providers(self, sample_config):
        """Test loading config with missing providers section."""
        sample_config.pop("providers")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            temp_path = f.name

        try:
            loader = ConfigLoader(temp_path)
            registry = loader.get_registry()
            assert len(registry.list_providers()) == 0
        finally:
            os.remove(temp_path)

    def test_config_with_empty_file(self):
        """Test loading empty configuration file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with pytest.raises(InvalidConfigurationError):
                ConfigLoader(temp_path)
        finally:
            os.remove(temp_path)

    def test_config_invalid_quality_score(self, sample_config):
        """Test loading config with invalid quality score."""
        # Set invalid quality score
        sample_config["capabilities"]["image_generation"]["models"]["test_model"][
            "quality_score"
        ] = 1.5

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_config, f)
            temp_path = f.name

        try:
            with pytest.raises(InvalidConfigurationError):
                ConfigLoader(temp_path)
        finally:
            os.remove(temp_path)
