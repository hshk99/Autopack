"""Model catalog loader from config files (BUILD-180).

Loads model catalog from config/models.yaml and config/pricing.yaml
instead of hardcoded seed catalog.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config paths relative to repo root
DEFAULT_MODELS_PATH = Path("config/models.yaml")
DEFAULT_PRICING_PATH = Path("config/pricing.yaml")

# Required tiers for routing
REQUIRED_TIERS = ["haiku", "sonnet", "opus"]

# Tier to alias mapping (for lookup in models.yaml)
TIER_ALIASES = {
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
}

# Default model specs when not in pricing config
DEFAULT_MODEL_SPECS = {
    "max_tokens": 8192,
    "max_context_chars": 200_000,
    "safety_compatible": True,
}


@dataclass(frozen=True)
class ModelCatalogEntry:
    """Single model entry in the catalog with pricing and capabilities."""

    model_id: str
    provider: str
    tier: str
    max_tokens: int
    max_context_chars: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    safety_compatible: bool = True


def parse_models_config(config: Dict[str, Any]) -> Dict[str, str]:
    """Parse model aliases from models.yaml config.

    Args:
        config: Parsed YAML config

    Returns:
        Dictionary mapping alias to model_id
    """
    aliases = config.get("model_aliases", {})
    return {k: v for k, v in aliases.items() if isinstance(v, str)}


def parse_pricing_config(config: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Parse pricing from pricing.yaml config.

    Args:
        config: Parsed YAML config

    Returns:
        Dictionary mapping model_id to pricing dict
    """
    pricing = {}

    # Parse each provider section
    for provider in ["anthropic", "openai", "google"]:
        provider_models = config.get(provider, {})
        if isinstance(provider_models, dict):
            for model_id, model_pricing in provider_models.items():
                if isinstance(model_pricing, dict):
                    pricing[model_id] = {
                        "input_per_1k": model_pricing.get("input_per_1k", 0.0),
                        "output_per_1k": model_pricing.get("output_per_1k", 0.0),
                        "provider": provider,
                    }

    return pricing


def infer_provider_from_model_id(model_id: str) -> str:
    """Infer provider from model ID.

    Args:
        model_id: Model identifier

    Returns:
        Provider name
    """
    model_lower = model_id.lower()

    if "claude" in model_lower:
        return "anthropic"
    elif "gpt" in model_lower:
        return "openai"
    elif "gemini" in model_lower:
        return "google"
    else:
        return "unknown"


def load_model_catalog_from_config(
    models_path: Path,
    pricing_path: Path,
) -> Optional[List[ModelCatalogEntry]]:
    """Load model catalog from config files.

    Args:
        models_path: Path to models.yaml
        pricing_path: Path to pricing.yaml

    Returns:
        List of ModelCatalogEntry, or None if files unavailable
    """
    try:
        # Load models config
        if not models_path.exists():
            logger.warning(f"[ModelCatalog] Models config not found: {models_path}")
            return None

        with open(models_path, "r", encoding="utf-8") as f:
            models_config = yaml.safe_load(f) or {}

        # Load pricing config
        if not pricing_path.exists():
            logger.warning(f"[ModelCatalog] Pricing config not found: {pricing_path}")
            return None

        with open(pricing_path, "r", encoding="utf-8") as f:
            pricing_config = yaml.safe_load(f) or {}

        # Parse configs
        aliases = parse_models_config(models_config)
        pricing = parse_pricing_config(pricing_config)

        logger.debug(
            f"[ModelCatalog] Loaded {len(aliases)} aliases, {len(pricing)} pricing entries"
        )

        # Build catalog entries
        catalog = []
        tiers_seen: set[str] = set()

        for tier in REQUIRED_TIERS:
            # Get model ID from alias
            alias_key = TIER_ALIASES.get(tier, tier)
            model_id = aliases.get(alias_key)

            if not model_id:
                logger.warning(f"[ModelCatalog] No alias found for tier '{tier}'")
                # Direction: required tiers must be present for deterministic routing.
                # If any required tier is missing, treat the config as unusable and fall back.
                return None

            # Get pricing
            model_pricing = pricing.get(model_id, {})
            provider = model_pricing.get("provider") or infer_provider_from_model_id(model_id)

            entry = ModelCatalogEntry(
                model_id=model_id,
                provider=provider,
                tier=tier,
                max_tokens=DEFAULT_MODEL_SPECS["max_tokens"],
                max_context_chars=DEFAULT_MODEL_SPECS["max_context_chars"],
                cost_per_1k_input=model_pricing.get("input_per_1k", 0.0),
                cost_per_1k_output=model_pricing.get("output_per_1k", 0.0),
                safety_compatible=DEFAULT_MODEL_SPECS["safety_compatible"],
            )
            catalog.append(entry)
            tiers_seen.add(tier)

        # Direction: config catalog must include all required tiers; partial catalogs are not allowed.
        missing_tiers = [t for t in REQUIRED_TIERS if t not in tiers_seen]
        if missing_tiers:
            logger.warning(
                f"[ModelCatalog] Missing required tiers from config: {missing_tiers}. "
                "Falling back to seed catalog."
            )
            return None

        logger.info(f"[ModelCatalog] Built catalog with {len(catalog)} entries from config")
        return catalog

    except yaml.YAMLError as e:
        logger.error(f"[ModelCatalog] YAML parse error: {e}")
        return None

    except Exception as e:
        logger.error(f"[ModelCatalog] Failed to load catalog: {e}")
        return None


def get_repo_root() -> Path:
    """Get repository root path.

    Returns:
        Path to repo root
    """
    # Try to find repo root by looking for config/ directory
    current = Path(__file__).resolve()

    for parent in [current] + list(current.parents):
        if (parent / "config" / "models.yaml").exists():
            return parent

    # Fallback to current working directory
    return Path.cwd()


def load_model_catalog() -> List[ModelCatalogEntry]:
    """Load model catalog from default config paths.

    Returns:
        List of ModelCatalogEntry (from config or fallback seed)
    """
    repo_root = get_repo_root()

    models_path = repo_root / DEFAULT_MODELS_PATH
    pricing_path = repo_root / DEFAULT_PRICING_PATH

    catalog = load_model_catalog_from_config(models_path, pricing_path)

    if catalog is not None:
        return catalog

    # Return empty list - caller should use SEED_CATALOG fallback
    logger.info("[ModelCatalog] Config unavailable, caller should use seed catalog")
    return []
