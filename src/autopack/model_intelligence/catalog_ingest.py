"""Catalog ingestion: Load config/models.yaml + config/pricing.yaml into DB.

This module ingests model definitions and pricing from YAML configuration files
into the Postgres-backed model catalog.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import yaml
from sqlalchemy.orm import Session

from .models import ModelCatalog, ModelPricing


def load_yaml(file_path: str) -> Dict[str, Any]:
    """Load YAML configuration file.

    Args:
        file_path: Path to YAML file.

    Returns:
        Parsed YAML content as dictionary.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_models_from_config(models_config: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract unique model IDs from models.yaml configuration.

    Args:
        models_config: Parsed models.yaml content.

    Returns:
        List of model dictionaries with model_id and usage context.
    """
    models = set()

    # Extract from complexity_models
    if "complexity_models" in models_config:
        for tier, roles in models_config["complexity_models"].items():
            for role, model in roles.items():
                models.add(model)

    # Extract from llm_routing_policies
    if "llm_routing_policies" in models_config:
        for policy, config in models_config["llm_routing_policies"].items():
            for key, value in config.items():
                if key.endswith("_primary") or key.endswith("_auditor") or key.endswith("_builder"):
                    if isinstance(value, str):
                        models.add(value)
                elif key == "escalate_to" and isinstance(value, dict):
                    models.add(value.get("builder", ""))
                    models.add(value.get("auditor", ""))

    # Extract from category_models
    if "category_models" in models_config:
        for category, config in models_config["category_models"].items():
            models.add(config.get("builder_model_override", ""))
            models.add(config.get("auditor_model_override", ""))
            models.add(config.get("secondary_auditor", ""))

    # Extract from fallback_strategy
    if "fallback_strategy" in models_config:
        for key, value in models_config["fallback_strategy"].items():
            if isinstance(value, dict) and "fallbacks" in value:
                models.update(value["fallbacks"])
        if "default_fallbacks" in models_config["fallback_strategy"]:
            models.update(models_config["fallback_strategy"]["default_fallbacks"])

    # Extract from model_aliases
    if "model_aliases" in models_config:
        models.update(models_config["model_aliases"].values())

    # Extract from tool_models
    if "tool_models" in models_config:
        models.update(models_config["tool_models"].values())

    # Extract from escalation_chains
    if "escalation_chains" in models_config:
        for role, chains in models_config["escalation_chains"].items():
            for tier, config in chains.items():
                if "models" in config:
                    models.update(config["models"])

    # Extract from doctor_models
    if "doctor_models" in models_config:
        for key, value in models_config["doctor_models"].items():
            if isinstance(value, str):
                models.add(value)

    # Remove empty strings and None
    models.discard("")
    models.discard(None)

    return [{"model_id": model_id} for model_id in sorted(models)]


def parse_provider_and_family(model_id: str) -> tuple[str, str]:
    """Parse provider and family from model ID.

    Args:
        model_id: Model identifier (e.g., claude-sonnet-4-5, gpt-4o, glm-4.7).

    Returns:
        Tuple of (provider, family).
    """
    if model_id.startswith("claude"):
        return "anthropic", "claude"
    elif model_id.startswith("gpt"):
        return "openai", "gpt"
    elif model_id.startswith("gemini"):
        return "google", "gemini"
    elif model_id.startswith("glm"):
        return "zhipu_glm", "glm"
    else:
        return "unknown", "unknown"


def ingest_catalog(session: Session, models_yaml_path: str) -> int:
    """Ingest model catalog from models.yaml into database.

    Args:
        session: Database session.
        models_yaml_path: Path to models.yaml file.

    Returns:
        Number of models ingested.
    """
    models_config = load_yaml(models_yaml_path)
    model_list = extract_models_from_config(models_config)

    ingested_count = 0

    for model_info in model_list:
        model_id = model_info["model_id"]
        provider, family = parse_provider_and_family(model_id)

        # Check if model already exists
        existing = session.query(ModelCatalog).filter_by(model_id=model_id).first()

        if existing:
            # Update timestamp
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new catalog entry
            catalog_entry = ModelCatalog(
                model_id=model_id,
                provider=provider,
                family=family,
                display_name=model_id.replace("-", " ").title(),
                is_deprecated=False,
            )
            session.add(catalog_entry)
            ingested_count += 1

    session.commit()
    return ingested_count


def ingest_pricing(session: Session, pricing_yaml_path: str, effective_at: datetime = None) -> int:
    """Ingest pricing data from pricing.yaml into database.

    Args:
        session: Database session.
        pricing_yaml_path: Path to pricing.yaml file.
        effective_at: Effective date for pricing (defaults to now).

    Returns:
        Number of pricing records ingested.
    """
    if effective_at is None:
        effective_at = datetime.now(timezone.utc)

    pricing_config = load_yaml(pricing_yaml_path)
    ingested_count = 0

    for provider, models in pricing_config.items():
        if not isinstance(models, dict):
            continue

        for model_id, pricing in models.items():
            if not isinstance(pricing, dict):
                continue

            # Get or create catalog entry
            catalog_entry = session.query(ModelCatalog).filter_by(model_id=model_id).first()
            if not catalog_entry:
                # Create minimal catalog entry if not exists
                provider_name, family = parse_provider_and_family(model_id)
                catalog_entry = ModelCatalog(
                    model_id=model_id,
                    provider=provider_name,
                    family=family,
                    display_name=model_id.replace("-", " ").title(),
                )
                session.add(catalog_entry)
                session.flush()

            # Check if pricing record already exists
            existing = session.query(ModelPricing).filter_by(
                model_id=model_id,
                effective_at=effective_at,
                source=f"{provider}_pricing_yaml"
            ).first()

            if existing:
                # Update existing record
                existing.input_per_1k = pricing.get("input_per_1k", 0)
                existing.output_per_1k = pricing.get("output_per_1k", 0)
                existing.retrieved_at = datetime.now(timezone.utc)
            else:
                # Create new pricing record
                pricing_record = ModelPricing(
                    model_id=model_id,
                    input_per_1k=pricing.get("input_per_1k", 0),
                    output_per_1k=pricing.get("output_per_1k", 0),
                    currency="USD",
                    effective_at=effective_at,
                    source=f"{provider}_pricing_yaml",
                    source_url="config/pricing.yaml",
                )
                session.add(pricing_record)
                ingested_count += 1

    session.commit()
    return ingested_count


def ingest_all(models_yaml_path: str = None, pricing_yaml_path: str = None) -> Dict[str, int]:
    """Ingest all catalog and pricing data.

    Args:
        models_yaml_path: Path to models.yaml (defaults to config/models.yaml).
        pricing_yaml_path: Path to pricing.yaml (defaults to config/pricing.yaml).

    Returns:
        Dictionary with ingestion counts.
    """
    from .db import get_model_intelligence_session

    # Default paths relative to repo root
    if models_yaml_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        models_yaml_path = str(repo_root / "config" / "models.yaml")

    if pricing_yaml_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        pricing_yaml_path = str(repo_root / "config" / "pricing.yaml")

    with get_model_intelligence_session() as session:
        catalog_count = ingest_catalog(session, models_yaml_path)
        pricing_count = ingest_pricing(session, pricing_yaml_path)

        return {
            "catalog": catalog_count,
            "pricing": pricing_count,
        }
