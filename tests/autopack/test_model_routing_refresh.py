"""
Tests for catalog-backed model routing snapshot refresh.

Verifies:
- Deterministic model selection per tier
- Safety filtering (strict vs normal profile)
- Fallback to default snapshot when catalog unavailable
- Stable sort order for reproducible routing decisions
"""

import shutil

import pytest

from autopack.config import settings
from autopack.model_routing_refresh import (
    ModelCatalogEntry, create_catalog_backed_snapshot, load_model_catalog,
    refresh_or_load_snapshot_with_catalog, refresh_routing_snapshot,
    select_best_model_for_tier)
from autopack.model_routing_snapshot import (ModelRoutingEntry,
                                             RoutingSnapshotStorage)


@pytest.fixture
def temp_run_dir(tmp_path):
    """Create temporary autonomous_runs root dir and point Settings at it."""
    runs_root = tmp_path / ".autonomous_runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    old = settings.autonomous_runs_dir
    settings.autonomous_runs_dir = str(runs_root)
    try:
        yield runs_root
    finally:
        settings.autonomous_runs_dir = old
        shutil.rmtree(runs_root, ignore_errors=True)


class TestLoadModelCatalog:
    """Test model catalog loading."""

    def test_load_catalog_returns_seed_catalog(self):
        """load_model_catalog returns seed catalog entries."""
        catalog = load_model_catalog()
        assert len(catalog) > 0
        assert all(isinstance(entry, ModelCatalogEntry) for entry in catalog)

    def test_catalog_has_required_tiers(self):
        """Catalog has entries for haiku, sonnet, opus tiers."""
        catalog = load_model_catalog()
        tiers = {entry.tier for entry in catalog}
        assert "haiku" in tiers
        assert "sonnet" in tiers
        assert "opus" in tiers


class TestSelectBestModelForTier:
    """Test deterministic model selection per tier."""

    def test_select_haiku_tier(self):
        """Select best haiku tier model."""
        catalog = load_model_catalog()
        entry = select_best_model_for_tier(catalog, "haiku", safety_profile="normal")

        assert entry is not None
        assert entry.tier == "haiku"
        assert isinstance(entry, ModelRoutingEntry)

    def test_select_sonnet_tier(self):
        """Select best sonnet tier model."""
        catalog = load_model_catalog()
        entry = select_best_model_for_tier(catalog, "sonnet", safety_profile="normal")

        assert entry is not None
        assert entry.tier == "sonnet"

    def test_select_opus_tier(self):
        """Select best opus tier model."""
        catalog = load_model_catalog()
        entry = select_best_model_for_tier(catalog, "opus", safety_profile="normal")

        assert entry is not None
        assert entry.tier == "opus"

    def test_select_nonexistent_tier(self):
        """Select nonexistent tier returns None."""
        catalog = load_model_catalog()
        entry = select_best_model_for_tier(catalog, "nonexistent", safety_profile="normal")

        assert entry is None

    def test_deterministic_selection_cheapest_first(self):
        """Selection prefers cheaper models (cost ascending)."""
        # Create catalog with multiple haiku models at different costs
        catalog = [
            ModelCatalogEntry(
                model_id="expensive-haiku",
                provider="provider-a",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=2.0,
                cost_per_1k_output=10.0,  # Total: 12.0
                safety_compatible=True,
            ),
            ModelCatalogEntry(
                model_id="cheap-haiku",
                provider="provider-b",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=0.5,
                cost_per_1k_output=2.5,  # Total: 3.0 (cheaper)
                safety_compatible=True,
            ),
        ]

        entry = select_best_model_for_tier(catalog, "haiku", safety_profile="normal")

        assert entry.model_id == "cheap-haiku"
        assert entry.cost_per_1k_input + entry.cost_per_1k_output == 3.0

    def test_deterministic_selection_higher_context_wins_tie(self):
        """When cost ties, selection prefers higher context capacity."""
        catalog = [
            ModelCatalogEntry(
                model_id="low-context-haiku",
                provider="provider-a",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=100_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=True,
            ),
            ModelCatalogEntry(
                model_id="high-context-haiku",
                provider="provider-b",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,  # Higher context
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,  # Same cost
                safety_compatible=True,
            ),
        ]

        entry = select_best_model_for_tier(catalog, "haiku", safety_profile="normal")

        assert entry.model_id == "high-context-haiku"
        assert entry.max_context_chars == 200_000

    def test_deterministic_selection_lexicographic_tiebreaker(self):
        """When all else equal, model_id lexicographic order is tie-breaker."""
        catalog = [
            ModelCatalogEntry(
                model_id="z-haiku",
                provider="provider-a",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=True,
            ),
            ModelCatalogEntry(
                model_id="a-haiku",  # Lexicographically first
                provider="provider-b",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=True,
            ),
        ]

        entry = select_best_model_for_tier(catalog, "haiku", safety_profile="normal")

        assert entry.model_id == "a-haiku"


