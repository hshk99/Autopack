"""Tests for credential rotation tracking.

Tests the rotation tracker: lifecycle tracking, scope validation,
rotation warnings, and least privilege enforcement.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from autopack.credentials import (
    CredentialScope,
    CredentialEnvironment,
    RotationPolicy,
    CredentialRecord,
    CredentialRotationTracker,
    DEFAULT_ROTATION_POLICIES,
)


class TestCredentialRecord:
    """Tests for CredentialRecord model."""

    def test_age_days_new_credential(self):
        """New credential has zero age."""
        record = CredentialRecord(
            provider="youtube",
            credential_id="cred-123",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
            created_at=datetime.now(timezone.utc),
        )
        assert record.age_days() == 0

    def test_age_days_old_credential(self):
        """Old credential reports correct age."""
        created = datetime.now(timezone.utc) - timedelta(days=30)
        record = CredentialRecord(
            provider="etsy",
            credential_id="cred-456",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.WRITE],
            created_at=created,
        )
        assert record.age_days() == 30

    def test_age_days_uses_rotated_at(self):
        """Age calculation uses rotated_at if set."""
        created = datetime.now(timezone.utc) - timedelta(days=100)
        rotated = datetime.now(timezone.utc) - timedelta(days=10)
        record = CredentialRecord(
            provider="shopify",
            credential_id="cred-789",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.PUBLISH],
            created_at=created,
            rotated_at=rotated,
        )
        assert record.age_days() == 10

    def test_is_stale(self):
        """is_stale uses policy threshold."""
        policy = RotationPolicy(provider="test", max_age_days=30)
        old_record = CredentialRecord(
            provider="test",
            credential_id="old",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=45),
        )
        new_record = CredentialRecord(
            provider="test",
            credential_id="new",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=15),
        )
        assert old_record.is_stale(policy) is True
        assert new_record.is_stale(policy) is False

    def test_is_critical(self):
        """is_critical uses policy critical threshold."""
        policy = RotationPolicy(provider="test", critical_age_days=60)
        critical_record = CredentialRecord(
            provider="test",
            credential_id="critical",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
        assert critical_record.is_critical(policy) is True

    def test_has_scope(self):
        """has_scope checks credential scopes."""
        record = CredentialRecord(
            provider="youtube",
            credential_id="scoped",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ, CredentialScope.WRITE],
            created_at=datetime.now(timezone.utc),
        )
        assert record.has_scope(CredentialScope.READ) is True
        assert record.has_scope(CredentialScope.WRITE) is True
        assert record.has_scope(CredentialScope.PUBLISH) is False

    def test_can_perform_no_restrictions(self):
        """can_perform allows all actions when no restrictions."""
        record = CredentialRecord(
            provider="test",
            credential_id="unrestricted",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[],
            created_at=datetime.now(timezone.utc),
            allowed_actions=[],  # No restrictions
        )
        assert record.can_perform("any_action") is True

    def test_can_perform_with_restrictions(self):
        """can_perform enforces allowed actions list."""
        record = CredentialRecord(
            provider="test",
            credential_id="restricted",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[],
            created_at=datetime.now(timezone.utc),
            allowed_actions=["read_listings", "update_listings"],
        )
        assert record.can_perform("read_listings") is True
        assert record.can_perform("update_listings") is True
        assert record.can_perform("delete_listings") is False

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = CredentialRecord(
            provider="etsy",
            credential_id="cred-abc",
            environment=CredentialEnvironment.STAGING,
            scopes=[CredentialScope.READ, CredentialScope.WRITE],
            created_at=datetime.now(timezone.utc) - timedelta(days=10),
            rotated_at=datetime.now(timezone.utc) - timedelta(days=5),
            last_used_at=datetime.now(timezone.utc) - timedelta(hours=1),
            rotation_count=3,
            refresh_failures=1,
            last_refresh_error="Token expired",
            is_scoped=True,
            allowed_actions=["list_products"],
        )

        data = original.to_dict()
        restored = CredentialRecord.from_dict(data)

        assert restored.provider == original.provider
        assert restored.credential_id == original.credential_id
        assert restored.environment == original.environment
        assert restored.scopes == original.scopes
        assert restored.rotation_count == original.rotation_count
        assert restored.is_scoped == original.is_scoped


class TestRotationPolicy:
    """Tests for RotationPolicy."""

    def test_default_values(self):
        """Default policy values are reasonable."""
        policy = RotationPolicy(provider="test")
        assert policy.max_age_days == 90
        assert policy.critical_age_days == 180
        assert policy.auto_refresh_enabled is False
        assert 7 in policy.notify_at_days

    def test_default_policies_exist(self):
        """Default policies exist for all providers."""
        assert "youtube" in DEFAULT_ROTATION_POLICIES
        assert "etsy" in DEFAULT_ROTATION_POLICIES
        assert "shopify" in DEFAULT_ROTATION_POLICIES
        assert "alpaca" in DEFAULT_ROTATION_POLICIES

    def test_youtube_policy_has_auto_refresh(self):
        """YouTube policy enables auto-refresh."""
        policy = DEFAULT_ROTATION_POLICIES["youtube"]
        assert policy.auto_refresh_enabled is True


class TestCredentialRotationTracker:
    """Tests for CredentialRotationTracker service."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "creds" / "metadata.json"

    @pytest.fixture
    def tracker(self, temp_storage):
        """Create tracker with temp storage."""
        return CredentialRotationTracker(storage_path=temp_storage)

    def test_register_credential(self, tracker):
        """register_credential creates record."""
        record = tracker.register_credential(
            provider="youtube",
            credential_id="yt-cred-001",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ, CredentialScope.PUBLISH],
        )

        assert record.provider == "youtube"
        assert record.credential_id == "yt-cred-001"
        assert record.environment == CredentialEnvironment.PRODUCTION
        assert CredentialScope.PUBLISH in record.scopes

    def test_register_with_allowed_actions(self, tracker):
        """register_credential with allowed_actions sets is_scoped."""
        record = tracker.register_credential(
            provider="etsy",
            credential_id="etsy-limited",
            environment=CredentialEnvironment.STAGING,
            scopes=[CredentialScope.WRITE],
            allowed_actions=["create_listing", "update_listing"],
        )

        assert record.is_scoped is True
        assert "create_listing" in record.allowed_actions

    def test_get_record(self, tracker):
        """get_record retrieves registered credential."""
        tracker.register_credential(
            provider="shopify",
            credential_id="shop-001",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
        )

        record = tracker.get_record("shopify", CredentialEnvironment.PRODUCTION)
        assert record is not None
        assert record.credential_id == "shop-001"

    def test_get_record_not_found(self, tracker):
        """get_record returns None for unknown credential."""
        record = tracker.get_record("unknown", CredentialEnvironment.PRODUCTION)
        assert record is None

    def test_record_rotation(self, tracker):
        """record_rotation updates credential."""
        tracker.register_credential(
            provider="alpaca",
            credential_id="old-key",
            environment=CredentialEnvironment.PAPER,
            scopes=[CredentialScope.TRADE],
        )

        updated = tracker.record_rotation(
            provider="alpaca",
            environment=CredentialEnvironment.PAPER,
            new_credential_id="new-key",
        )

        assert updated.credential_id == "new-key"
        assert updated.rotation_count == 1
        assert updated.rotated_at is not None

    def test_record_rotation_resets_failures(self, tracker):
        """record_rotation resets refresh failures."""
        tracker.register_credential(
            provider="youtube",
            credential_id="failing-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.PUBLISH],
        )

        # Simulate failures
        tracker.record_refresh_failure("youtube", CredentialEnvironment.PRODUCTION, "Error 1")
        tracker.record_refresh_failure("youtube", CredentialEnvironment.PRODUCTION, "Error 2")

        record = tracker.get_record("youtube", CredentialEnvironment.PRODUCTION)
        assert record.refresh_failures == 2

        # Rotation should reset failures
        updated = tracker.record_rotation("youtube", CredentialEnvironment.PRODUCTION, "fresh-key")
        assert updated.refresh_failures == 0
        assert updated.last_refresh_error is None

    def test_record_usage(self, tracker):
        """record_usage updates last_used_at."""
        tracker.register_credential(
            provider="anthropic",
            credential_id="api-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
        )

        record_before = tracker.get_record("anthropic", CredentialEnvironment.PRODUCTION)
        assert record_before.last_used_at is None

        tracker.record_usage("anthropic", CredentialEnvironment.PRODUCTION)

        record_after = tracker.get_record("anthropic", CredentialEnvironment.PRODUCTION)
        assert record_after.last_used_at is not None

    def test_check_rotation_needed_healthy(self, tracker):
        """check_rotation_needed returns False for healthy credential."""
        tracker.register_credential(
            provider="openai",
            credential_id="fresh-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
        )

        needs_rotation, reason = tracker.check_rotation_needed(
            "openai", CredentialEnvironment.PRODUCTION
        )
        assert needs_rotation is False

    def test_check_rotation_needed_stale(self, tracker):
        """check_rotation_needed returns True for stale credential."""
        tracker.register_credential(
            provider="etsy",
            credential_id="old-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.WRITE],
        )

        # Manually age the credential
        record = tracker.get_record("etsy", CredentialEnvironment.PRODUCTION)
        record.created_at = datetime.now(timezone.utc) - timedelta(days=100)

        needs_rotation, reason = tracker.check_rotation_needed(
            "etsy", CredentialEnvironment.PRODUCTION
        )
        assert needs_rotation is True
        assert "exceeds" in reason

    def test_can_perform_action_success(self, tracker):
        """can_perform_action allows valid action."""
        tracker.register_credential(
            provider="youtube",
            credential_id="scoped-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ, CredentialScope.PUBLISH],
            allowed_actions=["upload_video", "get_video"],
        )

        can, error = tracker.can_perform_action(
            provider="youtube",
            environment=CredentialEnvironment.PRODUCTION,
            action="upload_video",
            required_scope=CredentialScope.PUBLISH,
        )
        assert can is True
        assert error is None

    def test_can_perform_action_missing_scope(self, tracker):
        """can_perform_action rejects missing scope."""
        tracker.register_credential(
            provider="etsy",
            credential_id="readonly-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],  # No WRITE scope
        )

        can, error = tracker.can_perform_action(
            provider="etsy",
            environment=CredentialEnvironment.PRODUCTION,
            action="create_listing",
            required_scope=CredentialScope.WRITE,
        )
        assert can is False
        assert "lacks required scope" in error

    def test_can_perform_action_not_in_allowed(self, tracker):
        """can_perform_action rejects action not in allowed list."""
        tracker.register_credential(
            provider="shopify",
            credential_id="limited-key",
            environment=CredentialEnvironment.STAGING,
            scopes=[CredentialScope.WRITE],
            allowed_actions=["update_product"],  # Only update allowed
        )

        can, error = tracker.can_perform_action(
            provider="shopify",
            environment=CredentialEnvironment.STAGING,
            action="delete_product",
        )
        assert can is False
        assert "not in allowed actions" in error

    def test_can_perform_action_critical_credential(self, tracker):
        """can_perform_action rejects critical credential."""
        tracker.register_credential(
            provider="alpaca",
            credential_id="ancient-key",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.TRADE],
        )

        # Age the credential past critical threshold
        record = tracker.get_record("alpaca", CredentialEnvironment.PRODUCTION)
        record.created_at = datetime.now(timezone.utc) - timedelta(days=200)

        can, error = tracker.can_perform_action(
            provider="alpaca",
            environment=CredentialEnvironment.PRODUCTION,
            action="place_order",
            required_scope=CredentialScope.TRADE,
        )
        assert can is False
        assert "immediate rotation" in error

    def test_get_health_report(self, tracker):
        """get_health_report summarizes all credentials."""
        # Register healthy credential
        tracker.register_credential(
            provider="anthropic",
            credential_id="healthy",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
        )

        # Register stale credential
        tracker.register_credential(
            provider="openai",
            credential_id="old",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.READ],
        )
        old_record = tracker.get_record("openai", CredentialEnvironment.PRODUCTION)
        old_record.created_at = datetime.now(timezone.utc) - timedelta(days=200)

        report = tracker.get_health_report()

        assert report["total_credentials"] == 2
        assert report["healthy_count"] == 1
        assert report["overall_status"] in ("warning", "critical")
        assert len(report["healthy"]) == 1
        assert len(report["warnings"]) + len(report["critical"]) == 1

    def test_persistence(self, temp_storage):
        """State persists across tracker instances."""
        # Create and register with first tracker
        tracker1 = CredentialRotationTracker(storage_path=temp_storage)
        tracker1.register_credential(
            provider="youtube",
            credential_id="persistent",
            environment=CredentialEnvironment.PRODUCTION,
            scopes=[CredentialScope.PUBLISH],
        )
        tracker1.record_rotation("youtube", CredentialEnvironment.PRODUCTION, "rotated")

        # Load with new tracker
        tracker2 = CredentialRotationTracker(storage_path=temp_storage)

        record = tracker2.get_record("youtube", CredentialEnvironment.PRODUCTION)
        assert record is not None
        assert record.credential_id == "rotated"
        assert record.rotation_count == 1


class TestCredentialEnvironment:
    """Tests for CredentialEnvironment enum."""

    def test_all_environments(self):
        """All expected environments exist."""
        assert CredentialEnvironment.DEVELOPMENT
        assert CredentialEnvironment.STAGING
        assert CredentialEnvironment.PRODUCTION
        assert CredentialEnvironment.PAPER


class TestCredentialScope:
    """Tests for CredentialScope enum."""

    def test_all_scopes(self):
        """All expected scopes exist."""
        assert CredentialScope.READ
        assert CredentialScope.WRITE
        assert CredentialScope.DELETE
        assert CredentialScope.PUBLISH
        assert CredentialScope.TRADE
        assert CredentialScope.ADMIN
