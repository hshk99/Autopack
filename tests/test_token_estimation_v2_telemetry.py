"""
Regression test for TokenEstimationV2 DB telemetry persistence.

Ensures that telemetry events can be written to the database with correct metric semantics.
"""
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.models import Base, TokenEstimationV2Event
from autopack.anthropic_clients import _write_token_estimation_v2_telemetry


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create engine and tables
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    yield Session, db_path

    # Cleanup - dispose engine to release file locks
    engine.dispose()
    try:
        os.unlink(db_path)
    except PermissionError:
        # Windows sometimes holds locks - ignore cleanup error
        pass


def test_telemetry_write_disabled_by_default(temp_db):
    """Test that telemetry is disabled by default (feature flag)."""
    Session, db_path = temp_db

    # Ensure feature flag is disabled
    if "TELEMETRY_DB_ENABLED" in os.environ:
        del os.environ["TELEMETRY_DB_ENABLED"]

    with patch("autopack.database.SessionLocal", Session):
        _write_token_estimation_v2_telemetry(
            run_id="test-run",
            phase_id="test-phase",
            category="implementation",
            complexity="low",
            deliverables=["src/test.py"],
            predicted_output_tokens=1000,
            actual_output_tokens=800,
            selected_budget=4096,
            success=True,
            truncated=False,
            stop_reason="end_turn",
            model="claude-sonnet-4",
        )

    # Should not write anything to DB
    session = Session()
    count = session.query(TokenEstimationV2Event).count()
    session.close()
    assert count == 0, "Telemetry should be disabled by default"


def test_telemetry_write_with_feature_flag(temp_db):
    """Test that telemetry writes correctly when feature flag is enabled."""
    Session, db_path = temp_db

    # Enable feature flag
    os.environ["TELEMETRY_DB_ENABLED"] = "1"

    try:
        with patch("autopack.database.SessionLocal", Session):
            _write_token_estimation_v2_telemetry(
                run_id="test-run",
                phase_id="test-phase",
                category="implementation",
                complexity="medium",
                deliverables=["src/file1.py", "src/file2.py", "tests/test_file.py"],
                predicted_output_tokens=1200,
                actual_output_tokens=800,
                selected_budget=4096,
                success=True,
                truncated=False,
                stop_reason="end_turn",
                model="claude-sonnet-4",
            )

        # Verify event was written
        session = Session()
        try:
            event = session.query(TokenEstimationV2Event).first()
            assert event is not None, "Event should be written to DB"

            # Verify fields
            assert event.run_id == "test-run"
            assert event.phase_id == "test-phase"
            assert event.category == "implementation"
            assert event.complexity == "medium"
            assert event.deliverable_count == 3
            assert event.predicted_output_tokens == 1200
            assert event.actual_output_tokens == 800
            assert event.selected_budget == 4096
            assert event.success is True
            assert event.truncated is False
            assert event.stop_reason == "end_turn"
            assert event.model == "claude-sonnet-4"

            # Verify deliverables JSON
            deliverables = json.loads(event.deliverables_json)
            assert deliverables == ["src/file1.py", "src/file2.py", "tests/test_file.py"]

            # Verify metric calculations
            # SMAPE = |actual - pred| / ((|actual| + |pred|) / 2) * 100
            #       = |800 - 1200| / ((800 + 1200) / 2) * 100
            #       = 400 / 1000 * 100 = 40.0
            assert event.smape_percent is not None
            assert abs(event.smape_percent - 40.0) < 0.01, f"Expected SMAPE ~40.0, got {event.smape_percent}"

            # Waste ratio = predicted / actual = 1200 / 800 = 1.5 (NOT 150)
            assert event.waste_ratio is not None
            assert abs(event.waste_ratio - 1.5) < 0.01, f"Expected waste_ratio ~1.5, got {event.waste_ratio}"

            # Underestimated = actual > pred = 800 > 1200 = False
            assert event.underestimated is False

        finally:
            session.close()

    finally:
        if "TELEMETRY_DB_ENABLED" in os.environ:
            del os.environ["TELEMETRY_DB_ENABLED"]


