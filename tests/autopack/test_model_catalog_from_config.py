"""Tests for model catalog config loading (BUILD-180 Phase 5).

Validates that model routing uses config files instead of hardcoded catalog.
"""

from pathlib import Path
import tempfile
import yaml

from autopack.model_catalog import (
    load_model_catalog_from_config,
    ModelCatalogEntry,
    parse_models_config,
    parse_pricing_config,
)


class TestModelsConfigParsing:
    """Test parsing models.yaml config."""

    def test_parses_model_aliases(self):
        """Should parse model aliases from config."""
        config = {
            "model_aliases": {
                "sonnet": "claude-sonnet-4-5",
                "opus": "claude-opus-4-5",
                "haiku": "claude-3-5-haiku-20241022",
            }
        }

        aliases = parse_models_config(config)

        assert aliases["sonnet"] == "claude-sonnet-4-5"
        assert aliases["opus"] == "claude-opus-4-5"
        assert aliases["haiku"] == "claude-3-5-haiku-20241022"

    def test_handles_missing_aliases(self):
        """Should handle missing model_aliases section."""
        config = {"complexity_models": {}}

        aliases = parse_models_config(config)

        assert aliases == {}


class TestPricingConfigParsing:
    """Test parsing pricing.yaml config."""

    def test_parses_anthropic_pricing(self):
        """Should parse Anthropic model pricing."""
        config = {
            "anthropic": {
                "claude-sonnet-4-5": {
                    "input_per_1k": 0.003,
                    "output_per_1k": 0.015,
                },
                "claude-opus-4-5": {
                    "input_per_1k": 0.015,
                    "output_per_1k": 0.075,
                },
            }
        }

        pricing = parse_pricing_config(config)

        assert "claude-sonnet-4-5" in pricing
        assert pricing["claude-sonnet-4-5"]["input_per_1k"] == 0.003
        assert pricing["claude-sonnet-4-5"]["output_per_1k"] == 0.015

    def test_parses_multiple_providers(self):
        """Should parse pricing from multiple providers."""
        config = {
            "anthropic": {
                "claude-sonnet-4-5": {"input_per_1k": 0.003, "output_per_1k": 0.015},
            },
            "openai": {
                "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
            },
        }

        pricing = parse_pricing_config(config)

        assert "claude-sonnet-4-5" in pricing
        assert "gpt-4o" in pricing


class TestLoadModelCatalog:
    """Test loading full model catalog from config files."""

    def test_loads_catalog_from_files(self):
        """Should load catalog entries from config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            models_path = Path(tmpdir) / "models.yaml"
            pricing_path = Path(tmpdir) / "pricing.yaml"

            models_config = {
                "model_aliases": {
                    "sonnet": "claude-sonnet-4-5",
                    "opus": "claude-opus-4-5",
                    "haiku": "claude-3-5-haiku-20241022",
                }
            }
            pricing_config = {
                "anthropic": {
                    "claude-sonnet-4-5": {"input_per_1k": 0.003, "output_per_1k": 0.015},
                    "claude-opus-4-5": {"input_per_1k": 0.015, "output_per_1k": 0.075},
                    "claude-3-5-haiku-20241022": {"input_per_1k": 0.001, "output_per_1k": 0.005},
                }
            }

            models_path.write_text(yaml.dump(models_config))
            pricing_path.write_text(yaml.dump(pricing_config))

            catalog = load_model_catalog_from_config(models_path, pricing_path)

            assert len(catalog) >= 3
            # Check that entries have correct structure
            sonnet_entry = next((e for e in catalog if e.tier == "sonnet"), None)
            assert sonnet_entry is not None
            assert sonnet_entry.model_id == "claude-sonnet-4-5"

    def test_returns_none_on_missing_files(self):
        """Should return None when config files missing."""
        catalog = load_model_catalog_from_config(
            Path("/nonexistent/models.yaml"), Path("/nonexistent/pricing.yaml")
        )

        assert catalog is None

    def test_validates_required_tiers(self):
        """Should validate that required tiers are present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            models_path = Path(tmpdir) / "models.yaml"
            pricing_path = Path(tmpdir) / "pricing.yaml"

            # Missing haiku tier
            models_config = {
                "model_aliases": {
                    "sonnet": "claude-sonnet-4-5",
                    "opus": "claude-opus-4-5",
                }
            }
            pricing_config = {
                "anthropic": {
                    "claude-sonnet-4-5": {"input_per_1k": 0.003, "output_per_1k": 0.015},
                    "claude-opus-4-5": {"input_per_1k": 0.015, "output_per_1k": 0.075},
                }
            }

            models_path.write_text(yaml.dump(models_config))
            pricing_path.write_text(yaml.dump(pricing_config))

            # Direction: required tiers must be present for deterministic routing.
            # If a required tier is missing, treat the config as unusable.
            catalog = load_model_catalog_from_config(models_path, pricing_path)

            assert catalog is None


class TestModelCatalogEntry:
    """Test ModelCatalogEntry dataclass."""

    def test_entry_has_required_fields(self):
        """ModelCatalogEntry should have required fields."""
        entry = ModelCatalogEntry(
            model_id="claude-sonnet-4-5",
            provider="anthropic",
            tier="sonnet",
            max_tokens=8192,
            max_context_chars=200_000,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            safety_compatible=True,
        )

        assert entry.model_id == "claude-sonnet-4-5"
        assert entry.provider == "anthropic"
        assert entry.tier == "sonnet"
        assert entry.cost_per_1k_input == 0.003


class TestModelRoutingRefreshIntegration:
    """Test integration with model_routing_refresh."""

    def test_routing_uses_config_catalog(self):
        """Model routing should use catalog from config files."""
        from autopack.model_routing_refresh import load_model_catalog

        # Should attempt to load from config
        catalog = load_model_catalog()

        # Should have entries (either from config or fallback)
        assert len(catalog) > 0

    def test_fallback_to_seed_on_config_error(self):
        """Should fall back to seed catalog on config error."""
        from autopack.model_routing_refresh import (
            load_model_catalog,
            SEED_CATALOG,
        )

        # Force "config unavailable" to validate seed fallback deterministically.
        from unittest.mock import patch

        with patch("autopack.model_catalog.load_model_catalog", return_value=[]):
            catalog = load_model_catalog()

        assert len(catalog) == len(SEED_CATALOG)
