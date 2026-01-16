"""Tests for database connection pool monitoring (IMP-DB-001)."""

import time
from unittest.mock import MagicMock, patch


from autopack.database import get_pool_health
from autopack.db_leak_detector import ConnectionLeakDetector
from autopack.dashboard_schemas import DatabasePoolStats


class TestDatabasePoolStats:
    """Test DatabasePoolStats schema."""

    def test_database_pool_stats_creation(self):
        """Test creating DatabasePoolStats with valid data."""
        from datetime import datetime

        stats = DatabasePoolStats(
            timestamp=datetime.now(),
            pool_size=20,
            checked_out=10,
            checked_in=10,
            overflow=0,
            max_overflow=10,
            utilization_pct=50.0,
            queue_size=0,
            potential_leaks=[],
            longest_checkout_sec=0.5,
            avg_checkout_ms=10.0,
            avg_checkin_ms=5.0,
            total_checkouts=100,
            total_timeouts=0,
        )

        assert stats.pool_size == 20
        assert stats.checked_out == 10
        assert stats.utilization_pct == 50.0
        assert stats.overflow == 0
        assert len(stats.potential_leaks) == 0

    def test_database_pool_stats_with_leaks(self):
        """Test DatabasePoolStats with detected potential leaks."""
        from datetime import datetime

        leak = {
            "severity": "warning",
            "checked_out": 15,
            "pool_size": 20,
            "message": "High pool utilization: 75.0%",
        }

        stats = DatabasePoolStats(
            timestamp=datetime.now(),
            pool_size=20,
            checked_out=15,
            checked_in=5,
            overflow=0,
            max_overflow=10,
            utilization_pct=75.0,
            queue_size=2,
            potential_leaks=[leak],
            longest_checkout_sec=2.5,
            avg_checkout_ms=15.0,
            avg_checkin_ms=8.0,
            total_checkouts=150,
            total_timeouts=1,
        )

        assert stats.utilization_pct == 75.0
        assert len(stats.potential_leaks) == 1
        assert stats.potential_leaks[0]["severity"] == "warning"


class TestConnectionLeakDetector:
    """Test ConnectionLeakDetector functionality."""

    def test_leak_detector_creation(self):
        """Test creating a ConnectionLeakDetector instance."""
        mock_pool = MagicMock()
        detector = ConnectionLeakDetector(pool=mock_pool, threshold=0.8)

        assert detector.pool == mock_pool
        assert detector.threshold == 0.8

    def test_pool_health_check_healthy_pool(self):
        """Test pool health check with healthy pool."""
        mock_pool = MagicMock()
        mock_pool.size.return_value = 20
        mock_pool.checkedout.return_value = 5
        mock_pool.overflow.return_value = 0

        detector = ConnectionLeakDetector(pool=mock_pool, threshold=0.8)
        health = detector.check_pool_health()

        assert health["pool_size"] == 20
        assert health["checked_out"] == 5
        assert health["overflow"] == 0
        assert health["is_healthy"] is True

    def test_pool_health_check_high_utilization(self):
        """Test pool health check with high utilization."""
        mock_pool = MagicMock()
        mock_pool.size.return_value = 20
        mock_pool.checkedout.return_value = 18
        mock_pool.overflow.return_value = 0

        detector = ConnectionLeakDetector(pool=mock_pool, threshold=0.8)
        health = detector.check_pool_health()

        assert health["pool_size"] == 20
        assert health["checked_out"] == 18
        assert health["utilization"] == 0.9
        assert health["is_healthy"] is False

    def test_force_cleanup_stale_connections(self):
        """Test force cleanup of stale connections."""
        mock_pool = MagicMock()
        detector = ConnectionLeakDetector(pool=mock_pool)

        # Simulate stale connection tracking
        with patch("autopack.db_leak_detector._connection_checkout_times") as mock_times:
            mock_times.items.return_value = [
                (123, time.time() - 35 * 60),  # 35 minutes old
                (456, time.time() - 5 * 60),  # 5 minutes old
            ]

            cleaned = detector.force_cleanup_stale_connections(max_age_minutes=30)
            assert cleaned == 1  # Only first connection is stale