def test_telemetry_underestimation_case(temp_db):
    """Test metrics when actual > predicted (underestimation)."""
    Session, db_path = temp_db

    os.environ["TELEMETRY_DB_ENABLED"] = "1"

    try:
        with patch("autopack.database.SessionLocal", Session):
            _write_token_estimation_v2_telemetry(
                run_id="test-run",
                phase_id="test-phase",
                category="implementation",
                complexity="high",
                deliverables=["src/complex.py"],
                predicted_output_tokens=500,
                actual_output_tokens=700,
                selected_budget=4096,
                success=True,
                truncated=False,
                stop_reason="end_turn",
                model="claude-sonnet-4",
            )

        session = Session()
        try:
            event = session.query(TokenEstimationV2Event).first()

            # SMAPE = |700 - 500| / ((700 + 500) / 2) * 100 = 200 / 600 * 100 = 33.33
            assert abs(event.smape_percent - 33.33) < 0.01

            # Waste ratio = 500 / 700 = 0.714 (under 1.0 = underestimate)
            assert abs(event.waste_ratio - 0.714) < 0.01

            # Underestimated = actual > pred = 700 > 500 = True
            assert event.underestimated is True

        finally:
            session.close()

    finally:
        del os.environ["TELEMETRY_DB_ENABLED"]


def test_telemetry_deliverable_sanitization(temp_db):
    """Test that deliverables are sanitized (max 20, truncate long paths)."""
    Session, db_path = temp_db

    os.environ["TELEMETRY_DB_ENABLED"] = "1"

    try:
        # Create 25 deliverables (should cap at 20)
        many_deliverables = [f"src/file{i}.py" for i in range(25)]

        # Add one very long path (should truncate to 200 chars)
        long_path = "src/" + "x" * 250 + ".py"
        many_deliverables.append(long_path)

        with patch("autopack.database.SessionLocal", Session):
            _write_token_estimation_v2_telemetry(
                run_id="test-run",
                phase_id="test-phase",
                category="implementation",
                complexity="low",
                deliverables=many_deliverables,
                predicted_output_tokens=1000,
                actual_output_tokens=1000,
                selected_budget=4096,
                success=True,
                truncated=False,
                stop_reason="end_turn",
                model="claude-sonnet-4",
            )

        session = Session()
        try:
            event = session.query(TokenEstimationV2Event).first()
            deliverables = json.loads(event.deliverables_json)

            # Should cap at 20
            assert len(deliverables) == 20, f"Expected 20 deliverables, got {len(deliverables)}"

            # Deliverable count should reflect original count
            assert event.deliverable_count == 26

        finally:
            session.close()

    finally:
        del os.environ["TELEMETRY_DB_ENABLED"]


def test_telemetry_fail_safe(temp_db):
    """Test that telemetry errors don't crash the build."""
    Session, db_path = temp_db

    os.environ["TELEMETRY_DB_ENABLED"] = "1"

    try:
        # Simulate a database error by breaking the session
        def broken_session():
            raise Exception("Simulated DB connection failure")

        with patch("autopack.database.SessionLocal", broken_session):
            # Should not raise - error is logged as warning
            _write_token_estimation_v2_telemetry(
                run_id="test-run",
                phase_id="test-phase",
                category="implementation",
                complexity="low",
                deliverables=["src/test.py"],
                predicted_output_tokens=1000,
                actual_output_tokens=800,
                selected_budget=4096,
                success=True,
                truncated=False,
                stop_reason="end_turn",
                model="claude-sonnet-4",
            )

        # If we get here, the fail-safe worked (no exception raised)
        # Verify DB is still empty (telemetry write failed gracefully)
        session = Session()
        count = session.query(TokenEstimationV2Event).count()
        session.close()
        assert count == 0, "Telemetry should fail gracefully without writing"

    finally:
        del os.environ["TELEMETRY_DB_ENABLED"]
