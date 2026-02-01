"""Tests for memory maintenance metrics (IMP-MEDIUM-001).

Tests cover:
- Memory freshness metrics calculation
- Freshness ratio, stale entries count, and pruning effectiveness
- Integration with telemetry system
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from autopack.memory.maintenance import calculate_memory_freshness_metrics, run_maintenance


class TestMemoryFreshnessMetrics:
    """Tests for IMP-MEDIUM-001: Memory freshness metrics calculation."""

    def test_calculate_freshness_empty_collection(self):
        """Verify freshness calculation handles empty collections."""
        mock_store = MagicMock()
        mock_store.scroll.return_value = []

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert metrics["freshness_ratio"] == 0.0
        assert metrics["stale_entries_count"] == 0
        assert metrics["total_entries"] == 0
        assert metrics["ttl_days"] == 30

    def test_calculate_freshness_all_fresh_entries(self):
        """Verify freshness calculation when all entries are fresh."""
        mock_store = MagicMock()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # Return 100 fresh entries
        mock_store.scroll.return_value = [
            {"id": f"doc-{i}", "payload": {"timestamp": fresh_timestamp}} for i in range(100)
        ]

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert metrics["freshness_ratio"] == 1.0
        assert metrics["stale_entries_count"] == 0
        assert metrics["total_entries"] == 100
        assert metrics["ttl_days"] == 30

    def test_calculate_freshness_mixed_entries(self):
        """Verify freshness calculation with mix of fresh and stale entries."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        entries = []
        # Add 70 fresh entries
        for i in range(70):
            entries.append({"id": f"fresh-{i}", "payload": {"timestamp": fresh_timestamp}})
        # Add 30 stale entries
        for i in range(30):
            entries.append({"id": f"stale-{i}", "payload": {"timestamp": old_timestamp}})

        mock_store.scroll.return_value = entries

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert metrics["freshness_ratio"] == 0.7
        assert metrics["stale_entries_count"] == 30
        assert metrics["total_entries"] == 100
        assert metrics["ttl_days"] == 30

    def test_calculate_freshness_all_stale_entries(self):
        """Verify freshness calculation when all entries are stale."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

        # Return 100 stale entries
        mock_store.scroll.return_value = [
            {"id": f"doc-{i}", "payload": {"timestamp": old_timestamp}} for i in range(100)
        ]

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert metrics["freshness_ratio"] == 0.0
        assert metrics["stale_entries_count"] == 100
        assert metrics["total_entries"] == 100
        assert metrics["ttl_days"] == 30

    def test_calculate_freshness_multiple_collections(self):
        """Verify freshness calculation aggregates across multiple collections."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # Simulate two collections with different freshness profiles
        mock_store.scroll.side_effect = [
            # First collection: 50 fresh, 50 stale
            [
                *(
                    [
                        {"id": f"fresh-{i}", "payload": {"timestamp": fresh_timestamp}}
                        for i in range(50)
                    ]
                ),
                *(
                    [
                        {"id": f"stale-{i}", "payload": {"timestamp": old_timestamp}}
                        for i in range(50)
                    ]
                ),
            ],
            # Second collection: 100 fresh
            [{"id": f"fresh2-{i}", "payload": {"timestamp": fresh_timestamp}} for i in range(100)],
        ]

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["collection1", "collection2"],
        )

        # Total: 200 entries, 150 fresh, 50 stale = 0.75 freshness ratio
        assert metrics["freshness_ratio"] == 0.75
        assert metrics["stale_entries_count"] == 50
        assert metrics["total_entries"] == 200
        assert metrics["ttl_days"] == 30

    def test_calculate_freshness_handles_missing_timestamps(self):
        """Verify freshness calculation handles entries without timestamps gracefully."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

        entries = [
            {"id": "doc-1", "payload": {"timestamp": old_timestamp}},
            {"id": "doc-2", "payload": {}},  # Missing timestamp
            {"id": "doc-3", "payload": {"timestamp": old_timestamp}},
        ]
        mock_store.scroll.return_value = entries

        metrics = calculate_memory_freshness_metrics(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        # Should count all 3 entries, but only 2 identified as stale
        # (entry without timestamp is not counted as stale)
        assert metrics["total_entries"] == 3
        assert metrics["stale_entries_count"] == 2
        assert metrics["freshness_ratio"] == pytest.approx(1 / 3, rel=0.01)

    def test_run_maintenance_includes_freshness_metrics(self):
        """Verify run_maintenance includes freshness metrics in stats."""
        mock_store = MagicMock()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # Mock scroll responses for freshness calculation
        mock_store.scroll.side_effect = [
            # For freshness_metrics calculation
            [{"id": f"doc-{i}", "payload": {"timestamp": fresh_timestamp}} for i in range(100)],
            # Additional scroll calls may occur for pruning
        ]
        mock_store.delete.return_value = 0

        stats = run_maintenance(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
        )

        # Verify freshness metrics are in stats
        assert "freshness_metrics" in stats
        assert stats["freshness_metrics"]["freshness_ratio"] == 1.0
        assert stats["freshness_metrics"]["total_entries"] == 100
        assert stats["freshness_metrics"]["stale_entries_count"] == 0
        assert stats["freshness_metrics"]["ttl_days"] == 30

    def test_run_maintenance_calculates_pruning_effectiveness(self):
        """Verify run_maintenance calculates pruning effectiveness."""
        mock_store = MagicMock()

        # Mock scroll to return some entries for freshness calc
        mock_store.scroll.side_effect = [
            [{"id": "doc-1", "payload": {"timestamp": "old"}}],  # For freshness
        ]

        # Mock pruning operations
        mock_store.delete.return_value = 10

        # Patch the individual pruning functions to return specific values
        with patch("autopack.memory.maintenance.prune_old_entries", return_value=10):
            with patch("autopack.memory.maintenance.tombstone_superseded_planning", return_value=5):
                with patch("autopack.memory.maintenance.prune_stale_rules", return_value=0):
                    stats = run_maintenance(
                        store=mock_store,
                        project_id="test-project",
                        ttl_days=30,
                    )

        # Verify pruning effectiveness is calculated
        # With 10 pruned, 5 tombstoned, 0 rules pruned:
        # pruning_effectiveness = 10 / (10 + 5 + 0) = 0.6667
        assert "pruning_effectiveness" in stats
        assert stats["pruning_effectiveness"] == pytest.approx(0.6667, rel=0.01)

    def test_run_maintenance_zero_operations_pruning_effectiveness(self):
        """Verify pruning effectiveness is 0.0 when no operations occur."""
        mock_store = MagicMock()

        # Mock scroll to return some entries for freshness calc
        mock_store.scroll.side_effect = [
            [{"id": "doc-1", "payload": {"timestamp": "recent"}}],
        ]

        # Patch all pruning functions to return 0
        with patch("autopack.memory.maintenance.prune_old_entries", return_value=0):
            with patch("autopack.memory.maintenance.tombstone_superseded_planning", return_value=0):
                with patch("autopack.memory.maintenance.prune_stale_rules", return_value=0):
                    stats = run_maintenance(
                        store=mock_store,
                        project_id="test-project",
                        ttl_days=30,
                    )

        # When no operations occur, pruning effectiveness is 0.0
        assert stats["pruning_effectiveness"] == 0.0
