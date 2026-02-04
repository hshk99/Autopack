"""Tests for model catalog config loading (BUILD-180 Phase 5).

Validates that model routing uses config files instead of hardcoded catalog.
"""

import tempfile
from pathlib import Path

import yaml

from autopack.model_catalog import (
    ModelCatalogEntry,
    load_model_catalog_from_config,
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
        # Force "config unavailable" to validate seed fallback deterministically.
        from unittest.mock import patch

        from autopack.model_routing_refresh import SEED_CATALOG, load_model_catalog

        with patch("autopack.model_catalog.load_model_catalog", return_value=[]):
            catalog = load_model_catalog()

        assert len(catalog) == len(SEED_CATALOG)


class TestP16SeedCatalogDriftContract:
    """P1.6: Contract tests to prevent SEED_CATALOG from silently drifting from config."""

    def test_seed_catalog_tiers_match_required_tiers(self):
        """SEED_CATALOG must cover all required tiers."""
        from autopack.model_catalog import REQUIRED_TIERS
        from autopack.model_routing_refresh import SEED_CATALOG

        seed_tiers = {e.tier for e in SEED_CATALOG}

        for tier in REQUIRED_TIERS:
            assert tier in seed_tiers, (
                f"SEED_CATALOG missing required tier '{tier}'. "
                "Update SEED_CATALOG or check REQUIRED_TIERS."
            )

    def test_seed_catalog_model_ids_are_valid_anthropic_models(self):
        """SEED_CATALOG model_ids should follow Anthropic naming conventions."""
        from autopack.model_routing_refresh import SEED_CATALOG

        for entry in SEED_CATALOG:
            # All seed models should be Anthropic Claude models
            assert entry.provider == "anthropic", (
                f"SEED_CATALOG entry {entry.model_id} is not Anthropic. "
                "Seed catalog is for Anthropic fallback only."
            )
            assert "claude" in entry.model_id.lower(), (
                f"SEED_CATALOG entry {entry.model_id} doesn't look like a Claude model."
            )

    def test_config_catalog_preferred_over_seed_when_available(self):
        """When config is available, it should be used instead of seed."""
        from autopack.model_catalog import load_model_catalog as load_from_config
        from autopack.model_routing_refresh import load_model_catalog

        # Load from config
        config_catalog = load_from_config()

        # If config is available, load_model_catalog should return config, not seed
        if config_catalog:
            loaded = load_model_catalog()

            # Should NOT be using seed (model IDs might differ)
            # The key assertion: if config exists, we should get config entries
            loaded_ids = {e.model_id for e in loaded}
            config_ids = {e.model_id for e in config_catalog}

            # If config is available, loaded should match config
            assert loaded_ids == config_ids, (
                "load_model_catalog() returned different model IDs than config. "
                "Config should be preferred when available."
            )

    def test_seed_catalog_pricing_is_plausible(self):
        """SEED_CATALOG pricing should be plausible (not zero, not absurdly high)."""
        from autopack.model_routing_refresh import SEED_CATALOG

        for entry in SEED_CATALOG:
            # Pricing should be positive (free models would be suspicious for Claude)
            assert entry.cost_per_1k_input > 0, (
                f"SEED_CATALOG entry {entry.model_id} has zero input cost. "
                "Claude models are not free."
            )
            assert entry.cost_per_1k_output > 0, (
                f"SEED_CATALOG entry {entry.model_id} has zero output cost. "
                "Claude models are not free."
            )

            # Pricing should be reasonable (< $100/1k tokens is safe upper bound)
            assert entry.cost_per_1k_input < 100, (
                f"SEED_CATALOG entry {entry.model_id} has implausible input cost."
            )
            assert entry.cost_per_1k_output < 100, (
                f"SEED_CATALOG entry {entry.model_id} has implausible output cost."
            )
