"""Tests for rule lifecycle management with decay and pruning.

IMP-REL-002: Tests for rule lifecycle tracking and automatic pruning.

Tests cover:
- Lifecycle tracking fields added to rules (created_at, last_applied, application_count)
- record_rule_application() updates tracking fields
- prune_stale_rules() removes rules with insufficient usage
- Integration with maintenance cycle
"""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest


class TestRuleLifecycleTracking:
    """Tests for rule lifecycle tracking in MemoryService."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock FaissStore."""
        store = Mock()
        store.upsert = Mock(return_value=1)
        store.get_payload = Mock(return_value=None)
        store.update_payload = Mock(return_value=True)
        store.delete = Mock(return_value=1)
        store.scroll = Mock(return_value=[])
        return store

    @pytest.fixture
    def memory_service(self, mock_store):
        """Create a MemoryService with mocked store."""
        from autopack.memory.deduplication import ContentDeduplicator
        from autopack.memory.memory_service import MemoryService

        with patch.object(MemoryService, "__init__", lambda self, **kwargs: None):
            service = MemoryService()
            service.enabled = True
            service._deduplicator = ContentDeduplicator()  # IMP-MAINT-003 extraction
            service.store = mock_store
            service.top_k = 10
            yield service

    def test_rule_insight_gets_lifecycle_fields(self, memory_service):
        """Rules should have lifecycle tracking fields added."""
        with patch("autopack.memory.memory_service.TelemetryFeedbackValidator") as MockValidator:
            MockValidator.validate_insight.return_value = (True, [])

            with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
                mock_embed.return_value = [0.1] * 768

                # Create a rule insight
                rule_insight = {
                    "insight_type": "promoted_rule",
                    "description": "Test rule description",
                    "content": "Test rule content",
                    "is_rule": True,
                    "suggested_action": "Take this action",
                    "severity": "high",
                    "confidence": 0.85,
                    "run_id": "run_1",
                    "phase_id": "phase_1",
                }

                memory_service.write_telemetry_insight(rule_insight, project_id="test_project")

                # Verify upsert was called
                assert memory_service.store.upsert.called

                # Get the payload that was passed to upsert
                call_args = memory_service.store.upsert.call_args
                points = call_args[0][1]  # Second positional arg
                payload = points[0]["payload"]

                # Verify lifecycle fields are present
                assert "created_at" in payload
                assert "last_applied" in payload
                assert payload["last_applied"] is None
                assert "application_count" in payload
                assert payload["application_count"] == 0
                assert payload["is_rule"] is True

    def test_record_rule_application_updates_fields(self, memory_service):
        """record_rule_application should update last_applied and increment count."""
        # Setup: existing rule payload
        existing_payload = {
            "type": "rule",
            "is_rule": True,
            "application_count": 2,
            "last_applied": None,
            "created_at": "2025-01-01T00:00:00+00:00",
        }
        memory_service.store.get_payload.return_value = existing_payload

        # Call record_rule_application
        rule_id = "rule:test_project:abc123"
        result = memory_service.record_rule_application(rule_id)

        assert result is True

        # Verify update_payload was called with incremented count
        assert memory_service.store.update_payload.called
        call_args = memory_service.store.update_payload.call_args
        updated_payload = call_args[0][2]  # Third positional arg

        assert updated_payload["application_count"] == 3
        assert updated_payload["last_applied"] is not None

    def test_record_rule_application_not_found(self, memory_service):
        """record_rule_application should return False if rule not found."""
        memory_service.store.get_payload.return_value = None

        result = memory_service.record_rule_application("nonexistent_rule")

        assert result is False
        assert not memory_service.store.update_payload.called

    def test_rule_insight_preserves_existing_lifecycle_metadata(self, memory_service):
        """Existing lifecycle metadata should be preserved."""
        with patch("autopack.memory.memory_service.TelemetryFeedbackValidator") as MockValidator:
            MockValidator.validate_insight.return_value = (True, [])

            with patch("autopack.memory.memory_service.sync_embed_text") as mock_embed:
                mock_embed.return_value = [0.1] * 768

                # Rule with existing lifecycle metadata
                rule_insight = {
                    "insight_type": "effectiveness_rule",
                    "description": "Test rule",
                    "content": "Test content",
                    "is_rule": True,
                    "metadata": {
                        "created_at": "2025-01-15T10:00:00+00:00",
                        "last_applied": "2025-01-20T10:00:00+00:00",
                        "application_count": 5,
                    },
                }

                memory_service.write_telemetry_insight(rule_insight, project_id="test_project")

                call_args = memory_service.store.upsert.call_args
                points = call_args[0][1]
                payload = points[0]["payload"]

                # Existing values should be preserved
                assert payload["created_at"] == "2025-01-15T10:00:00+00:00"
                assert payload["last_applied"] == "2025-01-20T10:00:00+00:00"
                assert payload["application_count"] == 5


