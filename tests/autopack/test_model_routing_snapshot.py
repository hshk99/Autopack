"""
Tests for model routing snapshot system.

Verifies routing snapshot persistence, escalation logic, and budget-aware decisions.
"""

import shutil
from datetime import datetime, timedelta

import pytest

from autopack.model_routing_snapshot import (
    ModelRoutingEntry,
    ModelRoutingSnapshot,
    RoutingSnapshotStorage,
    create_default_snapshot,
    refresh_or_load_snapshot,
)
from autopack.config import settings


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


class TestModelRoutingEntry:
    """Test model routing entry schema."""

    def test_entry_schema_validation(self):
        """Routing entry accepts valid data."""
        entry = ModelRoutingEntry(
            tier="sonnet",
            model_id="claude-3-5-sonnet-20241022",
            provider="anthropic",
            max_tokens=8192,
            max_context_chars=200_000,
            cost_per_1k_input=3.0,
            cost_per_1k_output=15.0,
            safety_compatible=True,
        )
        assert entry.tier == "sonnet"
        assert entry.max_tokens == 8192

    def test_entry_extra_fields_forbidden(self):
        """Routing entry rejects unknown fields."""
        with pytest.raises(ValueError):
            ModelRoutingEntry(
                tier="sonnet",
                model_id="claude-3-5-sonnet-20241022",
                provider="anthropic",
                max_tokens=8192,
                max_context_chars=200_000,
                cost_per_1k_input=3.0,
                cost_per_1k_output=15.0,
                safety_compatible=True,
                unknown_field="should fail",  # type: ignore
            )


class TestModelRoutingSnapshot:
    """Test routing snapshot schema and logic."""

    def test_snapshot_schema_validation(self):
        """Snapshot accepts valid data."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="haiku",
                    model_id="claude-3-5-haiku-20241022",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=1.0,
                    cost_per_1k_output=5.0,
                )
            ],
        )
        assert snapshot.run_id == "test-run"
        assert len(snapshot.entries) == 1

    def test_get_model_for_tier(self):
        """get_model_for_tier returns correct entry."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="haiku",
                    model_id="haiku-model",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=1.0,
                    cost_per_1k_output=5.0,
                ),
                ModelRoutingEntry(
                    tier="sonnet",
                    model_id="sonnet-model",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=3.0,
                    cost_per_1k_output=15.0,
                ),
            ],
        )
        entry = snapshot.get_model_for_tier("sonnet")
        assert entry is not None
        assert entry.model_id == "sonnet-model"

    def test_get_model_for_tier_not_found(self):
        """get_model_for_tier returns None for missing tier."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[],
        )
        entry = snapshot.get_model_for_tier("opus")
        assert entry is None

    def test_get_model_respects_safety_profile(self):
        """Strict safety profile filters out incompatible models."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="haiku",
                    model_id="unsafe-haiku",
                    provider="provider-x",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=1.0,
                    cost_per_1k_output=5.0,
                    safety_compatible=False,
                )
            ],
        )
        # Normal safety: should find it
        entry_normal = snapshot.get_model_for_tier("haiku", safety_profile="normal")
        assert entry_normal is not None

        # Strict safety: should not find it
        entry_strict = snapshot.get_model_for_tier("haiku", safety_profile="strict")
        assert entry_strict is None

    def test_escalate_tier_haiku_to_sonnet(self):
        """Escalation from haiku to sonnet."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="haiku",
                    model_id="haiku-model",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=1.0,
                    cost_per_1k_output=5.0,
                ),
                ModelRoutingEntry(
                    tier="sonnet",
                    model_id="sonnet-model",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=3.0,
                    cost_per_1k_output=15.0,
                ),
            ],
        )
        escalated = snapshot.escalate_tier("haiku")
        assert escalated is not None
        assert escalated.tier == "sonnet"

    def test_escalate_tier_opus_no_further_escalation(self):
        """No escalation beyond opus."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="opus",
                    model_id="opus-model",
                    provider="anthropic",
                    max_tokens=4096,
                    max_context_chars=200_000,
                    cost_per_1k_input=15.0,
                    cost_per_1k_output=75.0,
                )
            ],
        )
        escalated = snapshot.escalate_tier("opus")
        assert escalated is None


