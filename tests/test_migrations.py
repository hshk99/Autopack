"""Tests for Alembic database migrations (IMP-OPS-002).

This test suite verifies that:
- Migration files are valid and can be parsed
- Migrations can be applied and rolled back
- Database schema is properly versioned
- Migration history is tracked correctly

"""

import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from autopack.database import engine, run_migrations
from autopack import models  # noqa: F401 - Import to register models
from autopack.auth.models import User, APIKey  # noqa: F401 - Import to register models
from autopack.usage_recorder import (  # noqa: F401 - Import to register models
    LlmUsageEvent,
    DoctorUsageStats,
    TokenEfficiencyMetrics,
)


@pytest.fixture
def alembic_config():
    """Create Alembic config for testing."""
    from autopack.config import get_database_url

    cfg = Config()
    script_dir = os.path.join(os.path.dirname(__file__), "..", "src", "autopack", "migrations")
    cfg.set_main_option("script_location", script_dir)
    cfg.set_main_option("sqlalchemy.url", get_database_url())
    return cfg


def test_migration_files_exist():
    """Verify all migration files exist and are importable."""
    import glob

    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "autopack", "migrations", "versions"
    )
    migration_files = glob.glob(os.path.join(migrations_dir, "*.py"))

    # Should have at least initial migration
    assert len(migration_files) > 0, "No migration files found"

    # Verify initial migration exists
    initial_migration = os.path.join(migrations_dir, "001_initial_schema.py")
    assert os.path.exists(initial_migration), "Initial migration file not found"

    # Verify migration can be imported
    import importlib.util

    spec = importlib.util.spec_from_file_location("001_initial_schema", initial_migration)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Verify migration has required attributes
    assert hasattr(module, "upgrade"), "Migration missing upgrade() function"
    assert hasattr(module, "downgrade"), "Migration missing downgrade() function"
    assert hasattr(module, "revision"), "Migration missing revision id"


def test_run_migrations_function_exists():
    """Verify run_migrations() function exists in database module."""
    from autopack.database import run_migrations

    assert callable(run_migrations), "run_migrations() is not callable"


def test_alembic_env_exists():
    """Verify Alembic env.py exists and is importable."""
    import autopack.migrations.env as env_module

    # Verify env module has required functions
    assert hasattr(env_module, "run_migrations_online"), "env.py missing run_migrations_online()"
    assert hasattr(env_module, "run_migrations_offline"), "env.py missing run_migrations_offline()"
    assert hasattr(env_module, "upgrade"), "env.py missing upgrade()"


def test_migration_creates_tables(alembic_config):
    """Verify that running migrations creates expected database tables."""
    from sqlalchemy import text

    # Clear existing schema for clean test
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Run migrations
    command.upgrade(alembic_config, "head")

    # Verify tables were created
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # Check for core tables
    assert "users" in table_names, "users table not created by migration"
    assert "api_keys" in table_names, "api_keys table not created by migration"
    assert "runs" in table_names, "runs table not created by migration"
    assert "tiers" in table_names, "tiers table not created by migration"
    assert "phases" in table_names, "phases table not created by migration"
    assert "planning_artifacts" in table_names, "planning_artifacts table not created"
    assert "plan_changes" in table_names, "plan_changes table not created by migration"
    assert "llm_usage_events" in table_names, "llm_usage_events table not created"
    assert "doctor_usage_stats" in table_names, "doctor_usage_stats table not created"
    assert "token_efficiency_metrics" in table_names, "token_efficiency_metrics table not created"

    # Verify indexes were created (check for a few key indexes)
    runs_indexes = [idx["name"] for idx in inspector.get_indexes("runs")]
    assert "ix_runs_id" in runs_indexes, "runs.id index not created"
    assert "ix_runs_state_created" in runs_indexes, "runs state+created index not created"

    phases_indexes = [idx["name"] for idx in inspector.get_indexes("phases")]
    assert "ix_phases_run_state" in phases_indexes, "phases run+state index not created"


def test_migration_downgrade(alembic_config):
    """Verify that migrations can be downgraded."""
    from sqlalchemy import text

    # Clear schema and upgrade to head
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    command.upgrade(alembic_config, "head")

    # Verify tables exist
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    assert len(table_names) > 0, "No tables after upgrade"

    # Downgrade to base (no migrations)
    command.downgrade(alembic_config, "base")

    # Verify all tables were dropped
    inspector = inspect(engine)
    table_names_after_downgrade = inspector.get_table_names()
    assert len(table_names_after_downgrade) == 0, "Tables still exist after downgrade"


def test_migration_version_tracking(alembic_config):
    """Verify that Alembic tracks migration versions correctly."""
    from sqlalchemy import text

    # Clear schema for clean test
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Run migrations
    command.upgrade(alembic_config, "head")

    # Check alembic_version table
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one()

    # Should be at initial migration version
    assert version == "001_initial_schema", f"Unexpected version: {version}"


def test_database_module_exports_run_migrations():
    """Verify database module exports run_migrations."""
    from autopack.database import run_migrations

    assert run_migrations is not None, "run_migrations not exported from database module"
    assert callable(run_migrations), "run_migrations is not callable"


def test_migration_template_exists():
    """Verify Alembic migration template exists."""
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "autopack", "migrations", "script.py.mako"
    )
    assert os.path.exists(template_path), "script.py.mako template not found"

    # Read and verify template content
    with open(template_path, "r") as f:
        content = f.read()

    # Verify template has required placeholders
    assert "${message}" in content, "Template missing ${message} placeholder"
    assert "${up_revision}" in content, "Template missing ${up_revision} placeholder"
    assert "${down_revision}" in content, "Template missing ${down_revision} placeholder"
    assert "def upgrade()" in content, "Template missing upgrade() function"
    assert "def downgrade()" in content, "Template missing downgrade() function"


def test_alembic_ini_exists():
    """Verify alembic.ini configuration exists."""
    ini_path = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
    assert os.path.exists(ini_path), "alembic.ini not found"

    # Read and verify configuration
    with open(ini_path, "r") as f:
        content = f.read()

    # Verify required sections
    assert "[alembic]" in content, "alembic.ini missing [alembic] section"
    assert "script_location" in content, "alembic.ini missing script_location"
    assert "sqlalchemy.url" in content, "alembic.ini missing sqlalchemy.url"


@pytest.mark.skipif(
    os.getenv("CI") == "true",
    reason="Skip in CI to avoid PostgreSQL connection issues",
)
def test_run_migrations_integration():
    """Integration test for run_migrations() function.

    This test verifies that run_migrations() can be called successfully
    and properly upgrades the database schema.
    """
    from sqlalchemy import text

    # Clear schema for clean test
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    # Call run_migrations (same as app startup)
    run_migrations()

    # Verify migrations were applied
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # Should have created tables
    assert "runs" in table_names, "runs table not created by run_migrations()"

    # Verify alembic_version table exists and has correct version
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one_or_none()

    assert version is not None, "alembic_version table not created or empty"
    assert version == "001_initial_schema", f"Unexpected version: {version}"
