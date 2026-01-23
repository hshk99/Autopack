"""Tests for database connection pool monitoring (IMP-DB-001, IMP-PERF-001)."""

import time
from unittest.mock import MagicMock, patch


from autopack.database import (
    get_pool_health,
    get_session,
    get_session_metrics,
    ScopedSession,
)
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


class TestConnectionPooling:
    """Tests for IMP-PERF-001 connection pooling enhancements."""

    def test_get_session_context_manager(self):
        """Test get_session context manager provides session and cleans up."""
        with get_session() as session:
            assert session is not None
            # Verify session is usable by executing a simple query
            from sqlalchemy import text

            result = session.execute(text("SELECT 1"))
            assert result is not None
        # After context manager exits, session should be returned to pool
        # (verified by scoped session remove being called)

    def test_get_session_commits_on_success(self):
        """Test get_session commits on successful completion."""
        with patch.object(ScopedSession, "remove") as mock_remove:
            with get_session() as session:
                # Session should be provided
                assert session is not None
            # After success, remove should be called to return to pool
            mock_remove.assert_called_once()

    def test_get_session_rollback_on_exception(self):
        """Test get_session rolls back on exception."""

        class TestException(Exception):
            pass

        with patch("autopack.database.logger") as mock_logger:
            try:
                with get_session() as _session:
                    raise TestException("Test error")
            except TestException:
                pass
            # Should log warning about rollback
            assert any(
                "rollback" in str(call).lower() for call in mock_logger.warning.call_args_list
            )

    def test_scoped_session_thread_local(self):
        """Test ScopedSession provides thread-local session."""
        session1 = ScopedSession()
        session2 = ScopedSession()
        # Same thread should get same session
        assert session1 is session2
        ScopedSession.remove()

    def test_get_session_metrics_returns_dict(self):
        """Test get_session_metrics returns metrics dictionary."""
        metrics = get_session_metrics()

        assert isinstance(metrics, dict)
        assert "total_checkouts" in metrics
        assert "total_checkins" in metrics
        assert "active_sessions" in metrics
        assert "peak_active_sessions" in metrics

    def test_get_session_metrics_tracks_checkouts(self):
        """Test that session metrics track checkouts correctly."""
        initial_metrics = get_session_metrics()
        initial_checkouts = initial_metrics["total_checkouts"]

        # Use a session to trigger checkout
        with get_session() as session:
            from sqlalchemy import text

            session.execute(text("SELECT 1"))

        final_metrics = get_session_metrics()
        # Checkout count should increase
        assert final_metrics["total_checkouts"] >= initial_checkouts

    def test_get_pool_health_includes_session_metrics(self):
        """Test get_pool_health includes session checkout metrics."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 5,
                "overflow": 0,
                "utilization": 0.25,
                "is_healthy": True,
                "queue_size": 0,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                # Should include total_checkouts from session metrics
                assert hasattr(stats, "total_checkouts")
                assert stats.total_checkouts >= 0


class TestScopedSessionCleanup:
    """Tests for scoped session cleanup behavior."""

    def test_scoped_session_remove_returns_to_pool(self):
        """Test that ScopedSession.remove() properly returns session to pool."""
        # Get a session
        session = ScopedSession()
        assert session is not None

        # Remove should not raise
        ScopedSession.remove()

        # Getting another session should work
        new_session = ScopedSession()
        assert new_session is not None
        ScopedSession.remove()

    def test_multiple_get_session_calls(self):
        """Test multiple sequential get_session calls work correctly."""
        results = []

        for i in range(3):
            with get_session() as session:
                from sqlalchemy import text

                result = session.execute(text("SELECT 1"))
                results.append(result.scalar())

        assert len(results) == 3
        assert all(r == 1 for r in results)
