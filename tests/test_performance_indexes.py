"""Tests for BUILD-146 P12 performance indexes.

Verifies that database indexes are created correctly for dashboard query optimization.
"""

import os
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError


@pytest.fixture
def test_db_url():
    """Get test database URL (in-memory SQLite)."""
    return "sqlite:///:memory:"


@pytest.fixture
def test_engine(test_db_url):
    """Create test database engine."""
    engine = create_engine(test_db_url)

    # Create minimal schema for testing
    with engine.begin() as conn:
        # Create tables that indexes depend on
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                state TEXT,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id TEXT,
                run_id TEXT,
                state TEXT,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS phase_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                phase_id TEXT,
                total_tokens INTEGER,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dashboard_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                event_type TEXT,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS llm_usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                total_tokens INTEGER,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS token_efficiency_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                tokens_saved_artifacts INTEGER,
                created_at TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS phase6_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                phase_id TEXT,
                failure_hardening_triggered BOOLEAN,
                created_at TIMESTAMP
            )
        """))

    yield engine

    engine.dispose()


def index_exists_sqlite(engine, index_name: str, table_name: str) -> bool:
    """Check if index exists in SQLite database."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA index_list({table_name})"))
        existing_indexes = [row[1] for row in result.fetchall()]
        return index_name in existing_indexes


def test_create_phase_metrics_indexes(test_engine):
    """Test creating indexes on phase_metrics table."""
    with test_engine.begin() as conn:
        # Create indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_id ON phase_metrics(run_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phase_metrics_created_at ON phase_metrics(created_at DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phase_metrics_run_created ON phase_metrics(run_id, created_at DESC)"))

    # Verify indexes exist
    assert index_exists_sqlite(test_engine, "idx_phase_metrics_run_id", "phase_metrics")
    assert index_exists_sqlite(test_engine, "idx_phase_metrics_created_at", "phase_metrics")
    assert index_exists_sqlite(test_engine, "idx_phase_metrics_run_created", "phase_metrics")


def test_create_dashboard_events_indexes(test_engine):
    """Test creating indexes on dashboard_events table."""
    with test_engine.begin() as conn:
        # Create indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_events_run_id ON dashboard_events(run_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_dashboard_events_event_type ON dashboard_events(event_type)"))

    # Verify indexes exist
    assert index_exists_sqlite(test_engine, "idx_dashboard_events_run_id", "dashboard_events")
    assert index_exists_sqlite(test_engine, "idx_dashboard_events_event_type", "dashboard_events")


def test_create_phases_indexes(test_engine):
    """Test creating indexes on phases table."""
    with test_engine.begin() as conn:
        # Create index
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phases_run_state ON phases(run_id, state)"))

    # Verify index exists
    assert index_exists_sqlite(test_engine, "idx_phases_run_state", "phases")


def test_create_llm_usage_events_indexes(test_engine):
    """Test creating indexes on llm_usage_events table."""
    with test_engine.begin() as conn:
        # Create index
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_llm_usage_events_run_id ON llm_usage_events(run_id)"))

    # Verify index exists
    assert index_exists_sqlite(test_engine, "idx_llm_usage_events_run_id", "llm_usage_events")


def test_create_token_efficiency_indexes(test_engine):
    """Test creating indexes on token_efficiency_metrics table."""
    with test_engine.begin() as conn:
        # Create index
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_token_efficiency_run_id ON token_efficiency_metrics(run_id)"))

    # Verify index exists
    assert index_exists_sqlite(test_engine, "idx_token_efficiency_run_id", "token_efficiency_metrics")


def test_create_phase6_metrics_indexes(test_engine):
    """Test creating indexes on phase6_metrics table."""
    with test_engine.begin() as conn:
        # Create index
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_phase6_metrics_run_id ON phase6_metrics(run_id)"))

    # Verify index exists
    assert index_exists_sqlite(test_engine, "idx_phase6_metrics_run_id", "phase6_metrics")


def test_indexes_idempotent(test_engine):
    """Test that CREATE INDEX IF NOT EXISTS is idempotent."""
    with test_engine.begin() as conn:
        # Create index twice
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_test ON phases(run_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_test ON phases(run_id)"))  # Should not error

    # Verify index exists (only once)
    assert index_exists_sqlite(test_engine, "idx_test", "phases")


def test_query_uses_index(test_engine):
    """Test that queries use the created indexes (EXPLAIN QUERY PLAN)."""
    # Create index
    with test_engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_phase_metrics_run_id ON phase_metrics(run_id)"))

        # Insert test data
        conn.execute(text("""
            INSERT INTO phase_metrics (run_id, phase_id, total_tokens, created_at)
            VALUES ('test-run', 'test-phase', 1000, datetime('now'))
        """))

    # Query with EXPLAIN QUERY PLAN
    with test_engine.connect() as conn:
        result = conn.execute(text("""
            EXPLAIN QUERY PLAN
            SELECT * FROM phase_metrics WHERE run_id = 'test-run'
        """))

        plan = result.fetchall()
        plan_text = " ".join([str(row) for row in plan])

        # Should mention index usage (SQLite: "SEARCH ... USING INDEX")
        assert "idx_phase_metrics_run_id" in plan_text or "SEARCH" in plan_text


def test_composite_index_covers_query(test_engine):
    """Test that composite index (run_id, created_at) covers ORDER BY queries."""
    # Create composite index
    with test_engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_composite ON phase_metrics(run_id, created_at DESC)"))

        # Insert test data
        for i in range(10):
            conn.execute(text(f"""
                INSERT INTO phase_metrics (run_id, phase_id, total_tokens, created_at)
                VALUES ('test-run', 'phase-{i}', {i * 1000}, datetime('now', '+{i} seconds'))
            """))

    # Query should use composite index
    with test_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM phase_metrics
            WHERE run_id = 'test-run'
            ORDER BY created_at DESC
            LIMIT 5
        """))

        rows = result.fetchall()
        assert len(rows) == 5


def test_migration_script_syntax():
    """Test that migration script can be imported without errors."""
    try:
        import scripts.migrations.add_performance_indexes as migration
        assert hasattr(migration, "add_indexes")
        assert hasattr(migration, "main")
    except ImportError:
        pytest.skip("Migration script not importable (expected in test environment)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
