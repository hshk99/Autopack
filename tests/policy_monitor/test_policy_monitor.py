"""Tests for policy monitor.

Validates gap analysis requirement 6.2:
- Provider policy/compliance monitors
- Policy snapshot freshness gating
- Change detection and acknowledgment
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from autopack.policy_monitor import PolicyMonitor, PolicySnapshot, PolicyStatus
from autopack.policy_monitor.models import PolicyCategory, ProviderPolicyConfig


class TestPolicySnapshot:
    """Test PolicySnapshot model."""

    def test_compute_hash_deterministic(self):
        """Hash is deterministic for same content."""
        content = "This is some policy content."
        hash1 = PolicySnapshot.compute_hash(content)
        hash2 = PolicySnapshot.compute_hash(content)
        assert hash1 == hash2

    def test_compute_hash_changes_with_content(self):
        """Hash changes when content changes."""
        hash1 = PolicySnapshot.compute_hash("Original content")
        hash2 = PolicySnapshot.compute_hash("Modified content")
        assert hash1 != hash2

    def test_is_fresh_within_threshold(self):
        """Snapshot is fresh when within threshold."""
        now = datetime.now(timezone.utc)
        snapshot = PolicySnapshot(
            snapshot_id="test-1",
            provider="youtube",
            policy_url="https://example.com",
            policy_category=PolicyCategory.CONTENT_POLICY,
            content_hash="abc123",
            fetched_at=now - timedelta(days=3),
            freshness_days=7,
        )
        assert snapshot.is_fresh(now) is True

    def test_is_stale_past_threshold(self):
        """Snapshot is stale when past threshold."""
        now = datetime.now(timezone.utc)
        snapshot = PolicySnapshot(
            snapshot_id="test-1",
            provider="youtube",
            policy_url="https://example.com",
            policy_category=PolicyCategory.CONTENT_POLICY,
            content_hash="abc123",
            fetched_at=now - timedelta(days=10),
            freshness_days=7,
        )
        assert snapshot.is_fresh(now) is False

    def test_to_dict_structure(self):
        """to_dict returns expected structure."""
        now = datetime.now(timezone.utc)
        snapshot = PolicySnapshot(
            snapshot_id="test-1",
            provider="youtube",
            policy_url="https://example.com",
            policy_category=PolicyCategory.CONTENT_POLICY,
            content_hash="abc123",
            fetched_at=now,
        )
        result = snapshot.to_dict()

        assert "snapshot_id" in result
        assert "provider" in result
        assert "content_hash" in result
        assert "fetched_at" in result
        assert "status" in result


class TestPolicyMonitor:
    """Test PolicyMonitor service."""

    @pytest.fixture
    def monitor(self):
        with TemporaryDirectory() as tmpdir:
            yield PolicyMonitor(storage_dir=Path(tmpdir))

    def test_create_snapshot(self, monitor):
        """Can create a policy snapshot."""
        snapshot = monitor.create_snapshot(
            provider="youtube",
            policy_url="https://example.com/policy",
            category=PolicyCategory.CONTENT_POLICY,
            content="Policy content here",
            content_summary="Content policy summary",
        )

        assert snapshot.snapshot_id is not None
        assert snapshot.provider == "youtube"
        assert snapshot.policy_category == PolicyCategory.CONTENT_POLICY
        assert snapshot.status == PolicyStatus.FRESH

    def test_snapshot_persisted(self, monitor):
        """Snapshots are persisted to storage."""
        monitor.create_snapshot(
            provider="youtube",
            policy_url="https://example.com/policy",
            category=PolicyCategory.CONTENT_POLICY,
            content="Policy content",
        )

        # Create new monitor with same storage dir
        monitor2 = PolicyMonitor(storage_dir=monitor.storage_dir)
        snapshot = monitor2.get_snapshot("youtube", PolicyCategory.CONTENT_POLICY)

        assert snapshot is not None
        assert snapshot.provider == "youtube"

    def test_detect_content_change(self, monitor):
        """Content changes are detected."""
        # Create initial snapshot
        monitor.create_snapshot(
            provider="etsy",
            policy_url="https://example.com/policy",
            category=PolicyCategory.PROHIBITED_ITEMS,
            content="Original policy content",
        )

        # Create snapshot with changed content
        snapshot = monitor.create_snapshot(
            provider="etsy",
            policy_url="https://example.com/policy",
            category=PolicyCategory.PROHIBITED_ITEMS,
            content="MODIFIED policy content",
        )

        assert snapshot.status == PolicyStatus.CHANGED

    def test_policy_gate_blocks_missing(self, monitor):
        """Policy gate blocks when snapshots are missing."""
        result = monitor.check_policy_gate("youtube", "publish")

        assert result.can_proceed is False
        assert len(result.missing_snapshots) > 0
        assert "missing" in result.error_message.lower()

    def test_policy_gate_blocks_stale(self, monitor):
        """Policy gate blocks when snapshots are stale."""
        # Create a stale snapshot
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=30)

        snapshot = PolicySnapshot(
            snapshot_id="test-1",
            provider="youtube",
            policy_url="https://example.com",
            policy_category=PolicyCategory.CONTENT_POLICY,
            content_hash="abc123",
            fetched_at=old_time,
            freshness_days=7,
        )
        monitor._snapshots["youtube"] = {
            PolicyCategory.CONTENT_POLICY.value: snapshot,
        }

        result = monitor.check_policy_gate(
            "youtube",
            "publish",
            required_categories=[PolicyCategory.CONTENT_POLICY],
        )

        assert result.can_proceed is False
        assert PolicyCategory.CONTENT_POLICY.value in result.stale_policies

    def test_policy_gate_blocks_unacknowledged(self, monitor):
        """Policy gate blocks unacknowledged changes."""
        # Create a snapshot in CHANGED status
        snapshot = PolicySnapshot(
            snapshot_id="test-1",
            provider="youtube",
            policy_url="https://example.com",
            policy_category=PolicyCategory.CONTENT_POLICY,
            content_hash="abc123",
            fetched_at=datetime.now(timezone.utc),
            status=PolicyStatus.CHANGED,
        )
        monitor._snapshots["youtube"] = {
            PolicyCategory.CONTENT_POLICY.value: snapshot,
        }

        result = monitor.check_policy_gate(
            "youtube",
            "publish",
            required_categories=[PolicyCategory.CONTENT_POLICY],
        )

        assert result.can_proceed is False
        assert PolicyCategory.CONTENT_POLICY.value in result.unacknowledged_changes

    def test_policy_gate_allows_fresh(self, monitor):
        """Policy gate allows fresh, acknowledged snapshots."""
        # Create fresh snapshots for all youtube policies
        config = ProviderPolicyConfig.youtube()
        for policy in config.policies:
            category = policy["category"]
            snapshot = PolicySnapshot(
                snapshot_id=f"test-{category.value}",
                provider="youtube",
                policy_url=policy["url"],
                policy_category=category,
                content_hash="abc123",
                fetched_at=datetime.now(timezone.utc),
                status=PolicyStatus.FRESH,
            )
            if "youtube" not in monitor._snapshots:
                monitor._snapshots["youtube"] = {}
            monitor._snapshots["youtube"][category.value] = snapshot

        result = monitor.check_policy_gate("youtube", "publish")

        assert result.can_proceed is True
        assert result.error_message is None

    def test_acknowledge_change(self, monitor):
        """Can acknowledge a policy change."""
        # Create snapshot in CHANGED status
        monitor.create_snapshot(
            provider="youtube",
            policy_url="https://example.com/policy",
            category=PolicyCategory.CONTENT_POLICY,
            content="Original content",
        )
        # Create change
        monitor.create_snapshot(
            provider="youtube",
            policy_url="https://example.com/policy",
            category=PolicyCategory.CONTENT_POLICY,
            content="Changed content",
        )

        # Acknowledge
        updated = monitor.acknowledge_change(
            provider="youtube",
            category=PolicyCategory.CONTENT_POLICY,
            operator="admin",
            notes="Reviewed and approved",
        )

        assert updated.status == PolicyStatus.ACKNOWLEDGED
        assert updated.acknowledged_by == "admin"
        assert updated.acknowledged_at is not None

    def test_get_unacknowledged_changes(self, monitor):
        """Can get list of unacknowledged changes."""
        # Create a change
        monitor.create_snapshot(
            provider="etsy",
            policy_url="https://example.com/policy",
            category=PolicyCategory.PROHIBITED_ITEMS,
            content="Original",
        )
        monitor.create_snapshot(
            provider="etsy",
            policy_url="https://example.com/policy",
            category=PolicyCategory.PROHIBITED_ITEMS,
            content="Changed",
        )

        unacknowledged = monitor.get_unacknowledged_changes()

        assert len(unacknowledged) == 1
        assert unacknowledged[0].provider == "etsy"
        assert unacknowledged[0].status == PolicyStatus.CHANGED

    def test_health_summary_structure(self, monitor):
        """Health summary has expected structure."""
        summary = monitor.get_health_summary()

        assert "checked_at" in summary
        assert "providers" in summary
        assert "overall_status" in summary
        assert "stale_count" in summary
        assert "changed_count" in summary
        assert "missing_count" in summary

    def test_unknown_provider_blocked(self, monitor):
        """Unknown provider is blocked by gate."""
        result = monitor.check_policy_gate("unknown_provider", "publish")

        assert result.can_proceed is False
        assert "Unknown provider" in result.error_message


class TestProviderPolicyConfig:
    """Test provider configuration helpers."""

    def test_youtube_config(self):
        """YouTube config has expected policies."""
        config = ProviderPolicyConfig.youtube()

        assert config.provider == "youtube"
        assert len(config.policies) >= 3
        assert config.freshness_days == 7

        categories = [p["category"] for p in config.policies]
        assert PolicyCategory.CONTENT_POLICY in categories
        assert PolicyCategory.AI_DISCLOSURE in categories

    def test_etsy_config(self):
        """Etsy config has expected policies."""
        config = ProviderPolicyConfig.etsy()

        assert config.provider == "etsy"
        assert len(config.policies) >= 2

        categories = [p["category"] for p in config.policies]
        assert PolicyCategory.PROHIBITED_ITEMS in categories
        assert PolicyCategory.INTELLECTUAL_PROPERTY in categories

    def test_shopify_config(self):
        """Shopify config has expected policies."""
        config = ProviderPolicyConfig.shopify()

        assert config.provider == "shopify"
        assert len(config.policies) >= 1
