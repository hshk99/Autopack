"""
Test that init_db() correctly registers ALL tables from usage_recorder.py

This drift test prevents "works on my machine" issues where existing DBs
have tables but fresh DBs are missing them due to incomplete imports.

BUILD-145 P0: Ensures init_db() imports all usage_recorder ORM classes.
"""

import pytest
from sqlalchemy import create_engine, inspect
from autopack.database import Base, init_db


def test_init_db_registers_all_usage_recorder_tables():
    """
    Verify that init_db() creates ALL tables from usage_recorder.py on a fresh DB.

    This test catches regressions where init_db() only imports some ORM classes
    but not others, causing missing tables on fresh databases.
    """
    # Create in-memory SQLite database (starts completely empty)
    engine = create_engine("sqlite:///:memory:")

    # Temporarily override the module-level engine for init_db
    import autopack.database as db_module
    original_engine = db_module.engine
    db_module.engine = engine

    try:
        # Call init_db() to register and create all tables
        init_db()

        # Inspect the created tables
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

        # Assert all 3 usage_recorder tables exist
        required_tables = {
            "llm_usage_events",          # LlmUsageEvent
            "doctor_usage_stats",        # DoctorUsageStats
            "token_efficiency_metrics",  # TokenEfficiencyMetrics
        }

        missing_tables = required_tables - table_names

        assert not missing_tables, (
            f"init_db() failed to create tables: {missing_tables}. "
            f"Check that database.py imports ALL ORM classes from usage_recorder.py"
        )

        # Also verify core models exist
        assert "runs" in table_names, "Missing runs table"
        assert "phases" in table_names, "Missing phases table"
        assert "tiers" in table_names, "Missing tiers table"

    finally:
        # Restore original engine
        db_module.engine = original_engine


def test_usage_recorder_tables_have_expected_columns():
    """
    Verify that usage_recorder tables have expected columns.

    This catches schema drift where tables exist but columns are missing.
    """
    engine = create_engine("sqlite:///:memory:")

    import autopack.database as db_module
    original_engine = db_module.engine
    db_module.engine = engine

    try:
        init_db()
        inspector = inspect(engine)

        # Check LlmUsageEvent columns
        llm_columns = {col["name"] for col in inspector.get_columns("llm_usage_events")}
        assert "id" in llm_columns
        assert "run_id" in llm_columns
        assert "phase_id" in llm_columns
        assert "model" in llm_columns
        assert "prompt_tokens" in llm_columns
        assert "completion_tokens" in llm_columns
        assert "total_tokens" in llm_columns

        # Check DoctorUsageStats columns (per-run, not per-phase)
        doctor_columns = {col["name"] for col in inspector.get_columns("doctor_usage_stats")}
        assert "id" in doctor_columns
        assert "run_id" in doctor_columns
        assert "doctor_calls_total" in doctor_columns
        assert "doctor_actions" in doctor_columns

        # Check TokenEfficiencyMetrics columns
        token_columns = {col["name"] for col in inspector.get_columns("token_efficiency_metrics")}
        assert "id" in token_columns
        assert "run_id" in token_columns
        assert "phase_id" in token_columns
        assert "artifact_substitutions" in token_columns
        assert "tokens_saved_artifacts" in token_columns

    finally:
        db_module.engine = original_engine
