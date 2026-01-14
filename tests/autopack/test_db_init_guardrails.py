"""
P0.4 Reliability Test: DB initialization guardrails.

Validates that init_db() enforces schema safety:
- Fails fast when schema is missing (unless bootstrap enabled)
- Prevents accidental schema drift between SQLite/Postgres
"""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String

from autopack.config import Settings


class TestDBInitGuardrails:
    """Test that DB initialization enforces safety guardrails."""

    def test_init_db_fails_fast_on_missing_schema(self):
        """init_db() should fail fast when schema is missing (bootstrap disabled)."""
        # Use in-memory database for isolation
        db_url = "sqlite:///:memory:"

        # Patch both engine creation and config.settings (imported inside init_db)
        with (
            patch("autopack.database.engine") as mock_engine,
            patch("autopack.config.settings") as mock_settings,
        ):
            # Mock settings: bootstrap DISABLED
            mock_settings.db_bootstrap_enabled = False

            # Create empty engine
            test_engine = create_engine(db_url)
            mock_engine.url = test_engine.url
            mock_engine.connect = test_engine.connect

            # Import init_db after patching
            from autopack.database import init_db

            # Should raise RuntimeError with clear message
            with pytest.raises(RuntimeError) as exc_info:
                init_db()

            error_msg = str(exc_info.value)
            assert "DATABASE SCHEMA MISSING" in error_msg
            assert "AUTOPACK_DB_BOOTSTRAP=1" in error_msg

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

    def test_init_db_validates_existing_schema(self):
        """init_db() should pass validation when schema exists (bootstrap disabled)."""
        # Use in-memory database with pre-populated schema
        db_url = "sqlite:///:memory:"
        test_engine = create_engine(db_url)

        # Create a minimal schema with 'runs' table
        metadata = MetaData()
        Table("runs", metadata, Column("id", String, primary_key=True), Column("status", String))
        metadata.create_all(test_engine)

        # Replace the engine object itself with our pre-populated test engine
        import autopack.database

        original_engine = autopack.database.engine
        autopack.database.engine = test_engine

        try:
            with (
                patch("autopack.config.settings") as mock_settings,
                patch("autopack.database.Base.metadata.create_all") as mock_create,
            ):
                # Mock settings: bootstrap DISABLED
                mock_settings.db_bootstrap_enabled = False

                # Import init_db after patching
                from autopack.database import init_db

                # Should succeed without calling create_all
                init_db()  # Should not raise

                # Verify create_all was NOT called
                mock_create.assert_not_called()
        finally:
            # Restore original engine
            autopack.database.engine = original_engine

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

    def test_missing_runs_table_triggers_error(self):
        """Even if some tables exist, missing 'runs' table should fail."""
        # Use in-memory database with partial schema
        db_url = "sqlite:///:memory:"
        test_engine = create_engine(db_url)

        # Create some tables but NOT 'runs'
        metadata = MetaData()
        Table("llm_usage_events", metadata, Column("id", Integer, primary_key=True))
        Table("users", metadata, Column("id", Integer, primary_key=True))
        metadata.create_all(test_engine)

        with (
            patch("autopack.database.engine") as mock_engine,
            patch("autopack.config.settings") as mock_settings,
        ):
            mock_settings.db_bootstrap_enabled = False

            # Use the partial-schema engine
            mock_engine.url = test_engine.url
            mock_engine.connect = test_engine.connect

            # Import init_db after patching
            from autopack.database import init_db

            # Should raise RuntimeError
            with pytest.raises(RuntimeError) as exc_info:
                init_db()

            assert "runs" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