class TestSafetyFiltering:
    """Test strict safety profile filtering."""

    def test_strict_safety_filters_unsafe_models(self):
        """Strict safety profile excludes safety_compatible=False models."""
        catalog = [
            ModelCatalogEntry(
                model_id="unsafe-haiku",
                provider="provider-x",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=0.1,  # Super cheap
                cost_per_1k_output=0.5,
                safety_compatible=False,  # Not safe
            ),
            ModelCatalogEntry(
                model_id="safe-haiku",
                provider="provider-y",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=True,
            ),
        ]

        # Normal profile: should select cheaper unsafe model
        entry_normal = select_best_model_for_tier(catalog, "haiku", safety_profile="normal")
        assert entry_normal.model_id == "unsafe-haiku"

        # Strict profile: should select safe model despite higher cost
        entry_strict = select_best_model_for_tier(catalog, "haiku", safety_profile="strict")
        assert entry_strict.model_id == "safe-haiku"

    def test_strict_safety_returns_none_if_no_safe_models(self):
        """Strict safety profile returns None if no safe models for tier."""
        catalog = [
            ModelCatalogEntry(
                model_id="unsafe-haiku",
                provider="provider-x",
                tier="haiku",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=1.0,
                cost_per_1k_output=5.0,
                safety_compatible=False,  # Only unsafe model
            ),
        ]

        entry = select_best_model_for_tier(catalog, "haiku", safety_profile="strict")
        assert entry is None


class TestCreateCatalogBackedSnapshot:
    """Test catalog-backed snapshot creation."""

    def test_create_snapshot_with_full_catalog(self, temp_run_dir):
        """Create snapshot when catalog has all required tiers."""
        snapshot = create_catalog_backed_snapshot("test-run", safety_profile="normal")

        assert snapshot is not None
        assert snapshot.run_id == "test-run"
        assert snapshot.snapshot_id.startswith("catalog-")
        assert len(snapshot.entries) == 3  # haiku, sonnet, opus

        # Verify all required tiers present
        tiers = {entry.tier for entry in snapshot.entries}
        assert tiers == {"haiku", "sonnet", "opus"}

    def test_create_snapshot_with_strict_safety(self, temp_run_dir):
        """Create snapshot with strict safety profile."""
        snapshot = create_catalog_backed_snapshot("test-run", safety_profile="strict")

        assert snapshot is not None
        # All entries should be safety compatible
        for entry in snapshot.entries:
            assert entry.safety_compatible is True


class TestRefreshRoutingSnapshot:
    """Test routing snapshot refresh logic."""

    def test_refresh_creates_catalog_backed_snapshot(self, temp_run_dir):
        """Refresh creates catalog-backed snapshot when catalog available."""
        snapshot = refresh_routing_snapshot("test-run", safety_profile="normal")

        assert snapshot is not None
        assert snapshot.run_id == "test-run"
        assert snapshot.snapshot_id.startswith("catalog-")

        # Verify snapshot was persisted
        loaded = RoutingSnapshotStorage.load_snapshot("test-run")
        assert loaded is not None
        assert loaded.snapshot_id == snapshot.snapshot_id


