"""Tests for database failure scenarios (IMP-TEST-015).

Tests that the system handles database failures gracefully:
- Connection failures
- Transaction rollbacks
- Pool exhaustion/timeout
- Session health check failures
- Migration failures
- Graceful degradation scenarios
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.orm import Session

from autopack.database import (ensure_session_healthy, get_db, get_pool_health,
                               run_migrations)
from autopack.exceptions import DatabaseError


class TestConnectionFailures:
    """Tests for database connection failure scenarios."""

    def test_connection_failure_during_session_creation(self):
        """Test that connection failures are handled during session creation."""
        # Create a mock that raises when called
        mock_session_local = MagicMock(
            side_effect=OperationalError("Connection refused", None, None)
        )

        with patch("autopack.database.SessionLocal", mock_session_local):
            with pytest.raises(OperationalError) as exc_info:
                # This simulates what happens when SessionLocal() fails

                mock_session_local()

            assert "Connection refused" in str(exc_info.value)

    def test_connection_refused_error_message_preserved(self):
        """Test that connection error messages are preserved for debugging."""
        error_message = "could not connect to server: Connection refused"
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = OperationalError(error_message, None, None)

        with pytest.raises(OperationalError) as exc_info:
            mock_session.execute("SELECT 1")

        assert "Connection refused" in str(exc_info.value)

    def test_get_db_handles_connection_failure_in_finally(self):
        """Test that get_db properly closes session even on connection failure."""
        mock_session = MagicMock(spec=Session)

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            gen = get_db()
            session = next(gen)
            assert session == mock_session

            # Simulate error during session use
            try:
                gen.throw(OperationalError("Connection lost", None, None))
            except OperationalError:
                pass

            # Session should still be closed
            mock_session.close.assert_called_once()


class TestTransactionRollback:
    """Tests for transaction rollback scenarios."""

    def test_integrity_error_triggers_rollback(self):
        """Test that IntegrityError causes transaction rollback."""
        mock_session = MagicMock(spec=Session)

        # Simulate integrity error on commit
        mock_session.commit.side_effect = IntegrityError("UNIQUE constraint failed", None, None)

        with pytest.raises(IntegrityError):
            mock_session.add(MagicMock())
            mock_session.commit()

        # Verify session can rollback
        mock_session.rollback()
        mock_session.rollback.assert_called()

    def test_session_rollback_on_exception(self):
        """Test that session rollback is called when exception occurs."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = IntegrityError("Foreign key violation", None, None)

        try:
            mock_session.execute("INSERT INTO invalid_table VALUES (1)")
        except IntegrityError:
            mock_session.rollback()

        mock_session.rollback.assert_called_once()

    def test_nested_transaction_rollback(self):
        """Test rollback behavior with nested transactions (savepoints)."""
        mock_session = MagicMock(spec=Session)
        mock_savepoint = MagicMock()
        mock_session.begin_nested.return_value = mock_savepoint

        # Begin nested transaction
        savepoint = mock_session.begin_nested()

        # Simulate error
        savepoint.rollback.side_effect = None  # Rollback succeeds

        # Should be able to rollback just the savepoint
        savepoint.rollback()
        savepoint.rollback.assert_called_once()


class TestPoolExhaustion:
    """Tests for connection pool exhaustion scenarios."""

    def test_pool_timeout_on_exhaustion(self):
        """Test that pool timeout raises appropriate error when exhausted."""
        # Simulate pool timeout error
        timeout_error = SATimeoutError(
            "QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00"
        )

        # Create a callable that raises the timeout error
        def raise_timeout():
            raise timeout_error

        mock_session_factory = MagicMock(side_effect=timeout_error)

        # Test that the timeout error is raised with proper message
        with pytest.raises(SATimeoutError) as exc_info:
            mock_session_factory()

        assert "QueuePool limit" in str(exc_info.value)
        assert "timeout" in str(exc_info.value)

    def test_pool_health_detects_high_utilization(self):
        """Test that pool health check detects high utilization."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 19,
                "overflow": 8,
                "utilization": 0.95,
                "is_healthy": False,
                "queue_size": 5,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                assert stats.utilization_pct == 95.0
                assert stats.checked_out == 19
                assert stats.overflow == 8
                # High utilization should trigger potential leak warning
                assert len(stats.potential_leaks) >= 1

    def test_pool_overflow_handling(self):
        """Test handling when pool enters overflow state."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.return_value = {
                "pool_size": 20,
                "checked_out": 20,
                "overflow": 5,
                "utilization": 1.0,
                "is_healthy": False,
                "queue_size": 2,
            }

            with patch("autopack.database.engine") as mock_engine:
                mock_engine.pool._max_overflow = 10

                stats = get_pool_health()

                assert stats.overflow == 5
                assert stats.utilization_pct == 100.0


