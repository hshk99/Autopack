"""
P0.4 Reliability Test: DB initialization guardrails.

Validates that init_db() enforces schema safety:
- Bootstrap mode uses create_all() directly (dev/test)
- Production mode uses Alembic migrations (IMP-OPS-002)
- Prevents accidental schema drift between SQLite/Postgres
- Concurrent bootstrap protection via advisory locks (IMP-OPS-006)
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from autopack.config import Settings
from autopack.exceptions import DatabaseError


# These tests modify global state (autopack.database.engine and autopack.config.settings)
# so they must run on the same worker to avoid race conditions with pytest-xdist
@pytest.mark.xdist_group(name="db_guardrails_global_state")
class TestDBInitGuardrails:
    """Test that DB initialization enforces safety guardrails."""

    def test_init_db_runs_migrations_when_bootstrap_disabled(self, monkeypatch):
        """init_db() should run Alembic migrations when bootstrap is disabled (IMP-OPS-002)."""
        # Use in-memory database for isolation
        db_url = "sqlite:///:memory:"
        test_engine = create_engine(db_url)

        # Use monkeypatch for reliable test isolation in parallel execution
        import autopack.config
        import autopack.database

        monkeypatch.setattr(autopack.database, "engine", test_engine)

        # Create mock settings with bootstrap disabled
        mock_settings = MagicMock()
        mock_settings.db_bootstrap_enabled = False
        monkeypatch.setattr(autopack.config, "settings", mock_settings)

        # Mock run_migrations to verify it gets called
        mock_run_migrations = MagicMock()
        monkeypatch.setattr(autopack.database, "run_migrations", mock_run_migrations)

        from autopack.database import init_db

        # Should call run_migrations (not raise)
        init_db()

        # Verify migrations were called
        mock_run_migrations.assert_called_once()

    def test_init_db_bootstrap_mode_creates_tables(self):
        """init_db() should create tables when bootstrap mode enabled."""
        # Use in-memory database for isolation
        db_url = "sqlite:///:memory:"

        with (
            patch("autopack.database.engine") as mock_engine,
            patch("autopack.config.settings") as mock_settings,
            patch("autopack.database.Base.metadata.create_all") as mock_create,
        ):
            # Mock settings: bootstrap ENABLED
            mock_settings.db_bootstrap_enabled = True

            # Create engine
            test_engine = create_engine(db_url)
            mock_engine.url = test_engine.url

            # Import init_db after patching
            from autopack.database import init_db

            # Should succeed and call create_all
            init_db()  # Should not raise

            # Verify create_all was called
            mock_create.assert_called_once()

    def test_init_db_uses_migrations_not_create_all_when_bootstrap_disabled(self, monkeypatch):
        """init_db() should use run_migrations, not create_all, when bootstrap disabled."""
        # Use in-memory database for isolation
        db_url = "sqlite:///:memory:"
        test_engine = create_engine(db_url)

        # Use monkeypatch for reliable test isolation in parallel execution
        import autopack.config
        import autopack.database

        monkeypatch.setattr(autopack.database, "engine", test_engine)

        # Create mock settings with bootstrap disabled
        mock_settings = MagicMock()
        mock_settings.db_bootstrap_enabled = False
        monkeypatch.setattr(autopack.config, "settings", mock_settings)

        # Mock both run_migrations and create_all to track which gets called
        mock_run_migrations = MagicMock()
        mock_create_all = MagicMock()
        monkeypatch.setattr(autopack.database, "run_migrations", mock_run_migrations)
        monkeypatch.setattr(autopack.database.Base.metadata, "create_all", mock_create_all)

        from autopack.database import init_db

        # Should succeed
        init_db()

        # Verify run_migrations was called, not create_all
        mock_run_migrations.assert_called_once()
        mock_create_all.assert_not_called()

    def test_bootstrap_flag_env_variable_aliases(self):
        """Test that both AUTOPACK_DB_BOOTSTRAP and DB_BOOTSTRAP_ENABLED work."""
        # Test AUTOPACK_DB_BOOTSTRAP
        with patch.dict(os.environ, {"AUTOPACK_DB_BOOTSTRAP": "1"}, clear=False):
            settings = Settings()
            assert settings.db_bootstrap_enabled is True

        # Test DB_BOOTSTRAP_ENABLED
        with patch.dict(os.environ, {"DB_BOOTSTRAP_ENABLED": "1"}, clear=False):
            settings = Settings()
            assert settings.db_bootstrap_enabled is True

        # Test default (disabled) - use explicit env override
        with patch.dict(
            os.environ, {"AUTOPACK_DB_BOOTSTRAP": "0", "DB_BOOTSTRAP_ENABLED": "0"}, clear=False
        ):
            settings = Settings()
            assert settings.db_bootstrap_enabled is False

    def test_migration_failure_raises_database_error(self, monkeypatch):
        """Migration failure should raise DatabaseError (IMP-OPS-002)."""
        # Use in-memory database for isolation
        db_url = "sqlite:///:memory:"
        test_engine = create_engine(db_url)

        # Use monkeypatch for reliable test isolation in parallel execution
        import autopack.config
        import autopack.database

        monkeypatch.setattr(autopack.database, "engine", test_engine)

        # Create mock settings with bootstrap disabled
        mock_settings = MagicMock()
        mock_settings.db_bootstrap_enabled = False
        monkeypatch.setattr(autopack.config, "settings", mock_settings)

        # Mock run_migrations to raise an exception (simulating migration failure)
        def failing_migrations():
            raise DatabaseError("Database migration failed: alembic error")

        monkeypatch.setattr(autopack.database, "run_migrations", failing_migrations)

        from autopack.database import init_db

        # Should raise DatabaseError from migration failure
        with pytest.raises(DatabaseError) as exc_info:
            init_db()

        assert "migration" in str(exc_info.value).lower()


@pytest.mark.xdist_group(name="db_guardrails_global_state")
class TestBootstrapConcurrencyControl:
    """Test migration concurrency control (IMP-OPS-006).

    Validates that PostgreSQL bootstrap uses advisory locks to prevent
    database corruption during concurrent startup.
    """

    def test_bootstrap_uses_advisory_lock_for_postgres(self, monkeypatch):
        """Bootstrap should acquire advisory lock before create_all on PostgreSQL (IMP-OPS-006)."""
        import autopack.database

        # Track executed SQL
        executed_sql = []

        # Create mock connection with execute tracking
        mock_conn = MagicMock()

        def track_execute(sql):
            executed_sql.append(str(sql))

        mock_conn.execute = track_execute
        mock_conn.__enter__ = lambda self: mock_conn
        mock_conn.__exit__ = lambda self, *args: None

        # Mock engine with PostgreSQL dialect
        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"
        mock_engine.connect.return_value = mock_conn
        monkeypatch.setattr(autopack.database, "engine", mock_engine)

        # Mock create_all to avoid actual schema creation
        mock_create_all = MagicMock()
        monkeypatch.setattr(autopack.database.Base.metadata, "create_all", mock_create_all)

        # Call _bootstrap_with_lock directly
        from autopack.database import _bootstrap_with_lock

        _bootstrap_with_lock()

        # Verify advisory lock was acquired
        lock_acquired = any("pg_advisory_lock" in sql for sql in executed_sql)
        assert lock_acquired, f"Advisory lock not acquired. SQL executed: {executed_sql}"

        # Verify advisory lock was released
        lock_released = any("pg_advisory_unlock" in sql for sql in executed_sql)
        assert lock_released, f"Advisory lock not released. SQL executed: {executed_sql}"

        # Verify create_all was called
        mock_create_all.assert_called_once()

    def test_bootstrap_releases_lock_on_exception(self, monkeypatch):
        """Advisory lock should be released even if create_all fails (IMP-OPS-006)."""
        import autopack.database

        # Track executed SQL
        executed_sql = []

        # Create mock connection with execute tracking
        mock_conn = MagicMock()

        def track_execute(sql):
            executed_sql.append(str(sql))

        mock_conn.execute = track_execute
        mock_conn.__enter__ = lambda self: mock_conn
        mock_conn.__exit__ = lambda self, *args: None

        # Mock engine with PostgreSQL dialect
        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"
        mock_engine.connect.return_value = mock_conn
        monkeypatch.setattr(autopack.database, "engine", mock_engine)

        # Mock create_all to raise an exception
        def failing_create_all(**kwargs):
            raise RuntimeError("Schema creation failed")

        monkeypatch.setattr(autopack.database.Base.metadata, "create_all", failing_create_all)

        # Call _bootstrap_with_lock directly
        from autopack.database import _bootstrap_with_lock

        with pytest.raises(RuntimeError):
            _bootstrap_with_lock()

        # Verify advisory lock was still released despite exception
        lock_released = any("pg_advisory_unlock" in sql for sql in executed_sql)
        assert lock_released, "Advisory lock not released after exception"

    def test_bootstrap_skips_lock_for_sqlite(self, monkeypatch):
        """SQLite bootstrap should not attempt advisory lock (IMP-OPS-006)."""
        import autopack.database

        # Track if engine.connect() is called
        connect_called = []

        def track_connect():
            connect_called.append(True)
            raise AssertionError("Should not call connect for SQLite")

        # Mock engine with SQLite dialect
        mock_engine = MagicMock()
        mock_engine.dialect.name = "sqlite"
        mock_engine.connect = track_connect
        monkeypatch.setattr(autopack.database, "engine", mock_engine)

        # Mock create_all to succeed
        mock_create_all = MagicMock()
        monkeypatch.setattr(autopack.database.Base.metadata, "create_all", mock_create_all)

        # Call _bootstrap_with_lock directly
        from autopack.database import _bootstrap_with_lock

        _bootstrap_with_lock()

        # Verify connect was not called (no advisory lock for SQLite)
        assert len(connect_called) == 0, "Should not attempt advisory lock for SQLite"

        # Verify create_all was still called
        mock_create_all.assert_called_once()

    def test_init_db_calls_bootstrap_with_lock_in_bootstrap_mode(self, monkeypatch):
        """init_db should use _bootstrap_with_lock when bootstrap enabled (IMP-OPS-006)."""
        import autopack.config
        import autopack.database

        # Create mock settings with bootstrap enabled
        mock_settings = MagicMock()
        mock_settings.db_bootstrap_enabled = True
        monkeypatch.setattr(autopack.config, "settings", mock_settings)

        # Mock _bootstrap_with_lock to track if it gets called
        mock_bootstrap = MagicMock()
        monkeypatch.setattr(autopack.database, "_bootstrap_with_lock", mock_bootstrap)

        from autopack.database import init_db

        init_db()

        # Verify _bootstrap_with_lock was called
        mock_bootstrap.assert_called_once()

    def test_advisory_lock_id_is_consistent(self):
        """Advisory lock ID should be constant to ensure proper locking (IMP-OPS-006)."""
        from autopack.database import _BOOTSTRAP_ADVISORY_LOCK_ID

        # Verify the lock ID is a non-zero integer
        assert isinstance(_BOOTSTRAP_ADVISORY_LOCK_ID, int)
        assert _BOOTSTRAP_ADVISORY_LOCK_ID != 0

        # Verify it fits in PostgreSQL's bigint range
        assert -9223372036854775808 <= _BOOTSTRAP_ADVISORY_LOCK_ID <= 9223372036854775807


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
