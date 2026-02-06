"""
Tests for SQL injection prevention in schema validator.

Verifies that schema repair operations use parameterized queries
instead of f-string SQL construction.
"""

import tempfile

import pytest
from sqlalchemy import create_engine, text

from autopack.models import PhaseState, RunState, TierState
from autopack.schema_validator import SchemaValidationError, SchemaValidator


@pytest.fixture
def in_memory_db():
    """Create SQLite database for testing."""
    import os

    # Use a temporary file for the database
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = db_file.name
    db_file.close()

    db_url = f"sqlite:///{db_path.replace(chr(92), '/')}"  # Handle Windows paths
    engine = create_engine(db_url)

    # Create runs table
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL
            )
        """))
        conn.commit()

        # Create phases table
        conn.execute(text("""
            CREATE TABLE phases (
                phase_id TEXT PRIMARY KEY,
                state TEXT NOT NULL
            )
        """))
        conn.commit()

        # Create tiers table
        conn.execute(text("""
            CREATE TABLE tiers (
                tier_id TEXT PRIMARY KEY,
                state TEXT NOT NULL
            )
        """))
        conn.commit()

    yield db_url

    # Cleanup
    engine.dispose()
    try:
        os.unlink(db_path)
    except Exception:
        pass


def test_invalid_run_state_uses_parameterized_query(in_memory_db):
    """Test that invalid run state repairs use parameterized queries."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Insert invalid state
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO runs (id, state) VALUES ('run1', 'INVALID')"))
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    # Check for error
    assert not result.is_valid
    assert len(result.errors) == 1

    error = result.errors[0]
    assert error.table == "runs"
    assert error.column == "state"
    assert error.invalid_value == "INVALID"
    assert error.affected_rows == ["run1"]

    # Verify parameterized query is used (no f-strings)
    assert ":new_state" in error.repair_sql
    assert ":old_state" in error.repair_sql
    assert "'" not in error.repair_sql  # No quoted values in SQL
    assert error.repair_params["new_state"] in [s.value for s in RunState]
    assert error.repair_params["old_state"] == "INVALID"


def test_invalid_phase_state_uses_parameterized_query(in_memory_db):
    """Test that invalid phase state repairs use parameterized queries."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Insert invalid state
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO phases (phase_id, state) VALUES ('phase1', 'BAD_STATE')"))
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    # Find phase error
    phase_errors = [e for e in result.errors if e.table == "phases"]
    assert len(phase_errors) == 1

    error = phase_errors[0]
    assert error.table == "phases"
    assert error.column == "state"
    assert error.invalid_value == "BAD_STATE"

    # Verify parameterized query
    assert ":new_state" in error.repair_sql
    assert ":old_state" in error.repair_sql
    assert "'" not in error.repair_sql
    assert error.repair_params["new_state"] in [s.value for s in PhaseState]
    assert error.repair_params["old_state"] == "BAD_STATE"


def test_invalid_tier_state_uses_parameterized_query(in_memory_db):
    """Test that invalid tier state repairs use parameterized queries."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Insert invalid state
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO tiers (tier_id, state) VALUES ('tier1', 'BROKEN')"))
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    # Find tier error
    tier_errors = [e for e in result.errors if e.table == "tiers"]
    assert len(tier_errors) == 1

    error = tier_errors[0]
    assert error.table == "tiers"
    assert error.column == "state"
    assert error.invalid_value == "BROKEN"

    # Verify parameterized query
    assert ":new_state" in error.repair_sql
    assert ":old_state" in error.repair_sql
    assert "'" not in error.repair_sql
    assert error.repair_params["new_state"] in [s.value for s in TierState]
    assert error.repair_params["old_state"] == "BROKEN"


def test_repair_sql_can_be_executed_safely(in_memory_db):
    """Test that repair SQL can be safely executed with parameters."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Insert invalid state
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO runs (id, state) VALUES ('run1', 'INVALID')"))
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    error = result.errors[0]

    # Execute the repair SQL safely with parameters
    with engine.connect() as conn:
        conn.execute(text(error.repair_sql), error.repair_params)
        conn.commit()

    # Verify the fix was applied
    with engine.connect() as conn:
        new_state = conn.execute(text("SELECT state FROM runs WHERE id = 'run1'")).scalar()
        assert new_state == error.repair_params["new_state"]


def test_repair_params_prevent_injection(in_memory_db):
    """Test that repair parameters prevent SQL injection."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Insert a state that looks like SQL injection
    injection_payload = "VALID'; DROP TABLE runs; --"
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO runs (id, state) VALUES ('run1', :state)"),
            {"state": injection_payload},
        )
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    error = result.errors[0]
    assert error.invalid_value == injection_payload

    # Execute repair safely - injection payload should be treated as literal value
    with engine.connect() as conn:
        conn.execute(text(error.repair_sql), error.repair_params)
        conn.commit()

        # Verify runs table still exists (injection was prevented)
        table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='runs'")
        ).scalar()
        assert table_exists is not None

        # Verify the injected value was treated as a literal string
        state = conn.execute(text("SELECT state FROM runs WHERE id = 'run1'")).scalar()
        assert state == error.repair_params["new_state"]
        assert state != injection_payload


def test_no_f_string_sql_in_error_construction():
    """Test that SchemaValidationError stores parameterized queries."""
    # Create error manually to verify no f-strings are used
    error = SchemaValidationError(
        table="runs",
        column="state",
        invalid_value="INVALID",
        affected_rows=["run1", "run2"],
        suggested_fix="PENDING",
        repair_sql="UPDATE runs SET state = :new_state WHERE state = :old_state",
        repair_params={"new_state": "PENDING", "old_state": "INVALID"},
    )

    # Verify the repair_sql uses placeholders, not f-string interpolation
    assert ":new_state" in error.repair_sql
    assert ":old_state" in error.repair_sql
    # The SQL should not contain actual values
    assert "PENDING" not in error.repair_sql
    assert "INVALID" not in error.repair_sql
    # Verify parameters are separate
    assert error.repair_params["new_state"] == "PENDING"
    assert error.repair_params["old_state"] == "INVALID"


def test_valid_schema_no_errors(in_memory_db):
    """Test that valid schema produces no errors."""
    db_url = in_memory_db
    engine = create_engine(db_url)

    # Get first valid value from each enum
    run_state = next(iter(RunState)).value
    phase_state = next(iter(PhaseState)).value
    tier_state = next(iter(TierState)).value

    # Insert valid states
    with engine.connect() as conn:
        conn.execute(text(f"INSERT INTO runs (id, state) VALUES ('run1', '{run_state}')"))
        conn.execute(
            text(f"INSERT INTO phases (phase_id, state) VALUES ('phase1', '{phase_state}')")
        )
        conn.execute(text(f"INSERT INTO tiers (tier_id, state) VALUES ('tier1', '{tier_state}')"))
        conn.commit()

    # Validate schema
    validator = SchemaValidator(db_url)
    result = validator.validate_on_startup()

    assert result.is_valid
    assert len(result.errors) == 0