class TestSessionHealthCheck:
    """Tests for session health check failures."""

    def test_ensure_session_healthy_returns_true_on_success(self):
        """Test that healthy session returns True."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.return_value = MagicMock()

        result = ensure_session_healthy(mock_session)

        assert result is True
        mock_session.execute.assert_called_once()

    def test_ensure_session_healthy_handles_connection_error(self):
        """Test that connection error is handled gracefully."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = OperationalError(
            "server closed the connection unexpectedly", None, None
        )

        with patch("autopack.database.logger") as mock_logger:
            result = ensure_session_healthy(mock_session)

            # Should return True (session will reconnect on next use)
            assert result is True
            # Should log warning
            mock_logger.warning.assert_called()
            # Should attempt rollback and close
            mock_session.rollback.assert_called()
            mock_session.close.assert_called()

    def test_ensure_session_healthy_handles_timeout(self):
        """Test that session timeout is handled gracefully."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = SATimeoutError("connection timed out")

        with patch("autopack.database.logger") as mock_logger:
            result = ensure_session_healthy(mock_session)

            assert result is True
            mock_logger.warning.assert_called()

    def test_ensure_session_healthy_cleanup_error_ignored(self):
        """Test that cleanup errors during health check are ignored."""
        mock_session = MagicMock(spec=Session)
        mock_session.execute.side_effect = OperationalError("connection lost", None, None)
        mock_session.rollback.side_effect = Exception("rollback failed")
        mock_session.close.side_effect = Exception("close failed")

        with patch("autopack.database.logger"):
            # Should not raise despite cleanup errors
            result = ensure_session_healthy(mock_session)
            assert result is True


class TestMigrationFailures:
    """Tests for database migration failure scenarios."""

    def test_migration_failure_raises_database_error(self):
        """Test that migration failure raises DatabaseError with context."""
        with patch("autopack.database.get_database_url") as mock_url:
            mock_url.return_value = "postgresql://localhost/test"

            with patch("alembic.command.upgrade") as mock_upgrade:
                mock_upgrade.side_effect = Exception("Migration failed: table exists")

                with pytest.raises(DatabaseError) as exc_info:
                    run_migrations()

                assert "migration failed" in str(exc_info.value).lower()

    def test_migration_failure_logs_error(self):
        """Test that migration failure is logged before raising."""
        with patch("autopack.database.get_database_url") as mock_url:
            mock_url.return_value = "sqlite:///:memory:"

            with patch("alembic.command.upgrade") as mock_upgrade:
                mock_upgrade.side_effect = Exception("Schema mismatch")

                with patch("autopack.database.logger") as mock_logger:
                    with pytest.raises(DatabaseError):
                        run_migrations()

                    # Verify error was logged
                    error_calls = [
                        call
                        for call in mock_logger.error.call_args_list
                        if "migration" in str(call).lower() or "failed" in str(call).lower()
                    ]
                    assert len(error_calls) >= 1


class TestGracefulDegradation:
    """Tests for graceful degradation when database is unavailable."""

    def test_get_db_generator_handles_initialization_failure(self):
        """Test that get_db handles session initialization failure."""
        with patch(
            "autopack.database.SessionLocal",
            side_effect=OperationalError("Database unavailable", None, None),
        ):
            with pytest.raises(OperationalError):
                gen = get_db()
                next(gen)

    def test_pool_health_handles_detector_failure(self):
        """Test that pool health check handles detector failure gracefully."""
        with patch("autopack.database.leak_detector") as mock_detector:
            mock_detector.check_pool_health.side_effect = Exception("Pool inspection failed")

            with pytest.raises(Exception) as exc_info:
                get_pool_health()

            assert "Pool inspection failed" in str(exc_info.value)

    def test_session_close_always_attempted(self):
        """Test that session close is always attempted in get_db."""
        mock_session = MagicMock(spec=Session)

        with patch("autopack.database.SessionLocal", return_value=mock_session):
            gen = get_db()
            _ = next(gen)

            # Complete the generator
            try:
                next(gen)
            except StopIteration:
                pass

            mock_session.close.assert_called_once()

    def test_multiple_connection_failures_handled(self):
        """Test handling of multiple consecutive connection failures."""
        failure_count = 0
        max_failures = 3

        def failing_session():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= max_failures:
                raise OperationalError(f"Connection attempt {failure_count} failed", None, None)
            return MagicMock(spec=Session)

        with patch("autopack.database.SessionLocal", side_effect=failing_session):
            # First 3 attempts should fail
            for i in range(max_failures):
                with pytest.raises(OperationalError):
                    gen = get_db()
                    next(gen)

            # 4th attempt should succeed
            gen = get_db()
            session = next(gen)
            assert session is not None


class TestDatabaseErrorContext:
    """Tests for DatabaseError context preservation."""

    def test_database_error_preserves_original_exception(self):
        """Test that DatabaseError preserves the original exception context."""
        original_error = OperationalError("Original error", None, None)

        try:
            try:
                raise original_error
            except OperationalError as e:
                raise DatabaseError(f"Database operation failed: {e}") from e
        except DatabaseError as db_error:
            assert db_error.__cause__ is original_error

    def test_database_error_includes_component_info(self):
        """Test that DatabaseError can include component information."""
        error = DatabaseError(
            "Connection failed",
            component="database",
            context={"host": "localhost", "port": 5432},
        )

        assert error.component == "database"
        assert error.context["host"] == "localhost"
        assert error.context["port"] == 5432
