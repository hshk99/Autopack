"""Tests for automatic memory maintenance scheduling (IMP-MEM-011).

Tests cover:
- Paginated pruning in prune_old_entries() for large collections
- Write-count based maintenance triggering in AutonomousLoop
- Integration of both time-based and write-based triggers
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


from autopack.memory.maintenance import prune_old_entries


class TestPaginatedPruning:
    """Tests for IMP-MEM-011: Paginated pruning in prune_old_entries()."""

    def test_prune_handles_empty_collection(self):
        """Verify pruning handles empty collections gracefully."""
        mock_store = MagicMock()
        mock_store.scroll.return_value = []

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert result == 0
        mock_store.scroll.assert_called_once()
        mock_store.delete.assert_not_called()

    def test_prune_single_batch_within_limit(self):
        """Verify pruning works for collections smaller than batch size."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

        # Return 100 old entries (well under batch limit)
        mock_store.scroll.side_effect = [
            [{"id": f"doc-{i}", "payload": {"timestamp": old_timestamp}} for i in range(100)],
            [],  # Second call returns empty (no more docs)
        ]
        mock_store.delete.return_value = 100

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert result == 100
        assert mock_store.delete.call_count == 1

    def test_prune_paginates_large_collections(self):
        """Verify pruning paginates through collections larger than batch size."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        batch_size = 1000

        # Simulate 2500 old entries across 3 batches
        mock_store.scroll.side_effect = [
            # First batch: 1000 entries
            [
                {"id": f"batch1-{i}", "payload": {"timestamp": old_timestamp}}
                for i in range(batch_size)
            ],
            # Second batch: 1000 entries
            [
                {"id": f"batch2-{i}", "payload": {"timestamp": old_timestamp}}
                for i in range(batch_size)
            ],
            # Third batch: 500 entries (partial batch indicates end)
            [{"id": f"batch3-{i}", "payload": {"timestamp": old_timestamp}} for i in range(500)],
        ]
        mock_store.delete.side_effect = [1000, 1000, 500]

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
            batch_size=batch_size,
        )

        assert result == 2500
        assert mock_store.scroll.call_count == 3
        assert mock_store.delete.call_count == 3

    def test_prune_stops_when_no_old_entries_in_batch(self):
        """Verify pruning stops when a batch has no old entries."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # First batch: 100 old entries
        # Second batch: 100 fresh entries (nothing to prune)
        mock_store.scroll.side_effect = [
            [{"id": f"old-{i}", "payload": {"timestamp": old_timestamp}} for i in range(100)],
            [{"id": f"fresh-{i}", "payload": {"timestamp": fresh_timestamp}} for i in range(100)],
        ]
        mock_store.delete.return_value = 100

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert result == 100
        assert mock_store.delete.call_count == 1

    def test_prune_handles_mixed_timestamps(self):
        """Verify pruning correctly filters old from fresh entries."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        fresh_timestamp = datetime.now(timezone.utc).isoformat()

        # Mix of old and fresh entries
        mock_store.scroll.side_effect = [
            [
                {"id": "old-1", "payload": {"timestamp": old_timestamp}},
                {"id": "fresh-1", "payload": {"timestamp": fresh_timestamp}},
                {"id": "old-2", "payload": {"timestamp": old_timestamp}},
                {"id": "fresh-2", "payload": {"timestamp": fresh_timestamp}},
            ],
            [],  # No more entries
        ]
        mock_store.delete.return_value = 2

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["test_collection"],
        )

        assert result == 2
        # Verify only old entries were passed to delete
        mock_store.delete.assert_called_once()
        deleted_ids = mock_store.delete.call_args[0][1]
        assert "old-1" in deleted_ids
        assert "old-2" in deleted_ids
        assert "fresh-1" not in deleted_ids
        assert "fresh-2" not in deleted_ids

    def test_prune_multiple_collections(self):
        """Verify pruning iterates through multiple collections."""
        mock_store = MagicMock()
        old_timestamp = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()

        # Each collection has 50 old entries (under batch_size, so one call per collection)
        # With batch_size optimization, if docs < batch_size, we break immediately
        mock_store.scroll.side_effect = [
            [{"id": f"col1-{i}", "payload": {"timestamp": old_timestamp}} for i in range(50)],
            [{"id": f"col2-{i}", "payload": {"timestamp": old_timestamp}} for i in range(50)],
        ]
        mock_store.delete.return_value = 50

        result = prune_old_entries(
            store=mock_store,
            project_id="test-project",
            ttl_days=30,
            collections=["collection1", "collection2"],
        )

        assert result == 100
        assert mock_store.delete.call_count == 2


class TestWriteCountMaintenance:
    """Tests for IMP-MEM-011: Write-count based maintenance triggering."""

    def test_loop_has_write_count_attributes(self):
        """Verify AutonomousLoop has write-count tracking attributes."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        assert hasattr(loop, "_memory_write_count")
        assert hasattr(loop, "_maintenance_write_threshold")
        assert hasattr(loop, "_last_maintenance_write_count")
        assert loop._memory_write_count == 0
        assert loop._maintenance_write_threshold == 100  # Default
        assert loop._last_maintenance_write_count == 0

    def test_increment_memory_write_count(self):
        """Verify write count increments correctly."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        loop._auto_maintenance_enabled = False  # Disable to avoid triggering

        loop._increment_memory_write_count()
        assert loop._memory_write_count == 1

        loop._increment_memory_write_count(5)
        assert loop._memory_write_count == 6

    def test_maintenance_triggered_at_threshold(self):
        """Verify maintenance is triggered when write threshold is reached."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        loop._maintenance_write_threshold = 10  # Low threshold for testing

        with patch.object(loop, "_run_write_triggered_maintenance") as mock_run:
            # Writes below threshold - no trigger
            for i in range(9):
                loop._increment_memory_write_count()
            mock_run.assert_not_called()

            # 10th write triggers maintenance
            loop._increment_memory_write_count()
            mock_run.assert_called_once()

    def test_maintenance_not_triggered_when_disabled(self):
        """Verify no maintenance when auto-maintenance is disabled."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        loop._auto_maintenance_enabled = False
        loop._maintenance_write_threshold = 5

        with patch("autopack.executor.autonomous_loop.run_maintenance_if_due") as mock_run:
            for i in range(10):
                loop._increment_memory_write_count()

            # Should not have called run_maintenance_if_due
            mock_run.assert_not_called()

    def test_write_count_reset_after_maintenance(self):
        """Verify last maintenance write count is updated after maintenance."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        loop._maintenance_write_threshold = 5

        with patch("autopack.executor.autonomous_loop.run_maintenance_if_due", return_value=None):
            # Trigger maintenance
            for i in range(5):
                loop._increment_memory_write_count()

            # Last maintenance count should be updated
            assert loop._last_maintenance_write_count == 5
            assert loop._memory_write_count == 5

            # Write more - should not trigger until next threshold
            for i in range(4):
                loop._increment_memory_write_count()
            # No additional maintenance call expected

    def test_maintenance_handles_errors_gracefully(self):
        """Verify maintenance errors don't crash the loop."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)
        loop._maintenance_write_threshold = 5

        with patch(
            "autopack.executor.autonomous_loop.run_maintenance_if_due",
            side_effect=Exception("Maintenance failed"),
        ):
            # Should not raise - error is caught and logged
            for i in range(5):
                loop._increment_memory_write_count()

            # Write count should still be updated to prevent retry storm
            assert loop._last_maintenance_write_count == 5


class TestMaintenanceIntegration:
    """Integration tests for combined maintenance triggers."""

    def test_write_and_time_based_triggers_coexist(self):
        """Verify both write-based and time-based triggers work together."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        # Both tracking mechanisms should be initialized
        assert loop._memory_write_count == 0
        assert loop._last_maintenance_check == 0.0
        assert loop._auto_maintenance_enabled is True

    def test_custom_threshold_from_settings(self):
        """Verify custom threshold is loaded from settings via getattr."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        # Mock settings to return custom threshold
        mock_settings = MagicMock()
        mock_settings.maintenance_write_threshold = 50
        # Ensure other required settings have defaults
        mock_settings.max_parallel_phases = 2
        mock_settings.feedback_pipeline_enabled = True
        mock_settings.telemetry_aggregation_interval = 3
        mock_settings.task_effectiveness_tracking_enabled = True
        mock_settings.maintenance_check_interval_seconds = 300.0
        mock_settings.auto_memory_maintenance_enabled = True
        mock_settings.meta_metrics_health_check_enabled = False
        mock_settings.goal_drift_detection_enabled = False

        with patch("autopack.executor.autonomous_loop.settings", mock_settings):
            loop = AutonomousLoop(mock_executor)
            assert loop._maintenance_write_threshold == 50
