"""
Catalog-backed routing snapshot refresh for intention-first autonomy.

Implements:
- Catalog source adapter reading from repo's model configuration
- Deterministic "best under budget+safety" selection per tier
- Graceful fallback to default snapshot if catalog unavailable
- Stable, reproducible routing decisions

Replaces "default-only" snapshot creation with real catalog-backed selection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from autopack.model_routing_snapshot import (
    ModelRoutingEntry,
    ModelRoutingSnapshot,
    RoutingSnapshotStorage,
    create_default_snapshot,
)
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelCatalogEntry:
    """
    Single model entry in the catalog with pricing and capabilities.

    This is the "source of truth" for model selection.
    """

    model_id: str
    provider: str
    tier: str  # "haiku", "sonnet", "opus"
    max_tokens: int
    max_context_chars: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    safety_compatible: bool = True


# Seed catalog: Anthropic Claude models (BUILD-161 Phase B)
# TODO: Replace with dynamic catalog source (e.g., from DB or external API)
# when model pricing becomes more dynamic
SEED_CATALOG = [
    # Haiku tier - fastest, cheapest
    ModelCatalogEntry(
        model_id="claude-3-5-haiku-20241022",
        provider="anthropic",
        tier="haiku",
        max_tokens=8192,
        max_context_chars=200_000,
        cost_per_1k_input=1.0,
        cost_per_1k_output=5.0,
        safety_compatible=True,
    ),
    # Sonnet tier - balanced performance
    ModelCatalogEntry(
        model_id="claude-3-5-sonnet-20241022",
        provider="anthropic",
        tier="sonnet",
        max_tokens=8192,
        max_context_chars=200_000,
        cost_per_1k_input=3.0,
        cost_per_1k_output=15.0,
        safety_compatible=True,
    ),
    ModelCatalogEntry(
        model_id="claude-sonnet-4-5",  # Newer Sonnet variant
        provider="anthropic",
        tier="sonnet",
        max_tokens=8192,
        max_context_chars=200_000,
        cost_per_1k_input=3.0,
        cost_per_1k_output=15.0,
        safety_compatible=True,
    ),
    # Opus tier - highest capability
    ModelCatalogEntry(
        model_id="claude-opus-4-20250514",
        provider="anthropic",
        tier="opus",
        max_tokens=4096,
        max_context_chars=200_000,
        cost_per_1k_input=15.0,
        cost_per_1k_output=75.0,
        safety_compatible=True,
    ),
    ModelCatalogEntry(
        model_id="claude-opus-4-5",  # Newer Opus variant
        provider="anthropic",
        tier="opus",
        max_tokens=4096,
        max_context_chars=200_000,
        cost_per_1k_input=15.0,
        cost_per_1k_output=75.0,
        safety_compatible=True,
    ),
]


def load_model_catalog() -> list[ModelCatalogEntry]:
    """
    Load model catalog from authoritative source.

    Current implementation: returns seed catalog.
    Future: could read from DB, external API, or enriched config file.

    Returns:
        List of catalog entries
    """
    # For now, return seed catalog
    # In future, this could enrich from config/models.yaml or external source
    return list(SEED_CATALOG)


def select_best_model_for_tier(
    catalog: list[ModelCatalogEntry],
    tier: str,
    safety_profile: Literal["normal", "strict"] = "normal",
) -> ModelRoutingEntry | None:
    """
    Select best model for tier using deterministic selection contract.

    Safety filtering:
    - Strict profile: only consider models with safety_compatible=True
    - Normal profile: consider all models (safety_compatible is not a selection criterion)

    Selection criteria (stable sort key):
    1. Cost (input + output) ascending (cheaper first)
    2. Context capacity descending (more context better)
    3. Max tokens descending (more tokens better)
    4. Model ID ascending (lexicographic tie-breaker)

    Args:
        catalog: Model catalog entries
        tier: Target tier (e.g., "haiku", "sonnet", "opus")
        safety_profile: Safety profile from IntentionRiskProfile

    Returns:
        ModelRoutingEntry if found, else None
    """
    # Filter by tier and safety
    candidates = [
        entry
        for entry in catalog
        if entry.tier == tier
        and (safety_profile != "strict" or entry.safety_compatible)
    ]

    if not candidates:
        return None

    # Deterministic sort by selection criteria
    # Note: safety_compatible is NOT a sort criterion in normal mode;
    # it's only used for filtering in strict mode
    sorted_candidates = sorted(
        candidates,
        key=lambda e: (
            e.cost_per_1k_input + e.cost_per_1k_output,  # cost ascending (cheaper first)
            -e.max_context_chars,  # context descending (negate for ascending sort)
            -e.max_tokens,  # tokens descending
            e.model_id,  # lexicographic tie-breaker
        ),
    )

    # Select first (best) candidate
    best = sorted_candidates[0]

    return ModelRoutingEntry(
        tier=best.tier,
        model_id=best.model_id,
        provider=best.provider,
        max_tokens=best.max_tokens,
        max_context_chars=best.max_context_chars,
        cost_per_1k_input=best.cost_per_1k_input,
        cost_per_1k_output=best.cost_per_1k_output,
        safety_compatible=best.safety_compatible,
    )


def create_catalog_backed_snapshot(
    run_id: str, safety_profile: Literal["normal", "strict"] = "normal"
) -> ModelRoutingSnapshot | None:
    """
    Create routing snapshot from catalog source.

    Args:
        run_id: Run ID
        safety_profile: Safety profile for filtering

    Returns:
        Snapshot if catalog available and has entries for required tiers, else None
    """
    try:
        catalog = load_model_catalog()
        if not catalog:
            logger.warning(
                "[ModelRoutingRefresh] Catalog empty, falling back to default"
            )
            return None

        # Required tiers per the system's canonical tier set
        required_tiers = ["haiku", "sonnet", "opus"]
        entries = []

        for tier in required_tiers:
            entry = select_best_model_for_tier(catalog, tier, safety_profile)
            if entry is None:
                logger.warning(
                    f"[ModelRoutingRefresh] No model found for tier {tier}, "
                    f"falling back to default"
                )
                return None
            entries.append(entry)

        # Create snapshot
        now = datetime.now(timezone.utc)
        return ModelRoutingSnapshot(
            snapshot_id=f"catalog-{run_id}",
            run_id=run_id,
            created_at=now,
            expires_at=now + timedelta(hours=24),
            entries=entries,
        )

    except Exception as e:
        logger.error(
            f"[ModelRoutingRefresh] Catalog source unavailable: {e}, "
            f"falling back to default"
        )
        return None


def refresh_routing_snapshot(
    run_id: str, safety_profile: Literal["normal", "strict"] = "normal"
) -> ModelRoutingSnapshot:
    """
    Refresh routing snapshot with catalog-backed selection.

    Logic:
    1. Try catalog-backed snapshot
    2. If catalog unavailable or incomplete, fall back to default snapshot
    3. Persist snapshot to run-local artifact

    Args:
        run_id: Run ID
        safety_profile: Safety profile for filtering

    Returns:
        Fresh routing snapshot (catalog-backed or default)
    """
    # Try catalog-backed snapshot
    snapshot = create_catalog_backed_snapshot(run_id, safety_profile)

    # Fall back to default if catalog unavailable
    if snapshot is None:
        logger.info(
            f"[ModelRoutingRefresh] Using default snapshot for run {run_id}"
        )
        snapshot = create_default_snapshot(run_id)
    else:
        logger.info(
            f"[ModelRoutingRefresh] Created catalog-backed snapshot for run {run_id}"
        )

    # Persist snapshot
    RoutingSnapshotStorage.save_snapshot(snapshot)

    return snapshot


def refresh_or_load_snapshot_with_catalog(
    run_id: str,
    force_refresh: bool = False,
    safety_profile: Literal["normal", "strict"] = "normal",
) -> ModelRoutingSnapshot:
    """
    Refresh or load routing snapshot with catalog-backed selection.

    This is the catalog-backed replacement for model_routing_snapshot.refresh_or_load_snapshot.

    Logic:
    1. If force_refresh: refresh with catalog and save
    2. If snapshot exists and fresh: load it
    3. If snapshot exists but expired: refresh with catalog and save
    4. If no snapshot exists: refresh with catalog and save

    Args:
        run_id: Run ID
        force_refresh: Force snapshot refresh
        safety_profile: Safety profile for filtering

    Returns:
        Fresh routing snapshot
    """
    if not force_refresh:
        existing = RoutingSnapshotStorage.load_snapshot(run_id)
        if existing and RoutingSnapshotStorage.is_snapshot_fresh(existing):
            logger.info(
                f"[ModelRoutingRefresh] Using existing fresh snapshot for run {run_id}"
            )
            return existing

    # Refresh snapshot (catalog-backed or default fallback)
    return refresh_routing_snapshot(run_id, safety_profile)
