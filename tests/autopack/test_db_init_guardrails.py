"""
P0.4 Reliability Test: DB initialization guardrails.

Validates that init_db() enforces schema safety:
- Bootstrap mode uses create_all() directly (dev/test)
- Production mode uses Alembic migrations (IMP-OPS-002)
- Prevents accidental schema drift between SQLite/Postgres
"""

import os
from unittest.mock import patch, MagicMock

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
        import autopack.database
        import autopack.config

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
        import autopack.database
        import autopack.config

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
        import autopack.database
        import autopack.config

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