class TestGetPoolHealth:
    """Test get_pool_health() function."""

    def test_get_pool_health_returns_database_pool_stats(self):
        """Test that get_pool_health returns DatabasePoolStats instance."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 8,
                "overflow": 0,
                "utilization": 0.4,
                "is_healthy": True,
                "queue_size": 0,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                assert isinstance(stats, DatabasePoolStats)
                assert stats.pool_size == 20
                assert stats.checked_out == 8
                assert stats.checked_in == 12
                assert stats.overflow == 0
                assert stats.max_overflow == 10

    def test_get_pool_health_with_high_utilization(self):
        """Test get_pool_health with high utilization warning."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 17,
                "overflow": 2,
                "utilization": 0.85,
                "is_healthy": False,
                "queue_size": 3,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                assert stats.utilization_pct == 85.0
                assert stats.checked_out == 17
                assert stats.overflow == 2
                assert len(stats.potential_leaks) == 1
                assert "High pool utilization" in stats.potential_leaks[0]["message"]

    def test_get_pool_health_calculates_checked_in(self):
        """Test that get_pool_health correctly calculates checked_in connections."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 6,
                "overflow": 0,
                "utilization": 0.3,
                "is_healthy": True,
                "queue_size": 0,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                # checked_in = pool_size - checked_out
                assert stats.checked_in == 14


class TestAutonomousLoopPoolHealthLogging:
    """Test autonomous loop pool health logging."""

    def test_log_db_pool_health_disabled(self):
        """Test _log_db_pool_health when feature flag is disabled."""
        from autopack.executor.autonomous_loop import AutonomousLoop
        from unittest.mock import MagicMock

        mock_executor = MagicMock()
        loop = AutonomousLoop(executor=mock_executor)

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.db_pool_monitoring_enabled = False

            with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                loop._log_db_pool_health()
                # Should return early without logging
                mock_logger.warning.assert_not_called()

    def test_log_db_pool_health_enabled_healthy(self):
        """Test _log_db_pool_health with healthy pool."""
        from autopack.executor.autonomous_loop import AutonomousLoop
        from autopack.dashboard_schemas import DatabasePoolStats
        from datetime import datetime
        from unittest.mock import MagicMock

        mock_executor = MagicMock()
        loop = AutonomousLoop(executor=mock_executor)

        healthy_stats = DatabasePoolStats(
            timestamp=datetime.now(),
            pool_size=20,
            checked_out=5,
            checked_in=15,
            overflow=0,
            max_overflow=10,
            utilization_pct=25.0,
            queue_size=0,
            potential_leaks=[],
            longest_checkout_sec=0.1,
            avg_checkout_ms=5.0,
            avg_checkin_ms=3.0,
            total_checkouts=50,
            total_timeouts=0,
        )

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.db_pool_monitoring_enabled = True

            with patch("autopack.database.get_pool_health") as mock_health:
                mock_health.return_value = healthy_stats

                with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                    loop._log_db_pool_health()
                    # Should not log warnings for healthy pool
                    mock_logger.warning.assert_not_called()
                    # Should log debug info
                    mock_logger.debug.assert_called_once()

    def test_log_db_pool_health_enabled_high_utilization(self):
        """Test _log_db_pool_health with high pool utilization."""
        from autopack.executor.autonomous_loop import AutonomousLoop
        from autopack.dashboard_schemas import DatabasePoolStats
        from datetime import datetime
        from unittest.mock import MagicMock

        mock_executor = MagicMock()
        loop = AutonomousLoop(executor=mock_executor)

        high_util_stats = DatabasePoolStats(
            timestamp=datetime.now(),
            pool_size=20,
            checked_out=17,
            checked_in=3,
            overflow=0,
            max_overflow=10,
            utilization_pct=85.0,
            queue_size=1,
            potential_leaks=[
                {
                    "severity": "warning",
                    "checked_out": 17,
                    "pool_size": 20,
                    "message": "High pool utilization: 85.0%",
                }
            ],
            longest_checkout_sec=1.5,
            avg_checkout_ms=20.0,
            avg_checkin_ms=10.0,
            total_checkouts=200,
            total_timeouts=2,
        )

        with patch("autopack.executor.autonomous_loop.settings") as mock_settings:
            mock_settings.db_pool_monitoring_enabled = True

            with patch("autopack.database.get_pool_health") as mock_health:
                mock_health.return_value = high_util_stats

                with patch("autopack.executor.autonomous_loop.logger") as mock_logger:
                    loop._log_db_pool_health()
                    # Should log warning for high utilization
                    warning_calls = [
                        call
                        for call in mock_logger.warning.call_args_list
                        if "utilization high" in str(call)
                    ]
                    assert len(warning_calls) >= 1