class TestPruneStaleRules:
    """Tests for prune_stale_rules in maintenance."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock FaissStore."""
        store = Mock()
        store.scroll = Mock(return_value=[])
        store.delete = Mock(return_value=0)
        return store

    def test_prune_stale_rules_removes_old_low_usage_rules(self, mock_store):
        """Rules older than max_age with low usage should be pruned."""
        from autopack.memory.maintenance import prune_stale_rules

        # Setup: old rule with insufficient applications
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        mock_store.scroll.return_value = [
            {
                "id": "rule:test:old_unused",
                "payload": {
                    "type": "rule",
                    "is_rule": True,
                    "created_at": old_date,
                    "application_count": 1,  # Less than min_applications (3)
                    "project_id": "test_project",
                },
            }
        ]
        mock_store.delete.return_value = 1

        result = prune_stale_rules(
            mock_store,
            project_id="test_project",
            max_age_days=30,
            min_applications=3,
        )

        assert result == 1
        mock_store.delete.assert_called_once()
        deleted_ids = mock_store.delete.call_args[0][1]
        assert "rule:test:old_unused" in deleted_ids

    def test_prune_stale_rules_keeps_active_rules(self, mock_store):
        """Rules with sufficient applications should not be pruned."""
        from autopack.memory.maintenance import prune_stale_rules

        # Setup: old rule with sufficient applications
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        mock_store.scroll.return_value = [
            {
                "id": "rule:test:old_active",
                "payload": {
                    "type": "rule",
                    "is_rule": True,
                    "created_at": old_date,
                    "application_count": 5,  # More than min_applications (3)
                    "project_id": "test_project",
                },
            }
        ]

        result = prune_stale_rules(
            mock_store,
            project_id="test_project",
            max_age_days=30,
            min_applications=3,
        )

        assert result == 0
        assert not mock_store.delete.called

    def test_prune_stale_rules_keeps_new_rules(self, mock_store):
        """New rules (within max_age) should not be pruned."""
        from autopack.memory.maintenance import prune_stale_rules

        # Setup: new rule with low applications (should not be pruned yet)
        new_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        mock_store.scroll.return_value = [
            {
                "id": "rule:test:new_unused",
                "payload": {
                    "type": "rule",
                    "is_rule": True,
                    "created_at": new_date,
                    "application_count": 1,
                    "project_id": "test_project",
                },
            }
        ]

        result = prune_stale_rules(
            mock_store,
            project_id="test_project",
            max_age_days=30,
            min_applications=3,
        )

        assert result == 0
        assert not mock_store.delete.called

    def test_prune_stale_rules_ignores_non_rules(self, mock_store):
        """Non-rule entries should not be affected."""
        from autopack.memory.maintenance import prune_stale_rules

        # Setup: regular hint (not a rule)
        old_date = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        mock_store.scroll.return_value = [
            {
                "id": "hint:test:old_hint",
                "payload": {
                    "type": "hint",
                    "is_rule": False,
                    "created_at": old_date,
                    "project_id": "test_project",
                },
            }
        ]

        result = prune_stale_rules(
            mock_store,
            project_id="test_project",
            max_age_days=30,
            min_applications=3,
        )

        assert result == 0
        assert not mock_store.delete.called


class TestMaintenanceIntegration:
    """Tests for rule pruning integration with maintenance cycle."""

    def test_run_maintenance_includes_rule_pruning(self):
        """run_maintenance should call prune_stale_rules."""
        from autopack.memory.maintenance import run_maintenance

        mock_store = Mock()
        mock_store.scroll.return_value = []
        mock_store.delete.return_value = 0

        with patch("autopack.memory.maintenance.prune_old_entries") as mock_prune_old:
            mock_prune_old.return_value = 0

            with patch(
                "autopack.memory.maintenance.tombstone_superseded_planning"
            ) as mock_tombstone:
                mock_tombstone.return_value = 0

                with patch("autopack.memory.maintenance.prune_stale_rules") as mock_prune_rules:
                    mock_prune_rules.return_value = 2

                    stats = run_maintenance(
                        mock_store,
                        project_id="test_project",
                        rule_max_age_days=30,
                        rule_min_applications=3,
                    )

                    # Verify prune_stale_rules was called
                    mock_prune_rules.assert_called_once_with(
                        mock_store,
                        "test_project",
                        max_age_days=30,
                        min_applications=3,
                    )

                    # Verify stats include rules_pruned
                    assert stats["rules_pruned"] == 2

    def test_maintenance_config_includes_rule_settings(self):
        """Maintenance config should include rule pruning settings."""
        from autopack.memory.maintenance import _load_maintenance_config

        with patch("autopack.memory.maintenance._load_memory_config") as mock_config:
            mock_config.return_value = {
                "maintenance": {
                    "rule_max_age_days": 45,
                    "rule_min_applications": 5,
                }
            }

            config = _load_maintenance_config()

            assert config["rule_max_age_days"] == 45
            assert config["rule_min_applications"] == 5

    def test_maintenance_config_defaults(self):
        """Maintenance config should have sensible defaults for rule settings."""
        from autopack.memory.maintenance import _load_maintenance_config

        with patch("autopack.memory.maintenance._load_memory_config") as mock_config:
            mock_config.return_value = {"maintenance": {}}

            config = _load_maintenance_config()

            # Should default to 30 days and 3 applications
            assert config["rule_max_age_days"] == 30
            assert config["rule_min_applications"] == 3