class TestRefreshOrLoadSnapshotWithCatalog:
    """Test refresh-or-load logic with catalog."""

    def test_fresh_snapshot_not_refreshed(self, temp_run_dir):
        """Fresh existing snapshot is loaded without refresh."""
        # Create and save initial snapshot
        initial = create_catalog_backed_snapshot("test-run", safety_profile="normal")
        initial.snapshot_id = "initial-snapshot"
        RoutingSnapshotStorage.save_snapshot(initial)

        # Load without force refresh
        loaded = refresh_or_load_snapshot_with_catalog(
            "test-run", force_refresh=False, safety_profile="normal"
        )

        # Should load existing snapshot (not create new one)
        assert loaded.snapshot_id == "initial-snapshot"

    def test_force_refresh_creates_new_snapshot(self, temp_run_dir):
        """Force refresh creates new snapshot even if fresh one exists."""
        # Create and save initial snapshot
        initial = create_catalog_backed_snapshot("test-run", safety_profile="normal")
        initial.snapshot_id = "initial-snapshot"
        RoutingSnapshotStorage.save_snapshot(initial)

        # Force refresh
        refreshed = refresh_or_load_snapshot_with_catalog(
            "test-run", force_refresh=True, safety_profile="normal"
        )

        # Should create new snapshot
        assert refreshed.snapshot_id != "initial-snapshot"
        assert refreshed.snapshot_id.startswith("catalog-")

    def test_no_existing_snapshot_creates_new(self, temp_run_dir):
        """No existing snapshot triggers creation."""
        snapshot = refresh_or_load_snapshot_with_catalog(
            "test-run", force_refresh=False, safety_profile="normal"
        )

        assert snapshot is not None
        assert snapshot.snapshot_id.startswith("catalog-")

        # Verify snapshot was persisted
        loaded = RoutingSnapshotStorage.load_snapshot("test-run")
        assert loaded is not None


class TestFallbackBehavior:
    """Test fallback to default snapshot when catalog unavailable."""

    def test_fallback_to_default_on_empty_catalog(self, temp_run_dir, monkeypatch):
        """Falls back to default snapshot if catalog is empty."""

        def mock_load_empty_catalog():
            return []

        monkeypatch.setattr(
            "autopack.model_routing_refresh.load_model_catalog", mock_load_empty_catalog
        )

        snapshot = refresh_routing_snapshot("test-run", safety_profile="normal")

        # Should fall back to default snapshot
        assert snapshot is not None
        assert snapshot.snapshot_id.startswith("default-")


class TestEndToEndRoutingRefresh:
    """End-to-end tests for routing refresh workflow."""

    def test_full_workflow_catalog_to_persistence(self, temp_run_dir):
        """End-to-end: catalog load → selection → snapshot → persistence."""
        # 1. Refresh snapshot (will use catalog)
        snapshot = refresh_or_load_snapshot_with_catalog(
            "test-run", force_refresh=True, safety_profile="normal"
        )

        # 2. Verify snapshot properties
        assert snapshot.snapshot_id.startswith("catalog-")
        assert len(snapshot.entries) == 3

        # 3. Verify each tier has entry
        haiku = snapshot.get_model_for_tier("haiku")
        sonnet = snapshot.get_model_for_tier("sonnet")
        opus = snapshot.get_model_for_tier("opus")

        assert haiku is not None
        assert sonnet is not None
        assert opus is not None

        # 4. Verify escalation works
        escalated = snapshot.escalate_tier("haiku")
        assert escalated is not None
        assert escalated.tier == "sonnet"

        # 5. Verify persistence
        loaded = RoutingSnapshotStorage.load_snapshot("test-run")
        assert loaded is not None
        assert loaded.snapshot_id == snapshot.snapshot_id

    def test_reproducible_selection_across_refreshes(self, temp_run_dir):
        """Selection is deterministic across multiple refreshes."""
        # Create two snapshots for same run (different IDs)
        snapshot1 = create_catalog_backed_snapshot("test-run-1", safety_profile="normal")
        snapshot2 = create_catalog_backed_snapshot("test-run-2", safety_profile="normal")

        # Model selections should be identical (same catalog, same safety profile)
        for tier in ["haiku", "sonnet", "opus"]:
            entry1 = snapshot1.get_model_for_tier(tier)
            entry2 = snapshot2.get_model_for_tier(tier)

            assert entry1.model_id == entry2.model_id
            assert entry1.tier == entry2.tier
            assert entry1.cost_per_1k_input == entry2.cost_per_1k_input
            assert entry1.cost_per_1k_output == entry2.cost_per_1k_output