class TestRoutingSnapshotStorage:
    """Test routing snapshot persistence."""

    def test_save_and_load_snapshot(self, temp_run_dir, monkeypatch):
        """Roundtrip: save → load preserves all fields."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            entries=[
                ModelRoutingEntry(
                    tier="haiku",
                    model_id="haiku-model",
                    provider="anthropic",
                    max_tokens=8192,
                    max_context_chars=200_000,
                    cost_per_1k_input=1.0,
                    cost_per_1k_output=5.0,
                )
            ],
        )

        RoutingSnapshotStorage.save_snapshot(snapshot)
        loaded = RoutingSnapshotStorage.load_snapshot("test-run")

        assert loaded is not None
        assert loaded.snapshot_id == snapshot.snapshot_id
        assert loaded.run_id == snapshot.run_id
        assert len(loaded.entries) == 1
        assert loaded.entries[0].model_id == "haiku-model"

    def test_load_nonexistent_snapshot(self):
        """Loading nonexistent snapshot returns None."""
        loaded = RoutingSnapshotStorage.load_snapshot("nonexistent-run")
        assert loaded is None

    def test_is_snapshot_fresh(self):
        """Snapshot freshness check."""
        now = datetime.now()
        fresh_snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=now,
            expires_at=now + timedelta(hours=12),
            entries=[],
        )
        assert RoutingSnapshotStorage.is_snapshot_fresh(fresh_snapshot)

        expired_snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-2",
            run_id="test-run",
            created_at=now - timedelta(hours=25),
            expires_at=now - timedelta(hours=1),
            entries=[],
        )
        assert not RoutingSnapshotStorage.is_snapshot_fresh(expired_snapshot)

    def test_snapshot_without_expiry_always_fresh(self):
        """Snapshot without expiry uses created_at age for freshness."""
        snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-1",
            run_id="test-run",
            created_at=datetime.now(),
            expires_at=None,
            entries=[],
        )
        assert RoutingSnapshotStorage.is_snapshot_fresh(snapshot)

        old_snapshot = ModelRoutingSnapshot(
            snapshot_id="snap-2",
            run_id="test-run",
            created_at=datetime.now() - timedelta(hours=48),
            expires_at=None,
            entries=[],
        )
        assert not RoutingSnapshotStorage.is_snapshot_fresh(old_snapshot)


class TestDefaultSnapshot:
    """Test default snapshot creation."""

    def test_create_default_snapshot(self):
        """Default snapshot has all tiers."""
        snapshot = create_default_snapshot("test-run")
        assert snapshot.run_id == "test-run"
        assert len(snapshot.entries) == 3  # haiku, sonnet, opus

        haiku = snapshot.get_model_for_tier("haiku")
        sonnet = snapshot.get_model_for_tier("sonnet")
        opus = snapshot.get_model_for_tier("opus")

        assert haiku is not None
        assert sonnet is not None
        assert opus is not None


class TestRefreshOrLoadSnapshot:
    """Test snapshot refresh logic."""

    def test_refresh_creates_new_snapshot(self, temp_run_dir, monkeypatch):
        """Force refresh creates new snapshot."""
        snapshot = refresh_or_load_snapshot("test-run", force_refresh=True)
        assert snapshot is not None
        assert snapshot.run_id == "test-run"

        # Verify it was saved
        loaded = RoutingSnapshotStorage.load_snapshot("test-run")
        assert loaded is not None

    def test_load_existing_fresh_snapshot(self, temp_run_dir, monkeypatch):
        """Load existing fresh snapshot without refresh."""
        # Create and save a snapshot
        original = create_default_snapshot("test-run")
        original.snapshot_id = "original-snap"
        RoutingSnapshotStorage.save_snapshot(original)

        # Load without refresh
        loaded = refresh_or_load_snapshot("test-run", force_refresh=False)
        assert loaded.snapshot_id == "original-snap"

    def test_refresh_expired_snapshot(self, temp_run_dir, monkeypatch):
        """Expired snapshot is refreshed."""
        # Create expired snapshot
        expired = ModelRoutingSnapshot(
            snapshot_id="expired-snap",
            run_id="test-run",
            created_at=datetime.now() - timedelta(hours=25),
            expires_at=datetime.now() - timedelta(hours=1),
            entries=[],
        )
        RoutingSnapshotStorage.save_snapshot(expired)

        # Load should refresh (now delegates to catalog-backed refresh)
        loaded = refresh_or_load_snapshot("test-run", force_refresh=False)
        assert loaded.snapshot_id != "expired-snap"
        # After Phase D, refresh delegates to catalog (or falls back to default)
        assert loaded.snapshot_id.startswith("catalog-") or loaded.snapshot_id.startswith("default-")
